# Arjun Kaneriya (kaneriya)

Individual document for T10. My share of the team split: the host-side restructuring (T4 phase 2),
the canvas-based question type (T7 hotspot) and, later, canvas images. My partner Vincent Zhou
(`vzhou2`) owns the admin-first restructuring (T4 phases 1 and 3), the second question type, image
upload (T8) and theming (T9).

## Repository and Codebase Organization

Buzzer is a FastAPI backend plus three browser apps, run together with Docker Compose (MySQL for
durable data, Redis for live game state).

**Backend (`backend/app/`).** It is layered, and the layers have different jobs:

- **`routers/`** is the REST layer: parse the request, run auth and role checks as FastAPI
  dependencies, shape the response. The intent is that routers stay thin. `host.py`, which I wrote
  in T4 phase 2, mostly is: its game and question handlers hand off to
  `services/content_service.py`, and only the small roster handlers query directly. `admin.py` still
  carries most of its logic inline until T4 phase 3 moves it into the same service, and
  `game.py` still holds the guest-merge logic itself.
- **`services/`** holds the business logic. The convention is that a service only `flush()`es and
  the caller owns the commit, so a request either commits as a whole or rolls back. There are three
  deliberate exceptions. On the socket path, `game_service.start_game` and
  `game_service.complete_game` commit themselves, because concurrent socket handlers in separate
  database sessions must see the new session status straight away; the startup `bootstrap` also
  commits its own work.
- **`websocket/gateway.py`** runs the live game over Socket.io: joining, advancing, answering,
  locking, timers.
- **`schemas/`** are the Pydantic request/response models; `schemas/admin.py` is where question
  validation lives, including the single set of hotspot checkers that both validation and scoring
  use.
- **`models/`** are the SQLAlchemy tables. `questions.config` and `answer_data` are schemaless
  JSON, which is why a new question type like hotspot needed no migration.

**Frontends (`frontend/`).** Host (the big screen), player (phones) and admin are three independent
Vite + React + TypeScript apps that share no code: primitives and the API client are copied into
each. That duplication is deliberate rather than an accident we never cleaned up. T4 considered a
shared frontend package and rejected it as too risky (Vite, tsconfig, CI and nginx changes across
three apps), choosing to port components and accept the extra copy instead
([t4-ui-restructuring.md, rejected alternatives](plans/t4-ui-restructuring.md)). The cost is
real and documented: the hotspot canvas layout rule now exists in the player's `HotspotCanvas`
and the host's `HotspotView`, and the host components README says to change both together.

*Screenshots: before/after screenshots in `docs/ui/`, including the hotspot editor and play flow,
will be added and referenced here once T8 and T9 land.*

**Tests and docs.** `tests/integration/` runs against the real Docker stack over HTTP and
Socket.io (the `docker_stack` fixture); `tests/unit/` covers pure functions such as the hotspot
band maths. Designs live in `docs/plans/`, one spec per feature.

### A game round, end to end

1. **Host advances.** The host app emits `host_advance` over its socket. In
   `gateway._on_host_advance_impl`, the gateway reads the room's phase from Redis, loads the next
   question from MySQL and emits `new_question` to the room. The payload carries the question's
   `config` but not its `answer_data` (fill-in-the-blank only gets its edit-distance tolerance),
   so the answer key never reaches a browser.
2. **Player submits.** The player app emits `submit_answer`. `gateway.on_submit_answer` checks
   that a question is actually open, not locked, matches the active question ID, and hasn't already
   been answered by this player, then validates the answer's shape by question type. A hotspot tap
   must carry `x` and `y` in [0, 1], and only the point is kept.
3. **Scoring happens at submit time.** `game_service.record_answer` calls `calculate_score`, adds a
   `session_scores` row to MySQL, and updates the player's score, the answered set and the answer
   distribution in Redis. For hotspot, the score comes from the aspect-corrected distance between
   the tap and the target: full points inside the inner radius, `points_value × partialFraction`
   inside the outer one, zero beyond. Distance is measured in units of the image's longer side, so
   a radius is a true circle on a non-square image.
4. **Commit, then emit.** The gateway commits before it emits `answer_received` to the player and
   `answer_status` to the host. That ordering is a fix I made (`b43040b`, merged in MR !11).
   Previously the row was committed only when the handler exited, after the emits, so a host that
   advanced within milliseconds of the last answer ran the results query before that row existed:
   on `main` it reproduced as `totalAnswered` one short and that player's points showing 0.
