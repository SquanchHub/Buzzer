# backend/app/services/

Business logic layer. Routers (HTTP) and the Socket.io gateway call into these modules; the
modules do the actual work against MySQL (SQLAlchemy `AsyncSession`) and Redis. Services never
emit socket events, and mostly only `flush()` — the caller owns the commit and the response.
Exceptions that commit: `game_service.start_game`, `game_service.complete_game`, `bootstrap`.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Empty package marker. |
| `auth_service.py` | bcrypt password hashing, RS256 JWT create/decode (access 2h, refresh 7d, temp 15m), user lookup/creation (local, netid, guest). |
| `bootstrap.py` | On startup, creates the first ADMIN from `ADMIN_USERNAME`/`ADMIN_PASSWORD` if none exists; retries every 5s until migrations have run. |
| `game_service.py` | Room/session lifecycle, join authorisation, per-question-type scoring, answer persistence, leaderboard and game-over summaries. |
| `state_service.py` | All Redis reads/writes for live game state: room, players, current question, answered sets, answer distributions. |
| `export_service.py` | Builds session score CSVs: a raw per-question table and a Canvas gradebook import format. |
| `report_service.py` | Builds a standalone, PII-free HTML session report (charts, word cloud, score histogram) from MySQL only. |
| `roster_service.py` | Upserts `course_rosters` from a Canvas CSV or pre-mapped rows; deactivates netids missing from the upload. |
| `content_service.py` | Game and question business logic shared by the admin and host routers (T4 §6.2.2): course game lists, create/update/delete games, the D7 live check, question CRUD/reorder with D8 re-validation, prompt sanitizing, game import/export (bundle format v1, never `course_id`). |

## Key entry points

- **auth_service** — `hash_password`, `verify_password`, `create_access_token(user_id, role)`,
  `create_refresh_token`, `create_temp_token`, `decode_token` (raises `JWTError`),
  `get_user_by_id`, `get_or_create_user_by_netid`, `create_guest_user`, `authenticate_local`.
  If `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` are unset, it generates in-memory keys (tokens die on restart).
- **game_service** — `create_room`, `get_session_by_code`, `start_game`, `complete_game`,
  `abandon_game`, `authorise_player`, `calculate_score`, `record_answer`, `get_leaderboard`,
  `get_player_question_summary`, `get_host_question_summary`.
  - Access: `assert_host_can_use_course` (HOST on the course) and `assert_host_can_use_game`
    (404 if missing; non-admins need a `user_game_access` grant **and** HOST on the game's course,
    unassigned games are admin-only, one shared 403 message). Admins bypass both.
  - `create_room` runs both asserts, then refuses (409) an unassigned game or one whose course
    differs from the requested course — admins included — before counting rooms.
  - `calculate_score` branches on `grading_type` (COMPLETENESS = full points for any answer)
    then on `question.type`: `multiple_choice`, `true_false`, `fill_in_the_blank` (Levenshtein
    within `editDistance`), `multi_select` (sum of per-option points, floored at 0).
    **Adding a question type means adding a branch here** and in `record_answer`'s distribution keys.
  - `record_answer` adds a `SessionScore` row (flush only), then updates the Redis score,
    answered set, and distribution hash.
  - `start_game` and `complete_game` call `db.commit()` themselves, so concurrent socket
    handlers see the new status.
- **state_service** — key layout is documented in its module docstring
  (`room:{code}`, `session:{id}:players|player:{uid}|question|answered:{qid}|dist:{qid}`).
  Main calls: `get/set_room_state`, `refresh_room_ttl`, `delete_room_state`, `add_player`,
  `get_player`, `get_all_players`, `get_player_count`, `set_player_connected`,
  `update_player_score`, `set/get_current_question`, `mark_answered`, `has_answered`,
  `get_answered_count`, `all_players_answered`, `increment_answer_dist`, `get_answer_dist`.
- **export_service** — `build_session_csv(db, session_id)`, `build_canvas_csv(db, session_id, ...)`;
  both return `(filename, bytes)`.
- **report_service** — `build_session_report(db, session_id)` → `(filename, html_bytes)`.
- **roster_service** — `process_roster_csv(db, course_id, bytes)`, `process_roster_rows(db, course_id, rows)`;
  both return `RosterUploadResult` and cap at 1000 rows.
