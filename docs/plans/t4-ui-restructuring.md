# T4 — UI Restructuring: host capabilities, course-specific games, admin-first admin app

Status: **agreed design, revised after goldfish test** (cross-course roster rule, D6/D8
semantics, named schemas, per-phase tests). **Phase 1 implemented** (branch
`feat/t4-ui-restructuring`); see §6.1.9 for the details it settled. Owners: Vincent Zhou (phases 1 and 3), Arjun
Kaneriya (phase 2). Read with the context hierarchy: `backend/app/README.md`,
`frontend/README.md`, and the per-directory READMEs they link.

## 1. Problem

Today every content-management capability — rosters, games, questions, session downloads — is
reachable only through `/api/admin/*` (every endpoint `require_admin`) and the Admin app. Hosts
(users with `HOST` in `user_course_access`) can only open rooms and run games. Games are global:
`games` has no `course_id`, so any host granted a game can run it in any course they host.

T4 requires:

- **Host app gains:** (a) download a completed session's HTML summary; (b) download a completed
  session's per-player scores CSV; (c) view/update the roster of any course they have HOST access
  to (add/deactivate via CSV); (d) create games and add/edit/delete/reorder questions and their
  scoring; (e) games attach to one course at creation and are reachable only by that course's
  hosts and players.
- **Admin app:** admin-first layout (user accounts, course creation, course/game access grants
  primary); all host and player actions still available but secondary.
- **Hard constraint:** integrate with the existing role/permission system; no bypassed checks.

## 2. The existing permission system (what we build on)

Three layers, all reused; no new roles are added.

| Layer | Storage | Checked by |
|---|---|---|
| Global role `ADMIN \| USER \| GUEST` | `users.role` | `common/dependencies.py`: `require_admin`, `require_user` (re-reads the DB each request) |
| Per-course role `HOST \| PLAYER` | `user_course_access` | `game_service.assert_host_can_use_course` (hosts); `game_service.authorise_player` (players: active roster row by netid, or PLAYER/HOST access) |
| Per-game grant | `user_game_access` | `game_service.assert_host_can_use_game` |

Admins bypass the per-course and per-game layers everywhere; that stays true.

## 3. Technical plan (summary)

1. Add `games.course_id` (nullable FK). The API requires it on every create/import.
2. **Effective host access to a game = a `user_game_access` grant AND HOST on `game.course_id`.**
   Admins bypass. A host who creates a game is auto-granted it.
3. **Invariant: a session's course equals its game's course at room creation.** `create_room`
   enforces it for everyone, admins included. Player access then follows from the unchanged
   roster check in `authorise_player`.
4. New router `backend/app/routers/host.py` at `/api/host/*` (`require_user` + per-resource
   course/game checks). `/api/admin/*` stays `require_admin`, unchanged in its gating.
5. Game/question business logic moves out of `routers/admin.py` into a new
   `services/content_service.py`, called by both routers.
6. Shared, course-scoped FastAPI dependencies are added to `common/dependencies.py`
   (`common/README.md`: "this is where any new role or permission check belongs").
7. Host app gains a management area; Admin app nav is regrouped admin-first.

## 4. Decisions made (with rationale)

### D1. Both grants required (course HOST + game grant)

The rubric only requires access ⊆ course members; "course HOST implies every game in the course"
would also comply. We chose both-grants because (a) it keeps the admin's "grant game access"
meaningful — the admin requirements name it explicitly; (b) revoking a user's course HOST role
silently neutralises their game grants for that course with no cleanup code; (c) auto-granting the
creator removes the main friction (a host never has to ask an admin for their own game).
Co-hosts of the same course still need an admin grant to see each other's games — accepted.

### D2. Guests keep joining course-specific games

`authorise_player` admits any `GUEST` token to any room. We keep that. Rationale: a guest can
join only while a live room is open, and that room can be opened only by an authorised host of
the game's course (D1 + the invariant in §3.3); guest scores stay outside course records until a
host explicitly merges the guest into a netid. Removing guests would break an existing feature
and the simulation tooling (`scripts/simulate_players.py`, guest-based integration tests). We do
**not** claim the room code is a security boundary — it is shown on a projector as a QR code.

### D3. Legacy games become "unassigned" (NULL), admin fixes them

Migration 004 backfills `course_id` only when unambiguous (§6.1.1); everything else is NULL.
Unassigned games are visible and runnable only after an admin assigns a course. Hosts never see
them: they fail D1's course check. On a fresh clone there are none (seed/test scripts pass
`course_id`), so this is a cleanup path for existing dev databases, not a grader-facing flow.