5. **Reveal.** The next `host_advance` (QUESTION → RESULTS) reads the stored scores back and builds
   the reveal. The host gets the answer reveal and the answer distribution (plus, for hotspot,
   every tap with its band, capped at 500). Each player gets a private `question_results` with
   only their own points, total, rank and, for hotspot, their own band (`yourBand`). Nobody
   sees another player's name or score.
6. **Game over.** After the last question, `game_service.complete_game` marks the session
   `COMPLETED` and commits. The scores were already in MySQL from step 3; Redis keeps the live
   state a while longer for reconnects.

### The context files I wrote, and what writing them taught me

For T3 I wrote the bottom-up `README.md` context files for nine directories on 2026-09-30:
[`backend/app/routers/`](../backend/app/routers/README.md),
[`backend/app/services/`](../backend/app/services/README.md),
[`backend/app/websocket/`](../backend/app/websocket/README.md), and the `pages/`, `components/`
and `lib/` directories of both [`frontend/host/src/`](../frontend/host/src/README.md) and
[`frontend/player/src/`](../frontend/player/src/README.md). Vincent wrote the admin, models,
schemas and common READMEs and the roll-ups. Later I added
[`frontend/dev-images/README.md`](../frontend/dev-images/README.md) for the T7 dev image route.

Writing them meant reading every file, and each one ended with a "Gotchas found while reading"
section. Three of those gotchas changed what we did:

- **The error-shape mismatch.** The host `lib/` README (`05a4db3`) recorded that `api.ts` read
  `body.detail`, while the backend sends `{"error", "message"}` for application errors and a
  `detail` *array* for validation errors. Users saw `HTTP 409` or `[object Object]` instead of the
  server's message. The same bug was in all three apps, so it became its own branch and MR,
  `fix/frontend-error-messages` (`b2449e5`, `883deb1`, `78e4407`).
- **One token for three apps.** The player `lib/` README (`117ff28`) recorded that host, player
  and admin all use the same `localStorage` key on one origin. On the same browser, joining as a
  guest signs out the host, and the player's "Play Again" removes the host's token.
