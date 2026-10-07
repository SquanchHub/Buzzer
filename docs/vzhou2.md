# Vincent Zhou (vzhou2)

My individual T10 document. The four T10 sections come first; my per-session work log is at the
end ([Session Log](#session-log)).

## 1. Repository and Codebase Organization

### How the pieces fit

Buzzer is one backend and three frontends, all behind one nginx entry point (`docker compose up`):

- **`backend/`** (FastAPI + python-socketio). Each layer has one job:
  - `app/routers/`: REST endpoints per role (`admin`, `host`, `auth`, …). They stay thin and
    delegate to the service layer.
  - `app/services/`: the business rules. For example, `content_service` handles games and
    questions, `game_service` handles answers and scoring, `state_service` handles the Redis
    room state, and `image_service` handles T8 images.
  - `app/models/` holds the SQLAlchemy tables (MySQL, migrated by Alembic). `app/schemas/` holds
    the Pydantic request and response shapes, including per-question-type validation.
  - `app/common/` holds auth dependencies (`RequireAdmin`, `RequireHost`, …), error shapes and
    the DB session.
  - `app/websocket/` holds the live-game gateway: socket events, the host state machine and
    the timers.
- **`frontend/admin`**: an admin console for courses, games, question editors, images, rosters
  and sessions.
- **`frontend/host`**: a host's own course/game setup, plus the big-screen live game.
- **`frontend/player`**: a phone app for joining, answering and seeing results.

Each frontend has the same `src/pages`, `src/components` and `src/lib` (API client, socket and
theme) split. Shared code is duplicated, not packaged, which is a gotcha I noted in
[frontend/README.md](../frontend/README.md).

Data is split by lifetime:
- **MySQL** holds what must survive: users, courses, games, questions, sessions, answers and
  images.
- **Redis** holds what only matters while a room is live: room state, the current question,
  who has answered and player sockets.

### Data flow of one game round

1. **Host starts a question.**
   - The host screen emits `host_advance` over its socket.
   - `on_host_advance` in [gateway.py](../backend/app/websocket/gateway.py) is a three-phase
     state machine (`LOBBY → QUESTION → RESULTS → …`). From the lobby or from results, it
     loads the next question and writes the current question and phase to Redis through
     `state_service`.
   - It starts the question timer and broadcasts `new_question` to the room.
   - Players receive a payload without the answer key. The answer key (`answer_data`) never
     leaves the server.
2. **Player submits an answer.**
   - The phone emits `submit_answer`. `on_submit_answer` checks four things:
     - the room is in the `QUESTION` phase;
     - the question is not locked;
     - the question ID matches the active one;
     - the player has not already answered (a Redis set).
   - It validates type-specific shapes, such as the hotspot tap or the ordering permutation.
   - It calls `game_service.record_answer`, which scores the answer server-side and writes an
     `Answer` row.
   - It **commits before emitting**. I made this ordering explicit in the
     `fix/get-db-commit-timing` work, so a host that advances immediately sees the row.
   - It sends the player `answer_received` and the host the `answer_status` count. When
     everyone has answered, it sends `answer_phase_ended`.
3. **Results.**
   - The host emits `host_advance` again, or the timer fires. In the `QUESTION` phase, the
     server aggregates the answers from MySQL into per-option counts and the leaderboard, and
     sets the phase to `RESULTS`.
   - It emits `question_results`: the host gets the distribution, and each player gets their
     own points and correctness.
   - The next advance either starts the next question or emits `game_over`.
   - A refreshed or reconnected client uses `rejoin_room` and gets `sync_state` from Redis.

### Context files I wrote (T3)

In the team split, I took the data and admin side, and Arjun took routers, services, websocket,
host and player.

**Leaf READMEs I wrote** (2026-09-30, branch `docs/t3-context-vincent`):
- [backend/app/models/](../backend/app/models/README.md)
- [backend/app/schemas/](../backend/app/schemas/README.md)
- [backend/app/common/](../backend/app/common/README.md)
- [frontend/admin/src/pages/](../frontend/admin/src/pages/README.md)
- [frontend/admin/src/components/](../frontend/admin/src/components/README.md)
- [frontend/admin/src/lib/](../frontend/admin/src/lib/README.md)

**Roll-ups I wrote:**
- [backend/app/](../backend/app/README.md)
- [backend/](../backend/README.md)
- [frontend/admin/src/](../frontend/admin/src/README.md)
- [frontend/host/src/](../frontend/host/src/README.md) and
  [frontend/player/src/](../frontend/player/src/README.md), built from Arjun's leaf READMEs
- [frontend/](../frontend/README.md)

What I learned writing them:

- **Writing bottom-up forces you to read the code.** You can't summarise a directory you
  haven't read, and each leaf README surfaced a real problem:
  - deleting a question failed on a foreign key (models);
  - the update path skipped the per-type validation (schemas);
  - there was no course-scoped permission check (common), which T4 later had to add;
  - the admin JSX showed literal `·` escapes (admin pages), which I finally fixed in T9.
- **Roll-ups find gaps that no single file shows.** The player roll-up noted that players never
  see the question prompt on their phone. That same fact later became a blocking Goldfish item
  in the T8 design. Without the README, I would have designed prompt images for a screen that
  doesn't show prompts.
- **READMEs go stale fast.** After merging main the same evening, I had to correct the host and
  player error-parsing notes, the auto-advance description and the JWT-key warning. That is why
  the `context-sync` rule exists, and why I updated READMEs in the same branch as the code on
  every later task (for example, `cd1497f` for T9).
- **They paid off as AI context.** Every later design and Goldfish subagent was told to load
  the README chain, not the source. That kept prompts small, and it meant a fresh session could
  understand the code in minutes.

## 2. Design Process (Elephant/Goldfish)

My design docs:
- [T8 image support](plans/t8-image-support.md)
- [T7 ordering question type](plans/t7-ordering.md)
- [T6 sample games plan](plans/t6-sample-games-vincent.md)
- [T9 theming](plans/t9-theming.md)

I implemented phases 1 and 3 of [T4 UI restructuring](plans/t4-ui-restructuring.md). Arjun
led its design, and I recorded my phase 1 and phase 3 decisions in §6.

**How the Elephant phase produced the doc.** For T8, the Elephant was a long discussion in one
session ([ai_log, session `bde9947c`](../ai_log/2026-10-04_21-37-26_bde9947c.md), 2026-10-04):
1. I merged the branches T8 depended on and loaded only the relevant READMEs.
2. Claude laid out the open decisions with options, and I asked for pros and cons and for what
   the instructions and rubric implied ("Does anything in the instructions or rubric help make
   these choices?").
3. I made the calls: DB-stored images with per-course reuse, a version 2 export, and
   upload-and-repoint replace.
4. We wrote the doc down with an explicit split: my upload and management half, Arjun's canvas
   integration half, and the contract between the two.

Claude first started drafting it as an online Claude Doc. I stopped that and moved it into
`docs/plans/` because the design doc is graded as a committed repo artifact. That correction is
now a memory and a CLAUDE.md rule.

For T7 and T9, I ran the Elephant phase in a **fresh subagent** given the brief and the
READMEs, not in my long-running session. That keeps the design separate from whatever my main
session had been assuming.

**What the Goldfish caught.** Each Goldfish was a fresh subagent given only the doc and the
standing docs. It had to explain the feature back, critique it, and say whether an implementer
could start without asking questions. Each doc has a dated revision section listing what
changed:

- **T8 (§13).** The Goldfish judged that neither owner could start. Three blocking gaps:
  - Raw image IDs in import bundles would bind to arbitrary local images. Fixed by rejecting
    raw IDs and allowing only refs in version 2.
  - My `ImagePicker` contract used `null` where Arjun's `HotspotEditor` used `undefined`, with
    no stated source for `courseId`. Fixed with an adapter, a defined `courseId` source and
    disabled pickers for unassigned games.
  - The draft put prompt images on the player screen, which never shows prompts. Fixed: prompt
    images go on the big screen.

  It also caught that two concurrent identical uploads would hit an `IntegrityError` → 500.
  Duplicate uploads did cause trouble in testing anyway: a related deadlock showed up, and I
  fixed it with test 22 already in place.
- **T7 ordering (§13).** The Elephant subagent had already corrected my own premise: I had
  assumed COMPLETENESS meant partial credit, but in this codebase it means participation
  credit, so partial credit moved behind an ACCURACY flag. The Goldfish then found one blocking
  item, wrong helper locations in the test plan, an inconsistent "adjacent pairs" table, and an
  editor rule that reshuffled every item on each move.
- **T6 (§8).** The Goldfish doubled as a fact check:
  - two answer keys were arguable (white chocolate "cocoa solids", butter in pesto);
  - two hotspot rings were unfair to taps that were correct but off-centre.
- **T9 (§13).** The doc said `focus-visible:ring-0` on inputs, which would have hidden keyboard
  focus. The Goldfish also found several colour pairs below WCAG contrast that I hadn't
  computed (Night focus on the ink slab was 2.18:1). It required static Tailwind class maps,
  because dynamic class names are purged at build time.

  The theme screenshots are in [`docs/ui/t9/`](ui/t9/): 38 before and 76 after, light and
  dark. The full side-by-side table is in [docs/ui/README.md](ui/README.md#t9-theming--t9-before--after).
  A few pairs:

  | Screen | Before | After (Paper) | After (Night) |
  |---|---|---|---|
  | Host lobby | [before](ui/t9/before-dark-host-lobby.png) | [Paper](ui/t9/after-light-host-lobby.png) | [Night](ui/t9/after-dark-host-lobby.png) |
  | Player question | [before](ui/t9/before-dark-player-mc-question.png) | [Paper](ui/t9/after-light-player-mc-question.png) | [Night](ui/t9/after-dark-player-mc-question.png) |
  | Host results | [before](ui/t9/before-dark-host-mc-results.png) | [Paper](ui/t9/after-light-host-mc-results.png) | [Night](ui/t9/after-dark-host-mc-results.png) |
  | Admin courses | [before](ui/t9/before-dark-admin-courses.png) | [Paper](ui/t9/after-light-admin-courses.png) | [Night](ui/t9/after-dark-admin-courses.png) |

**Did it change how I implemented?** Yes, in three concrete ways:
- The revised docs ended with a numbered, test-first implementation order. For T8 that was
  V0–V9 split by owner. I could implement one step at a time with failing tests already
  written, without re-deciding anything.
- When implementation diverged, I updated the doc first. For example, T9 dropped its CI job
  and the spec was updated to match.
- I learned to trust a fresh reader over myself. Every blocking Goldfish item was something I
  had read past because I already "knew" what I meant.

The cost is real: the T8 design took about 1.5 hours before any code. But during
implementation I was building, not re-deciding. The only design-level change in T8 came from a
bug found in testing, not from a gap in the doc.

## 3. AI Tools Used

**Claude Code** (Opus, mostly in VS Code) was the only AI tool I used.
Every prompt and tool call is recorded in [`ai_log/`](../ai_log/) by the project's
`UserPromptSubmit`/`Stop` hook. Files are named `<timestamp>_<session-id-prefix>.md`, and my
session IDs are listed below.

The `a05e4b3f` logs (the socket-reconnect fix) are on branch `fix/player-socket-reconnect`. The
other session IDs in `ai_log/` (`c57d751e`, `c7123e9d`, `2289c0ca`, `8732fdd2`, `cfcfbdde`) are
Arjun's.

| Session | Dates | What I asked | How I used the output |
|---|---|---|---|
| `78c8337e` | 09-30 | "Read through Readme, instructions, rubric, all files, then get back to me before you start planning"; how to split tasks to avoid merge conflicts; T0 branch; T3 READMEs; "make this a rule before every push" | Team split and merge order, which I proposed to Arjun; READMEs I reviewed and corrected before committing; the pre-push compliance checklist |
| `89259c1a` | 09-30 | Whether new chats follow my session-log rules; first-time setup | Learned that rules must live in memory or CLAUDE.md, because chats don't share history |
| `1236bbe6` | 10-01 → 10-05 | Implement T4 phase 1 test-first; summarise Arjun's phase 2 and plan phase 3; testing plans; many manual-testing questions | Phase 1 and phase 3 code and tests; the commit-timing fix; manual test plans I ran myself |
| `bde9947c` | 10-04 → 10-05 | T8 design (Elephant + Goldfish), then implement my half V0–V9 | The design doc; 74 integration tests; the image library and picker |
| `f6122621` | 10-05 | `/insights` on my usage, then turning its suggestions into CLAUDE.md sections, skills and hooks | My personal skills and hooks (see §4) |
| `52a25f37` | 10-05 | Separate T6/T7 branches; brainstorm types; build ordering; design T6 games and run `/qa-pass` | Ordering end to end; two sample games |
| `a05e4b3f`, `080aff2b` | 10-05 → 10-06 | Fix the player socket-reconnect race; T9 "bold and unique" theming end to end; this document | The Riso Press theme; the T10 draft, which I edited |

**Where it helped:**
- **Reading a codebase I didn't write.** The first-day "read everything, then come back
  before planning" prompt gave me a map of the code in about 30 minutes. The task split it
  suggested (by layer, ordered to minimise merge conflicts) is the one we used. Our merge
  conflicts were mostly in shared docs, not code.
- **Test-first volume.** I would not have written 74 T8 integration tests, or the ordering
  scoring DP with hand-checked examples, at this pace by myself. Claude wrote failing tests
  from the spec, then code to pass them.
- **Fresh-context reviews.** Subagent Goldfish tests, the `mean-review` skill and the T6 fact
  check found problems I had stopped seeing (see §2).
- **Finding bugs outside the task**, such as the commit-after-response race during T4 phase 1.
  I fixed it on its own branch, `fix/get-db-commit-timing`: 66 of 100 reads were stale before
  the fix and 0 after.

**Where it fell short:**
- **It ignored repo conventions until told.** It started the T8 design as an online doc. In T9
  it added a CI job even though R2 forbids pipeline changes. My pre-push compliance check
  caught that, and I reverted it before pushing.
- **Green tests weren't enough.** My manual testing found bugs the AI-written tests missed:
  - the admin "Open Host app" link didn't sign you in;
  - the course edit buttons appeared to do nothing, because the form opened off-screen.

  In T9, only looking at screenshots caught:
  - an over-bright Night sidebar;
  - one-pixel slivers on zero-count result bars;
  - a canvas border that skewed hotspot click positions.

  The test suite passed throughout.
- **AI-written content needed checking.** Two T6 answer keys were defensible either way. The
  fresh fact checker caught them, not the session that wrote them.
- **It took instructions too literally or too loosely.** "A new branch for my t6 and t7" got one
  branch instead of two. My first `/qa-pass` request on T9 was interrupted and never ran, so T9
  has screenshot review and e2e tests but no separate QA report.
- **Long sessions hit the context limit.** The T9 session was compacted several times. Each
  summary lost detail, and I sometimes had to re-check facts it had already established. A
  few responses were cut off mid-stream and had to be resumed.

## 4. Best Practices Learned

Most of what I learned this project was about **using Claude Code deliberately**: setting up
the context, rules and guardrails so its output was right the first time, rather than just
prompting it.

- **Bottom-up README context beats re-reading source.** Reading code once to write the READMEs
  set up every later session. Design and Goldfish subagents got "load these READMEs" instead
  of "read the repo". That was faster, cheaper and more consistent. The catch is that READMEs
  are code too: they go stale, so I update them in the same branch as the change.
- **Skills turn a repeated workflow into one command.** I used the repo's skills
  (`design-discussion`, `write-spec`, `goldfish-test`, `mean-review`). After `/insights`
  showed me which requests I kept retyping, I wrote my own in `~/.claude/skills/`:
  - `qa-pass`: independent browser QA from both `localhost` and `127.0.0.1`, with a failing
    e2e test before each fix. Testing both origins is there to catch websocket CORS
    mismatches.
  - `lecture`: README → SPEC → test-first → goldfish → commit.
  - `parallel-task`: one worktree plus an isolated Docker stack per task, so sessions don't
    collide.

  `qa-pass` is user-invoked only, so the model can't start it on its own. That is deliberate:
  it controls when a long, expensive pass runs.
- **Hooks enforce what prompts can only ask for.** "Always check the branch" in a prompt gets
  forgotten, and a hook doesn't forget. My `PreToolUse` hook prints the current branch on
  every `git add/commit/push`, and **blocks** `git add -A` / `git add .` outright. This
  mattered because several sessions shared one checkout and switched branches under each
  other.

  The project's logging hook writes `ai_log/` with no effort from me. My `context_reminder`
  hook tells me when to `/compact` or `/clear`: at 150k and 225k tokens, after a commit or
  push, and when the branch changes.
- **Memory is for preferences that should survive sessions, and scope matters.** I asked
  "Do you and all new chats follow the vzhou2.md session rules?" and learned they don't unless
  the rule lives somewhere loaded. So the session-log rule, the design-docs-in-repo rule and
  the pre-push compliance checklist became memory files.

  I kept the compliance check in **my own** memory, not in the repo's `.claude/rules`, because
  a repo rule would have imposed it on Arjun's sessions too. It earned its place in T9 by
  catching the CI change before it was pushed.
- **Context and usage management.**
  - Chats don't remember each other ("Retain context and memory from t4 chat session" doesn't
    do anything). Continuity comes from memory, CLAUDE.md, READMEs, the session log and git
    history.
  - I set `autoCompactWindow` to 300k and the default effort to medium, so routine work stays
    cheap. I delegate big reads and fresh-eyes reviews to subagents, so their output doesn't
    fill my main context.
  - I start new sessions at natural breaks (a push), instead of letting one session run until
    it is compacted three times.
- **Workflow efficiency.**
  - One branch per task, named for the task. Unrelated fixes go on their own branch (the
    commit-timing and socket-reconnect fixes).
  - Stacked branches when a task depends on unmerged work (T7 on T8). Atomic commits, with
    files staged explicitly.
  - A push ends a session and gets a session-log entry, which is why the log below exists.
  - Give Claude the acceptance criteria up front (test-first, coverage target, "pause when you
    need me to manually test"), and do the manual testing yourself: it found what the tests
    didn't.
- **Testing strategy.**
  - Integration tests run against the real stack (MySQL, Redis, sockets), not mocks. They
    include access-control and error cases, not just happy paths.
  - Playwright e2e tests drive host and player together.
  - For UI work, review screenshots: about half the T9 bugs were only visible in a
    screenshot.
  - Coverage of changed lines tells you about the work you just did. Overall coverage tells you
    about the whole project. I report both.

## Session Log

### Branch: `chore/t0-logging-verify-vincent`

- **2026-09-30, 16:53–17:25** — Read the README, instructions, rubric and full codebase; agreed on the team task split (Arjun: host capabilities, canvas type, canvas images; Vincent: admin-first restructure, course–game attachment, second question type, image upload, theming) and an ordering to minimize merge conflicts; verified AI session logging and pushed this branch (T0).

### Branch: `docs/t3-context-vincent`

- **2026-09-30, 21:10–21:40** — Created this branch from `origin/main` (now including Arjun's merged READMEs), set up this session log, wrote and verified T3 context READMEs for `backend/app/{models,schemas,common}` and `frontend/admin/src/{pages,components,lib}`, and rolled them up into `backend/app/`, `backend/` and `frontend/admin/src/` READMEs.
- **2026-09-30, 21:38–21:42** — Completed the remaining T3 roll-up READMEs (`frontend/host/src/`, `frontend/player/src/`, `frontend/`) from Arjun's child READMEs, noting that his error-message fix is now on `main`.
- **2026-09-30, 21:42–21:46** — Merged `main` into this branch and verified every README against the current code; corrected stale error-parsing notes in the host/player `lib` READMEs and roll-ups, the host pages auto-advance description, and the backend JWT-key warning note.
- **2026-09-30, 21:46–21:58** — Audited both pushed branches against the instructions and rubric, adopted a pre-push compliance check, and prepared this branch's merge request for Arjun.

### Branch: `feat/t4-ui-restructuring`

- **2026-10-01, 15:20–15:50** — Deleted the merged local branches, then implemented T4 phase 1 test-first: migration 004 (`games.course_id` with backfill), course-required game create/import, the both-grants host rule, the room/game course match, the admin grant and course-move 409s, the admin Games page course picker, 45 integration tests (100% coverage of changed backend lines), and README/design-doc updates; found a pre-existing commit-after-response race to fix separately.

### Branch: `fix/get-db-commit-timing`

- **2026-10-02, 19:35–19:52** — Summarized Arjun's merged T4 phase 2 and planned phase 3; then fixed the commit-after-response race test-first (`DbSession` declares `get_db` with `scope="function"` so the commit lands before the response), removed phase 2's interim handler commits, and added a write-then-read regression test (66/100 stale reads before, 0 after; full suite 130 passed).

### Branch: `feat/t4_ui_restructuring_phase_3`

- **2026-10-02, 19:52–20:37** — Implemented T4 phase 3 on top of the commit-timing fix: admin game/question/import/export routes now delegate to `content_service`, new `GET /admin/courses/{id}/access`, `RequireAdmin` role check, admin-first sidebar, course detail page, Games course filter and course move, course-grouped game-access picker, and the admin `HotspotEditor` copy (T7 stage D); 13 new integration tests (full suite 143 passed, 100% of changed backend lines covered), one hotspot test re-planted via MySQL, READMEs and design doc §6.5.1 updated.
- **2026-10-04, 21:25 – 2026-10-05, 14:40** — Manually tested T4 end to end on a freshly restarted stack with seeded QA courses, users and games; fixed two admin-app bugs it found (the "Open Host app" link now opens `/host/home` signed in, and the course/game edit forms scroll into view), cleaned leftover test games and courses from the local database, and re-ran the full suite (143 integration and 76 unit tests passing).

### Branch: `feat/t8-image-support`

- **2026-10-04, 21:30–22:57** — Merged T4 phase 3 into a new T8 branch, then wrote the T8 image-support design (`docs/plans/t8-image-support.md`): first draft, the remaining design decisions, revisions after a Goldfish test, and a test-first implementation order split by owner.
- **2026-10-05, 14:45–19:18** — Implemented my half of T8 test-first (steps V0–V9): migration 005 (`images`, `questions.prompt_image_id`), Pillow-validated uploads with metadata stripping and per-course duplicate reuse, prompt/option image fields with a course-aware existence check replacing the dev-image stand-in, image listing with reference counts, delete protection, upload-and-repoint replace, image copy on game move, version 2 export/import, and the admin/host `ImagePicker` and image library page; 74 new integration tests (full suite 217 passed), fixed a duplicate-upload deadlock found in testing, and passed a manual test on the nginx build.

### Branch: `feat/t7-ordering`

- **2026-10-05, 20:03–21:15** — Built the team's second T7 type, **ordering** (tap items into sequence, partial credit by longest in-order run), end to end on a branch stacked on the unmerged T8 and commit-timing work: design in a fresh subagent (corrected the brief's COMPLETENESS-as-partial-credit premise), Goldfish-tested and revised, then test-first through validation, scoring, socket results, engine mirror and simulator, export/import, report, a new Playwright e2e harness, player/host UIs and host + admin editors; mean-review fixes, a two-origin browser QA pass (no bugs), and 158 unit / 276 integration / 5 e2e tests green. Also split T6/T7 into their own branches and pruned stale local branches.

### Branch: `content/t6-games-vincent`

- **2026-10-05, 21:45–22:45** — Measured T7 coverage (97.7% of changed backend lines, 79.2% overall), then created my two T6 games: **Reading the Data** (classroom, intro statistics) and **Food Fight** (party). Each has every question type including hotspot and ordering, both grading modes, and self-drawn images in a version 2 bundle. Followed a plan with a fresh-subagent fact check that caught two arguable answer keys and unfair hotspot rings, built the games through the API, added 9 integration tests, and ran a two-origin browser QA (both games played end to end, no bugs in the content). Documented a pre-existing player socket-reconnect race found during QA.

### Branch: `feat/t9-theming`

- **2026-10-06, 19:45–21:05** — Designed and built T9 theming end to end. The visual identity is "Riso Press": a Paper light theme and a Night dark theme, with ink outlines, hard offset shadows, riso option inks with halftone dots, rubber-stamp verdicts and a ticket-stub room code. Took 38 before screenshots, wrote the design doc and revised it after a fresh-subagent Goldfish test, then wrote failing token, contrast and light/dark e2e tests first. Built the token layer, the pre-paint theme script, the toggle and the primitives in all three apps, then migrated every player, host and admin screen, including the T7 hotspot and ordering canvases and editors, which now repaint on toggle. The screenshot review caught an over-bright Night admin sidebar, result-bar slivers and an uneven histogram baseline. The mean-review caught canvas borders that skewed the editor's click position. Fixed all of these, plus literal `\u00b7` escapes in admin JSX, and dropped a planned CI job before pushing because R2 forbids pipeline changes. Results: 116 token/contrast unit tests, 577 backend unit and integration tests, and 18 e2e tests green; 76 after screenshots in `docs/ui/t9/`.