- **bootstrap** — `bootstrap_admin()`.
- **content_service** (T4 phase 2; access control happens before it is called, in route
  dependencies) — flushes, never commits:
  - `has_live_session(db, redis, game_id)` — D7: a LOBBY/IN_PROGRESS session whose
    `room:{code}` key still exists in Redis. Moved here unchanged from `routers/admin.py`.
  - `list_course_games(db, actor, course_id)` → `list[HostGameItem]` (admin: every game in the
    course; others: D1 — game grant AND course HOST), each with `session_count`.
  - `create_game(db, actor, meta, course_id)` — 404 unknown course; a non-admin creator is
    auto-granted the game (D1).
  - `update_game(db, redis, actor, game_id, patch)` — metadata; `course_id` (admin schema only)
    404 unknown / 409 while live. Takes `redis` for that live check (§6.2.2 omits it).
  - `delete_game(db, redis, actor, game_id)` — D6: 409 while live; a non-admin also 409 if any
    session has another or a NULL host; deletes scores, sessions and the game, then clears each
    session's Redis state.
  - Questions — every mutation is 409 while the game is live (D7):
    `list_questions`; `create_question` always **appends** (a sent `order_index` is ignored);
    `update_question` (D8) 422s any explicit `null` and any `order_index`, then merges the sent
    fields onto the stored question's seven content fields and re-validates the whole thing with
    `QuestionCreate` (`RequestBodyInvalidError` → 422 `VALIDATION_ERROR`); `delete_question` is 409
    if any answer was recorded for it, then re-packs `order_index` to 0..n-1;
    `reorder_questions` (409 unless exactly the game's ids) is the **only** way to move a question.
  - `sanitize_prompt` / `PROMPT_TAGS` — bleach, keeping `b i br u`. `routers/admin.py` still has
    its own copy until phase 3.
  - `export_game(db, game_id)` → `(filename, bytes)`: the version-1 bundle, byte-identical to the
    admin route's export. `import_game(db, actor, raw, course_id)` → `Game`: 404 unknown course;
    every structural problem is a 422 `RequestBodyInvalidError` on `body.file` with the admin
    route's message text (§6.2.5 b), raised before anything is written; then `create_game`
    (same auto-grant) and the questions in bundle order, prompts sanitized.

## Depends on

- `backend/app/models/` — `User`, `Course`, `CourseRoster`, `UserCourseAccess`, `Game`,
  `Question`, `UserGameAccess`, `GameSession`, `SessionScore`.
- `backend/app/schemas/` — `game.ScoreResult`, `admin.RosterUploadResult`.
- `backend/app/common/` — `exceptions` (`ConflictError`, `ForbiddenError`, `NotFoundError`).
- `backend/app/` top level — `config.settings`, `database.AsyncSessionLocal` (bootstrap only).
- Within the directory: `game_service` → `state_service`; `content_service` → `state_service`;
  `bootstrap` → `auth_service`.
- `content_service` also uses `schemas/admin.py`'s game schemas (`GameMeta`, `GameUpdate`,
  `HostGameUpdate`, `GameResponse`, `HostGameItem`).

## Depended on by

- `backend/app/routers/` — `auth`, `game`, `admin` (every service except `bootstrap`).
- `backend/app/websocket/` — `gateway.py` (`game_service`, `state_service`, `auth_service`),
  `middleware.py` (`auth_service`).
- `backend/app/common/dependencies.py` — `auth_service.decode_token`, `get_user_by_id`;
  `game_service.assert_host_can_use_course` / `assert_host_can_use_game`.
- `backend/app/routers/admin.py` — `content_service.has_live_session` (phase 3 switches the
  rest of the admin game/question handlers to `content_service`).
- `backend/app/main.py` — `bootstrap.bootstrap_admin` in the lifespan hook.
- `tests/unit/test_auth.py` — token creation functions.

## Gotchas found while reading

- **A prompt that is only markup is stored empty.** Prompts are validated (`min_length=1`)
  *before* they are sanitized, so e.g. `<script></script>` passes validation and is saved as
  `""` — on the admin path and in `content_service`. Kept as is (T4 §6.2.5 h); validate the
  sanitized text if empty prompts ever matter.
- Only `room:{code}` has a TTL (90 min). The `session:{id}:*` keys never expire; they are only
  removed by `delete_room_state` (abandon or host delete). Completed games leave them behind.
- `update_player_score` is read-modify-write on a JSON blob, so concurrent updates can lose one.
- `state_service.restore_from_mysql` and `remove_player` are not called anywhere in `backend/`.
  Despite its docstring, `restore_from_mysql` only returns data; it writes nothing to Redis.
- `report_service` has no `multi_select` handling (no chart, no answer reveal), and keeps its
  own copies of `_answer_reveal` and Levenshtein, separate from `game_service`/`gateway`.