### D4. One invariant, no admin exception

`create_room` rejects (409) when the game is unassigned or `game.course_id != body.course_id`,
for admins too. An admin who wants to run an unassigned game assigns it a course first. The
invariant is enforced **at room creation**; completed sessions keep the `course_id` they were
played in even if an admin later moves the game (see D5).

### D5. Who can change a game's course

Hosts: never (`course_id` is not in the host update schema; sending it is a 422). Admins: via
`PUT /api/admin/games/{id}`, refused (409) while the game has a live session (§6.2.3).
Historical sessions are not rewritten.

### D6. Deleting things that have history

- **Questions with recorded answers cannot be deleted** (409 "Question has recorded answers").
  Today this is a DB FK failure surfaced as a 500 (`models/README.md`). Deleting scores instead
  would silently rewrite completed sessions' totals.
- **Game deletion — everyone, admins included:** refused (409 "This game has a live session") while
  the game has any live session (D7 definition). An admin who needs the game gone deletes the live
  session first through the existing `DELETE /api/game/sessions/{id}`, then the game. Game
  deletion therefore never pulls a running room out from under connected sockets. (Deleting a live
  *session* also doesn't notify its sockets; that gap predates T4, see §7.)
- **Game deletion — admin, otherwise:** deletes all its sessions and scores (existing behaviour)
  **and now also clears each session's Redis state** (`state_service.delete_room_state`).
  Today the MySQL rows go but `room:{code}` stays in Redis as `LOBBY` for up to 90 minutes and
  counts toward `MAX_ROOMS`; `session:{id}:*` never expires (`backend/app/README.md` gotchas, and
  T5's "both datastores" warning).
- **Game deletion — host (non-ADMIN), additionally:** refused (409) if any of the game's sessions
  has `host_user_id` not equal to the actor, **including `host_user_id IS NULL`**. A session with
  no recorded host is not the actor's data. Implement the query as
  `host_user_id IS NULL OR host_user_id != :actor`, because a bare SQL `!=` skips NULLs. Otherwise
  as admin. A successful host delete permanently removes the student scores of the actor's own
  sessions of that game (§7); the host UI confirms with the session count first (§6.3).

### D7. No edits to a game's questions while it is live

Create/update/delete/reorder question → 409 while the game has a **live session**. "Live" means
MySQL `status IN (LOBBY, IN_PROGRESS)` **and** the `room:{code}` key still exists in Redis. The
Redis condition matters: a room that is never started keeps `status=LOBBY` in MySQL forever after
its 90-minute Redis TTL lapses, and a MySQL-only check would lock that game permanently.
Applies to admins too (scoring a running game against edited questions is wrong for anyone).

### D8. Question updates are re-validated

`QuestionUpdate` has no structural validation (`schemas/README.md`), so a PUT can store a
multiple-choice question with one option or mismatched `answer_points`, which breaks scoring.
Hosts make this far more likely. `content_service.update_question` merges the patch onto the
stored question and validates the **merged** result with `QuestionCreate` (422 on failure).
This tightens admin behaviour too once phase 3 switches the admin router over.

- **Merge scope:** exactly `QuestionCreate`'s seven fields: `type`, `grading_type`, `prompt`,
  `config`, `answer_data`, `time_limit_seconds`, `points_value`. Build the base dict from those
  columns of the stored row, never from the ORM object wholesale (`QuestionCreate` is
  `extra="forbid"`, and `id`/`game_id`/`order_index` would be rejected). Overlay only the fields
  present in the request (`patch.model_dump(exclude_unset=True)`).
- **Explicit nulls are 422.** A field sent as `null` is rejected, not treated as "keep" or
  "clear". Checked before the merge, reported against that field.
- **Error type:** the service raises a new `RequestBodyInvalidError(errors: list[dict])` from
  `common/exceptions.py`, never a FastAPI exception. It is rendered by its own handler as the
  established 422 body `{"error": "VALIDATION_ERROR", "detail": [ {loc, msg, type, …}, … ]}`,
  with `detail` taken from the caught `pydantic.ValidationError.errors()` and passed through
  `jsonable_encoder`, as the existing `RequestValidationError` handler does. The three frontends'
  `errorMessage()` already turn that shape into `field: msg; …`. (`common/exceptions.py` has no
  such type today; only `BuzzerError` and its 401/403/404/409 subclasses exist. `BuzzerError`'s
  `{"error","message"}` body can't carry the per-field array, hence the separate class.)

### D9. Session downloads

Both downloads are allowed for **the session's host (`host_user_id`) or an admin**, matching the
existing CSV endpoint's rule, and only for `status == COMPLETED` (409 otherwise). A host who later
loses course HOST keeps access to sessions they ran (their own data). The host CSV is the
existing raw format (`export_service.build_session_csv`: `Player, Q1..Qn, Total`); the Canvas
options stay admin-only. Note: reports are built from current MySQL questions at download time,
so editing a game after play changes old reports — documented, not fixed (versioning is out of scope).

### D10. Import/export bundles never carry `course_id`

Course IDs are instance-specific. The bundle format stays `version: 1`, unchanged; the target
course is supplied alongside the file on import. Every existing `sample_games/*.json` keeps
importing (T6 requirement).

## 5. Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Open `/api/admin/*` to hosts by loosening `require_admin` to "admin OR authorised host" | Every admin handler would need a correct per-resource check; one miss silently exposes an admin route to hosts. Violates the spirit of "no bypassing access checks" by weakening the one gate that is currently airtight. |
| Course HOST alone grants all games in the course (drop `user_game_access` for hosts) | Makes "admin grants game access" meaningless; see D1. |
| Remove guest access to course-specific games | Breaks an existing feature and the sim tooling; see D2. |
| Force every legacy game to be assigned during the migration (or auto-create a "Legacy" course) | Complexity for no grader-visible benefit; a fake course creates confusing access semantics. See D3. |
| Admins exempt from the course-match invariant | Two rules instead of one; admin-run sessions would land in courses whose players can't see the game. See D4. |
| Delete scores when deleting an answered question | Rewrites completed sessions' totals silently. See D6. |
| Shared frontend package for the question editor / roster wizard | Needs Vite, tsconfig, CI and nginx changes across three apps; too much risk for T4. We port the components instead and accept a third copy (documented in READMEs). |
| Host session downloads allowed for any current HOST of the session's course | Wider than the existing rule with no requirement asking for it; see D9. |
| Store `course_id` inside exported game bundles | Instance-specific IDs; would break cross-instance import. See D10. |

## 6. Detailed implementation

### Phase ownership and merge order

| Phase | Owner | Merges | Contents |
|---|---|---|---|
| **1 — contract** | Vincent | **first**, to `main` | §6.1: migration 004, `course_id` in models/schemas, both-grants check, `create_room` course match, 409 on admin game-grant, fixture/script updates, minimal admin Games page course picker |
| **2 — host backend + host app** | Arjun | after phase 1 | §6.2–6.4: `content_service` (incl. every new 409 and the Redis cleanup), shared dependencies, `/api/host/*`, `/api/game` additions, host frontend |
| **3 — admin switch + admin app** | Vincent | after phase 2 | §6.5: `routers/admin.py` delegates to `content_service`; admin-first frontend |

Phase 2 branches from `main` after phase 1 merges. Phase 3's frontend work may be *developed* in
parallel with phase 2, but merges after it. Each phase updates the READMEs of the directories it
touches (`.claude/rules/context-sync.md`).

### 6.1 Phase 1 — contract (Vincent)

#### 6.1.1 Migration `backend/app/migrations/versions/004_game_course.py`

- Add `games.course_id INT NULL`, FK → `courses.id` **ON DELETE RESTRICT**, plus an index.
  (Courses have no delete endpoint today; RESTRICT keeps it that way safely.)
- Backfill: for each game, if its `game_sessions` rows reference exactly one distinct
  `course_id`, set it; otherwise (no sessions, or several courses) leave NULL.
- Downgrade: drop FK, index, column.

#### 6.1.2 Models — `backend/app/models/game.py`, `course.py`

- `Game.course_id: Mapped[int | None]` with the FK above; `Game.course` relationship;
  `Course.games` back-populating (no ORM cascade — RESTRICT).

#### 6.1.3 Schemas

`backend/app/schemas/admin.py`:
- Split the current `GameCreate` into **`GameMeta`** (`title`, `description`, `max_players` —
  exactly today's fields and bounds, `extra="forbid"`) and **`GameCreate(GameMeta)`** adding
  required `course_id: int` (> 0). `import_game` validates the bundle's `game` block with
  **`GameMeta`** (today it uses `GameCreate`, `routers/admin.py:507`, which would otherwise reject
  every existing bundle).
- `GameUpdate` gains optional `course_id: int | None`.
- `GameResponse` gains `course_id: int | None`.

`backend/app/schemas/game.py`:
- `MyGameItem` gains `course_id: int | None` (the host app filters games by course with it).

#### 6.1.4 Access checks — `backend/app/services/game_service.py`

- `assert_host_can_use_game(db, user, game_id)`:
  - ADMIN: game must exist (404), as today.
  - Otherwise: game must exist (404); a `user_game_access` row must exist; `game.course_id` must
    be non-NULL **and** the user must have `HOST` on it in `user_course_access`. Any failure →
    `ForbiddenError("You do not have access to this game")`. (Same message for every failure: do
    not reveal which grant is missing.)
- `create_room`: after both existing asserts, load the game; if `game.course_id is None` →
  `ConflictError("This game is not assigned to a course; an admin must assign one first")`; if
  `game.course_id != course_id` → `ConflictError("This game belongs to a different course")`.
  Applies to admins. (The existing bare `await db.get(Game, game_id)` line becomes this load.)

#### 6.1.5 `backend/app/routers/game.py` — `GET /game/my-games`

Non-admin query additionally joins `user_course_access` on `(user_id, game.course_id, role='HOST')`
so hosts see exactly the games D1 lets them run. Admin branch unchanged (returns all, including
unassigned; the host app shows unassigned games as not runnable).

#### 6.1.6 `backend/app/routers/admin.py` (minimal, pre-content_service)

- `create_game`: requires `body.course_id`; 404 if the course doesn't exist.
- `update_game`: if `course_id` is present and differs: 404 if the course doesn't exist; 409 if the
  game has a live session (definition in D7 — phase 1 may implement the MySQL+Redis check inline;
  phase 2 moves it into `content_service`).
- `import_game`: accepts a required multipart form field `course_id` alongside `file`; 404 if
  unknown; bundle `game` block validated with `GameMeta`.
- `export_game`: unchanged — never writes `course_id`.
- `grant_game_access`: 409 `ConflictError("User must have HOST access to this game's course first")`
  if the target user is not ADMIN and either the game is unassigned or the user lacks HOST on
  `game.course_id`.

#### 6.1.7 Fixtures and scripts (must ship in the same MR or CI/tests break)

`GameCreate` is `extra="forbid"` and today's callers send no `course_id`:
- `tests/integration/conftest.py` — the game fixture already creates the course first; add
  `"course_id": course_id` to the `POST /api/admin/games` body. No test assertions change.
  (Integration tests create questions before rooms and rooms in the game's own course, so D4/D7
  do not affect them.)
- `scripts/seed_demo.py` — `create_game` takes the course id from `create_course` and sends it.
- `scripts/smoke_test_websocket.py` — add `course_id` to the `/admin/games` body.
- `scripts/simulate_players.py` creates no games; no change.

#### 6.1.8 Minimal admin frontend change

`frontend/admin/src/pages/GamesPage.tsx`: a required course `<select>` on Create and on Import JSON
(sent as the `course_id` form field). Without this the admin app cannot create games between
phases 1 and 3. Full restructuring is phase 3.

#### 6.1.9 Phase 1 as implemented (details the plan left open)

- **`GameUpdate.course_id`:** omitted = keep; a positive id = move; an explicit `null` is a 422
  (unassigning a game is not supported, matching D8's "explicit nulls are 422").
- **`create_room` order:** the course-match 409s run right after the two access asserts and
  *before* the `MAX_ROOMS` count, so a mismatched request is never reported as "too many rooms".
- **Live check (D7) in phase 1:** a private `_has_live_session(db, redis, game_id)` in
  `routers/admin.py`, used only by the admin course move. Phase 2 moves it to
  `content_service.has_live_session` unchanged.
- **Tests:** `tests/integration/test_course_games.py` (every phase-1 row of §6.4, plus the
  §6.1.6 404/409/422 cases and every `sample_games/*.json`). Unassigned games can't be created
  through the API any more, so the `legacy_game` fixture inserts one with `docker compose exec
  mysql`; the "Redis key expired" D7 case deletes `room:{code}` with `docker compose exec redis`.

### 6.2 Phase 2 — backend (Arjun)

#### 6.2.1 Shared dependencies — `backend/app/common/dependencies.py`

Thin FastAPI dependencies wrapping the `game_service` asserts, reading the id from the path:
- `require_course_host(course_id)` → `require_user`; **404 if the course doesn't exist, for
  everyone including admins**; then `assert_host_can_use_course` (403). This confirms course ids
  exist to any signed-in user; accepted, as courses are not secret.
- `require_game_access(game_id)` → `require_user` + `assert_host_can_use_game`.
- `require_session_host(session_id)` → `require_user`; 404 if the session doesn't exist; 403
  unless ADMIN or `session.host_user_id == user.id`. Replaces the four inlined copies in
  `routers/game.py` (delete session, list guests, merge guest, export).

Each returns the `User`. (`common` already imports from `services`; `game_service` imports only
`common.exceptions`, so no import cycle.)

Also in `common/exceptions.py`: `RequestBodyInvalidError` and its handler, registered in
`register_exception_handlers` (D8).

#### 6.2.2 `backend/app/services/content_service.py` (new)

Owns game/question business logic for both routers. Services `flush()`, never commit (`get_db`
commits). Use explicit queries / `selectinload`, never lazy relationship access
(`models/README.md`: `MissingGreenlet`). Moved from `routers/admin.py`: the bleach sanitising of
prompts (allowed tags `b i br u`), import/export bundle building, reorder logic.

Interface (the contract phase 3 depends on; `actor` is the authenticated `User`):

| Function | Behaviour |
|---|---|
| `create_game(db, actor, meta: GameMeta, course_id)` | 404 unknown course. Creates the game; if `actor` is not ADMIN, also inserts `user_game_access(actor, game)` (D1 auto-grant). Returns `Game`. |
| `update_game(db, actor, game_id, patch)` | Applies title/description/max_players. `course_id` handled only when present (admin schema only): 404 unknown course, 409 if live (D5). |
| `delete_game(db, redis, actor, game_id)` | D6. Everyone: 409 if `has_live_session`. Host (non-ADMIN): also 409 if any session has `host_user_id IS NULL OR host_user_id != actor.id`. Then for every session: delete scores, delete session, and `state_service.delete_room_state(redis, room_code, session_id)`; then delete the game. Redis cleanup runs after the MySQL deletes have flushed. |
| `has_live_session(db, redis, game_id) -> bool` | D7 definition (MySQL LOBBY/IN_PROGRESS **and** `room:{code}` exists). |
| `list_questions(db, game_id)` | Ordered by `order_index`. |
| `create_question(db, redis, game_id, body: QuestionCreate)` | 409 if live. Sanitise prompt, append at `max(order_index)+1`. |
| `update_question(db, redis, game_id, question_id, patch: QuestionUpdate)` | 404 if not in game; 409 if live; 422 on any explicit `null`; merge the set fields onto the stored question's seven `QuestionCreate` fields and validate with `QuestionCreate` (`RequestBodyInvalidError` → 422 `VALIDATION_ERROR` on failure, D8); sanitise prompt. |
| `delete_question(db, redis, game_id, question_id)` | 404; 409 if live; 409 if any `session_scores` row references it (D6). Then delete and re-pack remaining `order_index` to 0..n-1. |
| `reorder_questions(db, redis, game_id, order: list[int])` | 409 if live; existing "must be exactly this game's ids" 409. |
| `export_game(db, game_id) -> (filename, bytes)` | Existing bundle format, no `course_id`. |
| `import_game(db, actor, raw: bytes, course_id) -> Game` | Existing validation (format, version 1, `GameMeta`, every question via `QuestionCreate`); 404 unknown course; same auto-grant rule as `create_game`. |

The admin/host routers translate these to HTTP; neither router queries `Game`/`Question` directly
for mutations any more (phase 3 completes this for admin).

#### 6.2.3 New router `backend/app/routers/host.py` (`prefix="/host"`, mounted in `main.py`)

Every endpoint depends on one of the §6.2.1 dependencies; none uses `require_admin`. Admins pass
every check (existing bypass), so the admin can use the host app fully.

| Method & path | Dependency | Calls |
|---|---|---|
| `GET /host/courses/{course_id}/roster` | `require_course_host` | list `CourseRoster` rows → `list[RosterEntryResponse]` (existing schema) |
| `POST /host/courses/{course_id}/roster/import` | `require_course_host` | body `RosterImportPayload` (existing: `rows: list[RosterRowIn]`); `roster_service.process_roster_rows` (deactivates netids not in the upload) → `RosterUploadResult` (existing) |
| `PATCH /host/courses/{course_id}/roster/{roster_id}` | `require_course_host` | body `RosterEntryPatch` (existing; is_active, netid, full_name, email) → `RosterEntryResponse`. **404 unless the row's `course_id` equals the path's `course_id`** (query on both, as admin `patch_roster_entry` already does). Same rule as questions-in-game; without it a HOST of course A could edit course B's roster by id. |
| `GET /host/courses/{course_id}/games` | `require_course_host` | games in the course **the caller can access** (D1; admin: all in course) → `list[HostGameItem]` (new, `schemas/admin.py`: `GameResponse` fields + `session_count: int`, all of the game's sessions in any status, needed by the §6.3 delete confirm) |
| `POST /host/games` | `require_user`, then `assert_host_can_use_course(body.course_id)` | `content_service.create_game` (body: `GameCreate`) |
| `POST /host/games/import` (multipart `file`, `course_id`) | `require_user` + `assert_host_can_use_course` | `content_service.import_game` |
| `GET /host/games/{game_id}` | `require_game_access` | game (`GameResponse`) |
| `PUT /host/games/{game_id}` | `require_game_access` | `content_service.update_game` with **`HostGameUpdate`** (new schema: `GameUpdate` minus `course_id`, `extra="forbid"` → 422 if sent) |
| `DELETE /host/games/{game_id}` | `require_game_access` | `content_service.delete_game` |
| `GET /host/games/{game_id}/export` | `require_game_access` | `content_service.export_game` (attachment) |
| `GET/POST /host/games/{game_id}/questions` | `require_game_access` | list / create |
| `PUT/DELETE /host/games/{game_id}/questions/{question_id}` | `require_game_access` | update / delete |
| `POST /host/games/{game_id}/questions/reorder` | `require_game_access` | reorder |

The multipart roster endpoint (`POST /admin/courses/{id}/roster`) is unused by any UI and is not
mirrored. Course list for hosts is the existing `GET /game/my-courses`.

#### 6.2.4 `backend/app/routers/game.py` additions

- `GET /game/my-sessions` (`require_user`): sessions with `host_user_id == user.id` and
  `status == COMPLETED`, newest first → `list[MySessionItem]` (new, `schemas/game.py`):
  `session_id, room_code, game_title, course_name, course_semester, completed_at, player_count`
  (distinct `session_scores.user_id`).
- `GET /game/sessions/{session_id}/report` (`require_session_host`): 409 unless COMPLETED;
  `report_service.build_session_report` as an HTML attachment.
- `GET /game/sessions/{session_id}/export`: switch to `require_session_host`; add the COMPLETED
  409 (no existing test exercises this endpoint).

#### 6.2.5 Phase 2 implementation decisions (2026-10-02)

Reading the phase 2 code paths against this spec before implementation surfaced the points below.
Each was decided by the owner and **overrides the section it names**.

| # | Point | Decision |
|---|---|---|
| a | D8 says to merge "exactly `QuestionCreate`'s seven fields", but `QuestionCreate` has **eight**: the seven listed plus `order_index`. `QuestionUpdate` also accepts `order_index`, and today's admin handlers write a caller's `order_index` directly, which can create duplicate positions. | D8's count was wrong: the merge scope is the eight fields **minus `order_index`** (the seven D8 lists). `content_service.create_question` always appends at `max(order_index)+1` and ignores any `order_index` sent. `update_question` rejects a patch carrying `order_index` with a 422 (`RequestBodyInvalidError`, `loc: ["body","order_index"]`, message pointing at `POST …/questions/reorder`). Reorder is the only way to change a question's position. The admin editor never sends `order_index`, so phase 3 is unaffected. |
| b | Import errors today are `HTTPException(422, detail="…")`, but D8 says services never raise FastAPI exceptions, and T7 §6.3 expects "the project's 422 error type with the same messages". | `content_service.import_game` raises `RequestBodyInvalidError` carrying **one** error entry with today's message text (e.g. `loc: ["body","file"]`, `msg: "Question 3 invalid: …"`). The admin import route keeps its current `HTTPException` shape until phase 3 switches it to `content_service`. |
| c | §6.3 says "each course card links to `/courses/:courseId`", but the host `HomePage` has no course cards; courses appear only in the room-creation `<select>`. | Add a **"Your courses"** card list under the room-creation card; each card links to `/courses/:courseId`. |
| d | `GET /host/courses/{id}/games` needs `session_count` and the D1 filter, but §6.2.2 lists no read function for it. | Add `content_service.list_course_games(db, actor, course_id) -> list[HostGameItem data]` (admin: all games in the course; others: games D1 lets them run). |
| e | `require_session_host` replaces four inlined checks with four different 403 messages. | One message: `"Only the session host can access this session"`. No test asserts the old wording. |
| f | No host endpoint returns a single course, but the course and roster pages need its name. | The pages read the name from `GET /game/my-courses`; no new endpoint. |
| g | The phase 2 tests need user/course/grant helpers like those in `tests/integration/test_course_games.py`. | A small shared helper module under `tests/integration/`; `test_course_games.py` is not edited and its code is not copied. |
| h | Prompts are sanitized (bleach) **after** validation, so a prompt such as `<script></script>` passes `min_length=1` and is stored as an empty string. | Kept as is (existing behaviour, also on the admin path). Recorded as a finding in `backend/app/services/README.md` gotchas when `content_service` lands. |
| i | `delete_game` clears Redis after the MySQL deletes flush but before `get_db` commits, so a failed commit leaves MySQL rows without Redis state. | Accepted as specified: such sessions are simply no longer live (D7). |
| j | If T7's MR !13 merges first, the ported `QuestionEditorPage`'s type list won't include `hotspot`. | Port unchanged. Editing hotspot questions in the host editor is T7 stage B (`HotspotEditor`, t7-hotspot.md §7.9). |

Branching: phase 2 branches from `main` now rather than after !13 merges. New README text goes in
different places from T7's to keep conflicts small, and `main` is merged into this branch as soon as
!13 lands.

### 6.3 Phase 2 — host frontend (Arjun)

`frontend/host/src/lib/api.ts`: add `put`, `patch`, `postForm`, `download`, copied from
`frontend/admin/src/lib/api.ts` (download must use `fetch` + blob — an `<a href>` can't send the
bearer token).

Routes in `frontend/host/src/App.tsx`, all inside the existing `RequireAuth`, with a shared top
bar (Home · Sessions · Sign out) on the non-game pages:

| Route | Page | Content |
|---|---|---|
| `/home` | `HomePage.tsx` (edited) | Existing room creation; the game dropdown now lists only games whose `course_id` equals the selected course (unassigned games hidden). Each course card links to `/courses/:courseId`. |
| `/courses/:courseId` | `CoursePage.tsx` (new) | Games of this course (`GET /host/courses/:id/games`): create, import JSON, edit (→ editor), export, delete. Delete confirms first, naming the session count from `HostGameItem.session_count` (e.g. "Delete 'Quiz 3'? This permanently deletes its 4 sessions and all their scores."); a 409 is shown inline. Link to roster. |
| `/courses/:courseId/roster` | `RosterPage.tsx` (new, ported) | Port of the admin roster page and CSV column-mapping wizard, pointed at `/host/courses/:id/roster*`. |
| `/games/:gameId/edit` | `QuestionEditorPage.tsx` (new, ported) | Port of the admin editor, pointed at `/host/games/:id/*`; game metadata editable (no course field). Shows the live-session 409 as an inline message, not a page takeover. |
| `/sessions` | `SessionsPage.tsx` (new) | `GET /game/my-sessions`; per row **Download summary (HTML)** → `/game/sessions/:id/report`, **Download scores (CSV)** → `/game/sessions/:id/export`. |

Porting rules: do not copy the literal `…`-in-JSX bug (`frontend/admin/src/pages/README.md`);
add a "ported from admin" note to the host `pages/README.md` gotchas (three copies to keep in sync).
Update host `src/README.md`, `pages/README.md`, `lib/README.md`.

### 6.4 Tests implied (T5; written by the phase owner, against the live stack)

Success and denial for each rule. Each test ships in the MR of the phase tagged.

| Phase | Test |
|---|---|
| 1 | Host denied on a game whose course they don't HOST, even with a grant (D1) |
| 1 | Revoking course HOST revokes game access |
| 1 | `create_room` 409 for course mismatch and for an unassigned game (also as admin) |
| 1 | Admin grant-game-access 409 without course HOST |
| 1 | Importing an unmodified `sample_games/*.json` with `course_id` succeeds (admin import) |
| 2 | Host CRUD on an own-course game |
| 2 | Auto-grant on host create and host import |
| 2 | Host create/import with an unknown `course_id` → **403, not 404**: `assert_host_can_use_course` runs before `content_service`'s 404 and a non-admin is not HOST of a nonexistent course |
| 2 | Path-based course endpoints (`/host/courses/{id}/…`) → 404 for a nonexistent course, for a host and for an admin |
| 2 | Question mutation 409 while live, allowed after the room is deleted |
| 2 | Answered-question delete 409 |
| 2 | Update re-validation 422 with the `VALIDATION_ERROR` body; explicit `null` field 422 |
| 2 | Host game delete 409 with another host's session, and with a NULL-host session |
| 2 | Game delete 409 while a session is live |
| 2 | Game delete clears `room:{code}` and `session:{id}:*` in Redis. Exercised through the **host** delete path, which runs the shared `content_service.delete_game` |
| 2 | Downloads (HTML report and CSV): 403 for a non-host, 409 before COMPLETED, 200 with correct CSV columns / HTML for the host |
| 2 | Host roster import deactivates missing netids; a non-HOST gets 403 |
| 2 | Host roster PATCH with a `roster_id` from another course → 404 |
| 3 | Admin game delete clears Redis and is 409 while live (admin path now on `content_service`) |
| 3 | Admin question update re-validation 422 (admin path now on `content_service`) |

### 6.5 Phase 3 — admin switch + admin-first app (Vincent)

Backend:
- `routers/admin.py` game/question/import/export handlers delegate to `content_service` (same
  URLs, still `require_admin`). Admins thereby gain D6–D8 behaviour.
- New `GET /admin/courses/{course_id}/access` → users with their HOST/PLAYER role in that course
  (for the course detail page). Grant/revoke reuse the existing
  `POST/DELETE /admin/users/{id}/course-access` endpoints.

Frontend (`frontend/admin/src/`):
- Sidebar grouped. **Administration** (top): Users, Courses, Guests. **Content & hosting**
  (secondary, visually subordinate): Games, Sessions. **Footer:** "Open Host app" (`/host/`) and
  "Open Player app" (`/player/`) links, then Logout. Default route becomes `/users`.
- New `CourseDetailPage` (`/courses/:courseId`): rename, HOST/PLAYER members with grant/revoke,
  link to roster, list of the course's games.
- Games page: course column, course filter, an **Unassigned** filter, and assign-course on edit.
- User detail: game-access picker grouped by course; surfaces the 409 from §6.1.6.
- `RequireAdmin` also checks the JWT's `role` claim client-side (decode like player
  `isTokenExpired`) and sends non-admins to `/login` with a message. UX only — the server still
  enforces `require_admin`.
- Full host/player access is via the footer links. Under nginx all apps share one origin and one
  `localStorage.token`, so the admin arrives signed in; `authorise_player` admits ADMIN. Caveat
  (documented, not fixed): the player app's "Play Again" removes the shared token, signing the
  admin out. In `npm run dev` the apps are on different ports and the admin must sign in again.

## 7. Known risks and open edges

- Third copies of the question editor and roster wizard (host port) will drift from admin's.
- Reports reflect current questions, not the questions as played (D9).
- A disconnected host's room stays "live" for D7 until its Redis key expires (≤90 min) or the
  host deletes the session from Home — the escape hatch for a locked game.
- Concurrency: the D7 live check and a room creation can race (a room opened between the check and
  the flush). Accepted — window is milliseconds and the outcome is the pre-T4 status quo.
- Moving a game's course (admin) leaves completed sessions in the old course (D4/D5), so a game's
  sessions may span courses historically.
- **Host game deletion destroys score history.** A host deleting their own game also deletes
  every session of it they ran, with all student scores (D6). Those scores may be the only record
  of in-class participation. Mitigation: the confirm dialog names the session count (§6.3) and
  hosts can download each session's CSV first from `/sessions`. No soft-delete or archive in T4.
- **Deleting a live session doesn't notify its sockets (predates T4).** `DELETE /api/game/sessions/{id}`
  (`routers/game.py`) clears Redis and MySQL but emits nothing, so a connected host and players
  are left on a dead room until their next action errors. D6 sends admins through this endpoint
  before deleting a live game, so it is now on a documented path. Not changed in T4. The fix
  would be a `game_abandoned` emit to `room_code`, which needs a router→gateway call that the
  layering currently avoids.
- The HTML session report the host now downloads (`services/report_service.py`) renders no chart
  and no correct answer for `multi_select` questions, and keeps its own copies of the answer-reveal
  and Levenshtein logic separate from `game_service`/`gateway` (`services/README.md`). Documented,
  not fixed in T4; it is addressed alongside T7, which must extend report rendering for the new
  question types anyway.
- `host_advance` (`websocket/gateway.py`) reads `room_state.question_phase` and acts on it with
  no lock, and python-socketio runs handlers concurrently by default, so a double-click on Next can
  advance twice (e.g. skip a question's results). Out of T4 scope; revisit with T7's game-loop work.
