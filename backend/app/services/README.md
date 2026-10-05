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
| `image_service.py` | Question images (T8): validates uploads by their bytes with Pillow (PNG/JPEG/WebP, ≤ 2 MB, ≤ 4096 px per side), strips metadata with rotation applied, stores them per course with duplicate reuse, and serves contract calls C4–C6. |
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
    within `editDistance`), `multi_select` (sum of per-option points, floored at 0), `hotspot`
    (flat band: inner = full points and correct; outer = `points_value × partialFraction`;
    miss, malformed tap or invalid stored target = 0).
    **Adding a question type means adding a branch here** and in `record_answer`'s distribution keys.
  - `record_answer` adds a `SessionScore` row (flush only), then updates the Redis score,
    answered set, and distribution hash. Hotspot distribution keys are band names
    (`inner`/`outer`/`miss`) under ACCURACY; COMPLETENESS hotspot records no key.
  - Game-over summaries: for hotspot, both use `hotspot_reveal`; the host summary's
    `answerDistribution` is band counts over **all** answers, and it adds
    `taps: [{x, y, band}]` (band `null` under COMPLETENESS), the first `HOTSPOT_TAP_CAP` (500)
    in answer order (`session_scores.id`). Only hotspot items carry `taps`.
  - Hotspot helpers (pure, module level; `docs/plans/t7-hotspot.md` §5.2–5.4):
    `hotspot_target(question_id, config, answer_data)` → frozen `HotspotTarget` or `None` (bad
    stored data; logs `hotspot_target_invalid`, never raises); `hotspot_band(target, px, py)` →
    `"inner" | "outer" | "miss"` (aspect-corrected distance, boundaries inclusive);
    `hotspot_reveal(target | None)` → the one client-safe hotspot reveal shape, meant for every
    reveal builder (gateway, report, both summaries); `hotspot_tap(answer_data)` → `(x, y)` or
    `None` (the one tap parser); `hotspot_tap_band(grading_type, target, tap)` → band, `None`
    under COMPLETENESS, `"miss"` for an invalid target. Validation rules come from
    `schemas/admin.py`'s hotspot checker, not a copy. Call `hotspot_target` only under ACCURACY
    (COMPLETENESS rows have no target and it would log a false warning).
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
  Hotspot questions render as an inline SVG (`_render_hotspot`): viewBox in units of the image's
  longer side, rings under ACCURACY, every tap as a dot coloured by band, and a band legend
  ("N taps" under COMPLETENESS; "Target data invalid" when the stored target is bad). Band logic
  is imported from `game_service`, not copied. The image comes from `_hotspot_image_data_uri`,
  **a stage A stub that always returns `None`** (draws "Image unavailable") until T8's C5 lands
  (`docs/plans/t7-hotspot.md` §9 stage C).
- **image_service** (T8, `docs/plans/t8-image-support.md` D2) — `normalize(data, field)` →
  `(stored bytes, content_type, width, height)` or a 422 `RequestBodyInvalidError` on `field`;
  `create_image(db, course_id, data, uploaded_by)` → `(Image, created)` (C6: flush only; identical
  stored bytes in the course return the existing row; a concurrent duplicate is caught via a
  savepoint + `IntegrityError` and re-read with `FOR SHARE` — the pre-check must stay a plain read,
  or two uploads deadlock on gap locks); `get_image(db, id)` → `(content_type, bytes) | None`
  (C5); `image_exists(db, id)` (C4). Re-saved images keep their ICC colour profile.
  `question_image_fields(type, config, prompt_image_id)` → `[(body loc, image id)]` — **the one
  place that knows which fields hold images** (prompt, `optionImageIds`, hotspot `imageId`);
  `question_image_ids` is its id set; `assert_usable(db, course_id, fields)` → 422 per field for a
  missing image, another course's image, or a game with no course.
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
  - `sanitize_prompt` / `PROMPT_TAGS` — bleach, keeping `b i br u`; the only sanitizer.
  - `export_game(db, game_id)` → `(filename, bytes)`: the version-1 bundle, used by both routers.
    `import_game(db, actor, raw, course_id)` → `Game`: 404 unknown course;
    every structural problem is a 422 `RequestBodyInvalidError` on `body.file` with the old admin
    route's message text (§6.2.5 b), raised before anything is written; then `create_game`
    (same auto-grant) and the questions in bundle order, prompts sanitized.

## Depends on

- `backend/app/models/` — `User`, `Course`, `CourseRoster`, `UserCourseAccess`, `Game`,
  `Question`, `UserGameAccess`, `GameSession`, `SessionScore`.
- `backend/app/schemas/` — `game.ScoreResult`, `admin.RosterUploadResult`, and the hotspot
  checker in `admin.py` (`is_hotspot_aspect_ratio`, `hotspot_answer_error`).
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
- `backend/app/routers/admin.py` — `content_service` for every game, question, import and
  export handler (T4 phase 3), like `routers/host.py`.
- `backend/app/main.py` — `bootstrap.bootstrap_admin` in the lifespan hook.
- `tests/unit/test_auth.py` — token creation functions.

## Gotchas found while reading

- **A prompt that is only markup is stored empty.** Prompts are validated (`min_length=1`)
  *before* they are sanitized, so e.g. `<script></script>` passes validation and is saved as
  `""` — on the admin path and in `content_service`. Kept as is (T4 §6.2.5 h); validate the
  sanitized text if empty prompts ever matter.
- **Every image a question uses must exist and belong to its game's course** (T8 V3, replacing
  the stage-B dev stand-in): `content_service._check_images` runs on create and on every update
  (after `QuestionCreate`, so structural errors win) via `image_service.assert_usable`, which
  locks the rows `FOR SHARE` in id order. A game with no course can't use images. `import_game`
  rejects a v1 bundle carrying a hotspot question or a raw `prompt_image_id` / `optionImageIds`;
  until T8 V7 (version 2) a game with images exports as v1 and does not re-import.
- Only `room:{code}` has a TTL (90 min). The `session:{id}:*` keys never expire; they are only
  removed by `delete_room_state` (abandon or host delete). Completed games leave them behind.
- `update_player_score` is read-modify-write on a JSON blob, so concurrent updates can lose one.
- `state_service.restore_from_mysql` and `remove_player` are not called anywhere in `backend/`.
  Despite its docstring, `restore_from_mysql` only returns data; it writes nothing to Redis.
- `report_service` has no `multi_select` handling (no chart, no answer reveal), and keeps its
  own copies of `_answer_reveal` and Levenshtein, separate from `game_service`/`gateway`
  (its hotspot branch is the exception: it calls `game_service.hotspot_reveal`).