- **Copies drift.** Writing the READMEs side by side showed how far the copied primitives and API
  clients had already drifted (player button sizing, `TimerBar` props, which API methods exist).
  Since then, the READMEs for copied code name the other copies (for example the host components
  README's note that hotspot drawing exists in both apps), and the T4 phase 2 port of the question
  editor opens with a comment listing what changed and asking for fixes to be kept in sync.

The bigger lesson was that a README is a forcing function. I could not write "Depended on by" or
"Gotchas" without actually tracing the code, and the bugs above were found that way, not by
running anything.

## Design Process (Elephant/Goldfish)

I followed T3's Elephant/Goldfish process for both of my designs, using the repo's skills
(`design-discussion`, `write-spec`, `goldfish-test`). The two specs are
[`docs/plans/t4-ui-restructuring.md`](plans/t4-ui-restructuring.md) (with Vincent; I own phase 2)
and [`docs/plans/t7-hotspot.md`](plans/t7-hotspot.md).

**T4: what the Elephant produced and what the Goldfish caught.** The Elephant session
(`ai_log/2026-10-01_12-01-13_2289c0ca.md` through `12-12-31`) took the T4 task, loaded only the
relevant READMEs, discussed the design with me without writing code, and produced the spec
(first committed in `9a20587`, "pending goldfish"). A fresh Goldfish session
(`ai_log/2026-10-01_12-23-41_8732fdd2.md`) then read only the spec and the context hierarchy.
Its findings, as recorded in my decisions (`ai_log/2026-10-01_12-40-33_8732fdd2.md`) and the
revision commit, included:

- **Roster scoping:** a host roster `PATCH` didn't require the roster row to belong to the course
  in the URL, a cross-course hole.
- **D6 delete rules:** what happens to a session with no host, and that deleting a game must be a
  409 while any session is live, for admins too.
- **D8 update semantics:** exactly which fields an update merges onto the stored question, and
  that an explicit `null` is a 422 rather than "clear this field".
- **The 422 shape:** errors raised inside a service had to render as the existing
  `VALIDATION_ERROR` body, which led to the new `RequestBodyInvalidError`.

All of these were fixed in the spec in one revision commit, `2e07aa4` ("Revise T4 design after
goldfish test: close cross-course roster hole, pin D6/D8 semantics", 12:40 on 2026-10-01), before
the first T4 implementation commit (`c6b52c2`, 15:28 the same day); the spec's status line records
the revision. Every one of these was a rule the Elephant session and I had left implicit because
we had just discussed the surrounding design. The Goldfish had only the document, so wherever the
document was silent, it had to ask.

**T7: what the Goldfish revealed about time.** The T7 Goldfish
(`ai_log/2026-10-01_13-17-12_c7123e9d.md`) found ten gaps. Item 4 was that image loading eats
into answer time: answer time is measured from when the question page mounts, before the image
has loaded; a class of 150 fetches the image at the same moment; and the spec only discussed late
joiners. It posed a choice: "Decide whether
timing starts when the image is drawn, or record the unfairness as accepted", plus a request for
cache headers. Starting the timer when the image is drawn turned out to be unworkable here. The
authoritative timer is server-side (the gateway's timer task locks the question), and a
client-reported "image ready" time would be trivially gameable. So the revision (`ab54cb0`) took
neither option as written. The spec now accepts load time *with a justification* (decision H11):
the server owns the timer, T8's image size cap keeps loads short, the player starts fetching the
image the moment `new_question` arrives, and T8 is required to send
`Cache-Control: private, max-age=31536000, immutable` (contract C3) so repeat loads come from the
browser cache. The same Goldfish also found that labelling a player's hotspot result from points
breaks when `points_value` is 0 or `partialFraction` is 0 or 1, which is why the server now sends
each player their own band.

**Did it change how I implemented?** Yes, in one specific way. Each spec gained implementation
addenda: T4 §6.1.9 (phase 1, Vincent) and §6.2.5 (phase 2, mine), and T7 §13 and §13.1. When
implementation hit something the spec got wrong or left open, the rule was to stop and decide,
then write the decision into the addendum before coding it. In phase 2, for example, the plan
surfaced that D8's "seven fields" miscounted (`QuestionCreate` has eight; `order_index` is the one
excluded). That became row (a) of §6.2.5 instead of a silent deviation. So the surprises of
implementation became recorded decisions that Vincent could read, rather than drift between
the spec and the code. It also meant implementation started with tests already decided: both
specs list their tests by number (T4 §6.4, T7 §10), so testability was settled at design time.

## AI Tools Used

The only AI tool I used for this project was **Claude Code**, for planning, repository
navigation and implementation. Every session is logged automatically to `ai_log/`. Mine are the
sessions `c57d751e`, `2289c0ca`, `8732fdd2`, `cfcfbdde` and `c7123e9d`; `78c8337e`,
`89259c1a` and `1236bbe6` are Vincent's.

| Phase | Sessions (`ai_log/`) | What I asked for, and what I did with it |
|---|---|---|
| Orientation and T3 READMEs | `2026-09-30_14-32-14` to `15-07-42_c57d751e` | Walked through `docs/realtime.md`'s answer path, then wrote one README per directory, reading every file. I reviewed and approved each before moving on. |
| Early fixes | `2026-09-30_18-41-16` to `20-52-46_c57d751e` | The frontend error-message fix found while writing READMEs, and `fix/sim-stale-answers`. |
| T4 design and goldfish | `2026-10-01_12-01-13` to `12-12-31_2289c0ca`; `12-23-41`, `12-40-33_8732fdd2` | Design discussion, spec, fresh-session goldfish test, revision. |
| T7 design and goldfish | `2026-10-01_13-02-39`, `13-06-19_cfcfbdde`; `13-09-24` to `13-58-28_c7123e9d` | Same process for the hotspot type. |
| T7 stage A | `2026-10-01_14-07-25` to `15-57-35_c7123e9d` | Planned in numbered commits, implemented one at a time with a stop for my review after each. |
| T4 phase 2 | `2026-10-02_13-40-37` to `15-25-18_c7123e9d` | Plan, decisions, backend, tests, frontend. |
| Fixes and merges | `2026-10-02_16-16-56` to `16-48-44_c7123e9d` | The guest-merge fix, resolving its merge with phase 2, a full test run. |

**How I worked with it.** I gave it standing rules and held it to them: the spec is
authoritative, and where code and spec disagree it must stop and ask rather than improvise;
bugs found along the way go on their own branch and MR from `main`; no commit or push without my
say-so; CI (ruff and `tsc`) must pass. It planned, I decided, it implemented in small commits, I
reviewed each.

**Where it helped.** Mostly in finding problems I would not have found myself, in time to fix
them cheaply:

- The T7 Goldfish's points-0 / `partialFraction` label bug and its crash-on-bad-data finding
  (`2026-10-01_13-17-12_c7123e9d.md`).
- A pre-existing crash: a `NaN` in a request body returned 500 instead of 422
  (`2026-10-01_14-14-52_c7123e9d.md`), fixed on its own branch (`252b97e`, MR !10).
- The answer-commit race behind the commit-before-emit fix (`b43040b`, MR !11).
- During phase 2 it stopped mid-task because the code and the spec disagreed: FastAPI's `get_db`
  commits *after* the response is sent, so a client reading straight after a write saw stale data
  (a probe measured 111 of 200 reads stale, `2026-10-02_15-12-05_c7123e9d.md`). The interim fix,
  committing in each host handler before responding (`81dcd43`), took that to 0 of 200.
- While reviewing phase 2 it found that a host's guest merge could reattribute a guest's answers
  in *other hosts'* sessions. That got its own branch with tests that fail against the old handler
  (`6f1ac65`, `e22aed9`, MR !15).

**Where it fell short.** It was confidently wrong often enough that I treated every output as a
draft to verify:

- It got facts about its own spec wrong: D8's "seven fields" was a miscount, caught in phase 2
  planning (`2026-10-02_13-44-30_c7123e9d.md`).
- Its throwaway scripts had bugs of their own, for example a module loader problem in an ad-hoc
  check (`2026-10-01_15-18-21_c7123e9d.md`), so a failing check first had to be ruled out as a
  bug in the check itself.
- It reported 138 unit tests passing (`2026-10-02_16-48-44_c7123e9d.md`) when there were 69: a
  copy into the container had nested a second copy, so every test ran twice. It caught and
  corrected this itself in a later session, but only because a later run gave a different number.
- It accepts explanations too readily. When I reported a simulator bug, I had to tell it to treat
  my description of the cause as "an unverified theory, not a fact" and confirm it from the logs
  first (`2026-09-30_20-49-50_c57d751e.md`).

## Best Practices Learned

**Small MRs, merged often.** Between 2026-09-30 and 2026-10-02 the team merged 14 MRs (!1 to
!15), most of them one fix or one phase. A bug found mid-feature went on its own branch from
`main` (the NaN handler, commit-before-emit, guest merge) instead of riding along in a feature MR.
Each was reviewable on its own, and merge conflicts stayed small. The one real conflict, my guest-merge fix
against phase 2's new access dependency, was confined to one handler.

**Review by someone who didn't write it, and approvals that mean the current code.** Every MR was
approved by the teammate who didn't author it (`instructions.md`, merge request approval).
Approvals also reset on push, which I saw directly: my push to MR !15 reset Vincent's approval,
and he re-approved the new code before it merged. An approval is for a specific version of the
code, not for the branch.

**READMEs as a forcing function.** Writing the context files forced me to read code I would
otherwise have skimmed, and that reading found real bugs (above) before anyone ran anything. The
READMEs then became the context that the design and goldfish sessions loaded instead of raw
source, so their accuracy mattered beyond T3.

**Decide testability at design time.** Both specs list their tests before any code exists, with
the endpoint each test calls and what it needs. That surfaced design gaps early (a test you can't
write usually means an undecided behaviour), and it made "done" concrete.

**Know where your transaction ends.** The two most subtle bugs I hit were both about commit
timing: answers committed after the socket emit that announced them, and `get_db` committing after
the HTTP response. In each case the code looked right line by line, and the bug was in *when* the
data became visible to the next reader. I now check where a transaction commits relative to
anything that tells a client "done".

**AI output is a draft to verify, not an answer to trust.** The AI was most useful when I made
verification part of the workflow: plans before code, a stop at every commit, tests run against
the live stack, and an explicit rule to stop at disagreements instead of guessing. The mistakes
listed above were all caught that way, by checking rather than trusting.
