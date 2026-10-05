# backend/app/routers/

HTTP (REST) layer of the FastAPI backend. Each file defines one `APIRouter`; `backend/app/main.py`
mounts them all under the `/api` prefix. Routers handle request parsing, auth/role checks
(via FastAPI `Depends`), and shaping responses. Live gameplay (joining, answering, advancing
questions) is **not** here — that runs over Socket.io in `backend/app/websocket/`.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Empty package marker. |
| `health.py` | `GET /api/health` — pings MySQL and Redis, reports active room count from Redis. |
| `auth.py` | `/api/auth/*` — login, OAuth2 callback, temp-token exchange, guest join, refresh, logout. |
| `game.py` | `/api/game/*` — host-facing: list hostable courses/games/active and completed sessions, create/ping/get rooms, delete a session, list/merge guests, session CSV and HTML report downloads. |
| `host.py` | `/api/host/*` — course content management for hosts (T4 §6.2.3): course roster, course game list, game create/import/edit/delete/export, question CRUD/reorder. |
| `images.py` | `/api/images` (T8) — upload an image into a course (admin or course HOST), fetch its bytes (any token, guests included, with an immutable private cache header). |
| `admin.py` | `/api/admin/*` — admin-only CRUD for courses, rosters, games, questions, users, access grants; game JSON import/export; guest merge; session list, CSV export, HTML report. |

## Key entry points

Other code only touches the module-level `router` object in each file
(`from .routers import admin, auth, game, health, host, images` in `main.py`). Endpoint groups:

- **images.py** (T8, `docs/plans/t8-image-support.md` D4) — `POST /images` (multipart `file` +
  `course_id` form field; `require_user` + `assert_host_can_use_course`, so an unknown course is
  404 for an admin and 403 for a host; 201, or 200 with the existing row for identical bytes);
  `GET /images/{id}` (`get_current_user`, guests included; raw bytes with
  `Cache-Control: private, max-age=31536000, immutable` and `nosniff`, neither on a 404).

- **auth.py** — `POST /login` (username/password → access token + `refresh_token` cookie;
  `{netid}` dev-only fallback → temp token), `GET /oauth2-callback` (reads Traefik's
  `X-Auth-Request-User` header, returns an HTML redirect carrying a temp token),
  `POST /exchange-temp`, `POST /guest` (requires a live room in Redis), `POST /refresh`,
  `POST /logout`. The refresh cookie is HttpOnly, scoped to `path=/api/auth`, 7 days.
- **game.py** — `GET /my-courses`, `/my-games`, `/my-active-sessions`, `/my-sessions`
  (COMPLETED sessions the caller hosted, newest first, with `player_count`); `POST /rooms`
  (delegates to `game_service.create_room`); `GET /rooms/{code}/ping` (public, no auth);
  `GET /rooms/{code}`; `DELETE /sessions/{id}`; `GET /sessions/{id}/guests`;
  `POST /sessions/{id}/merge-guest`; `GET /sessions/{id}/export` (raw CSV) and
  `GET /sessions/{id}/report` (HTML) — both **409 until the session is COMPLETED** (T4 D9).
- **admin.py** — every endpoint depends on `require_admin`. The game, question, import and
  export handlers (T4 phase 3) only translate `content_service` calls, the same code `host.py`
  uses, so admins get its rules: game delete 409 while live and Redis cleared for the deleted
  sessions; question create/update/delete/reorder 409 while live; updates re-validated as a whole
  (explicit `null` and `order_index` are 422); answered questions can't be deleted (409); prompts
  sanitized; import errors as 422 `VALIDATION_ERROR` on `body.file`. Unlike `host.py`, admins may
  delete games with other hosts' sessions and are never auto-granted what they create.
  Games are course-bound: `POST /games` needs `course_id` in the body and `POST /games/import`
  a `course_id` form field next to `file` (404 for an unknown course); `PUT /games/{id}` can move
  a game to another course except while it has a live session (409, `content_service.has_live_session`:
  MySQL `LOBBY/IN_PROGRESS` **and** the `room:{code}` key still in Redis);
  `GET /courses/{id}/access` lists the course's HOST/PLAYER members (HOSTs first, 404 unknown);
  `POST /users/{id}/game-access` is 409 unless the target is ADMIN or HOSTs the game's course.
- **game.py `/my-games`** — admins get every game (unassigned included); others only games they
  hold a grant for **and** whose course they HOST.
- **host.py** — no `require_admin` anywhere; admins pass every check. Course routes
  (`/courses/{course_id}/roster`, `…/roster/import`, `…/roster/{roster_id}`, `…/games`) depend on
  `require_course_host` (**404 for a nonexistent course, even for a host**); game and question
  routes (`/games/{game_id}…`) on `require_game_access`. `POST /games` and `POST /games/import`
  take the course in the body/form, so they run `require_user` + `assert_host_can_use_course`
  first — an unknown `course_id` is therefore **403 for a host, not 404**. Handlers only
  translate `content_service` (and `roster_service`) calls; `PUT /games/{id}` uses
  `HostGameUpdate`, so `course_id` is a 422. Roster PATCH queries on both ids (404 otherwise).
  Handlers leave the commit to `get_db` (via `DbSession`), which runs before the response.

## Conventions visible in the code

- DB sessions come from `database.get_db`, which **commits automatically** when the request
  finishes; many update/delete handlers therefore never call `db.commit()` themselves.
- Auth dependencies from `common/dependencies.py`: `require_admin` (ADMIN only),
  `require_user` (ADMIN or USER, rejects GUEST), `get_current_user` (any valid token).
- Host-owned session endpoints in `game.py` (delete session, list guests, merge guest, CSV
  export) depend on `require_session_host`: 404 unknown session, 403 "Only the session host can
  access this session" unless ADMIN or `session.host_user_id` (T4 §6.2.1).
- Errors are raised as `common/exceptions.py` types (`NotFoundError`, `ConflictError`,
  `ForbiddenError`, `UnauthorizedError`) or `RequestBodyInvalidError` (422); no handler raises
  `HTTPException`.
- Rate limits via `common/rate_limit.limiter`: login 5/15min, exchange-temp 10/min, guest 10/15min.

## Depends on

- `backend/app/services/` — `auth_service` (tokens, password hashing, user lookup/creation),
  `game_service` (`create_room`, `get_session_by_code`), `state_service` (Redis room state,
  `delete_room_state`), `export_service`, `report_service`, `roster_service`, and
  `content_service` (all game/question logic for both `host.py` and `admin.py`).
- `backend/app/models/` — `User`, `Course`, `CourseRoster`, `UserCourseAccess`, `Game`,
  `Question`, `UserGameAccess`, `GameSession`, `SessionScore` (queried directly in handlers).
- `backend/app/schemas/` — `auth`, `game`, `admin` Pydantic request/response models.
- `backend/app/common/` — `dependencies`, `exceptions`, `rate_limit`.
- `backend/app/` top level — `database.get_db`, `redis_client.get_redis`, `config.settings`.

## Depended on by

- `backend/app/main.py` — the only importer; mounts each `router` at `/api`.
- All three frontends call these endpoints through `fetch('/api' + path)` in
  `frontend/{host,player,admin}/src/lib/api.ts`. The admin app uses `/api/admin/*` plus
  `/api/auth/login` and `DELETE /api/game/sessions/{id}`; the host and player apps use
  `/api/auth/*` and `/api/game/*`, and the host app (T4 phase 2) also `/api/host/*`.

## Gotchas found while reading

- **Inject the DB session only as `DbSession`, never `Depends(get_db)`.** `DbSession` sets
  `scope="function"`, so `get_db` commits before the response is sent; FastAPI's default scope
  commits only after it has gone out, and a client reading right after a write saw stale data
  (162/200 after `PUT /admin/games/{id}`, T4 §6.2.5 k). Mixing scopes would also give one request
  two sessions, since FastAPI caches dependencies per scope.
  `tests/integration/test_commit_timing.py` guards this.

- `health.py` counts players with `SCARD room:{code}:players`, but `state_service` stores the
  player set under `session:{session_id}:players`, so `activePlayers` looks like it is always 0.
- **The two guest merges are different operations, on purpose.** `admin.merge_guest`
  (`POST /admin/users/merge-guest`) is a **global identity merge**: it re-attributes *all* of the
  guest's answers, in every session, then deletes the guest — or, if no account has that netid
  yet, promotes the guest in place (`netid` set, `role=USER`). Admins are global, so that is
  intended. `merge_guest_for_session` in `game.py` (`POST /game/sessions/{id}/merge-guest`) is
  **session-scoped**: a host moves only *that* session's answers (409 unless the session is
  COMPLETED; 409 if the target already has answers in it; 404 if the guest has none there). The
  guest is kept while it still has answers elsewhere and deleted once it has none; it is never
  promoted, since that would change its identity in other hosts' sessions. Both normalise the
  netid with `.strip().lower()`. (Before the fix the host path moved *all* of the guest's
  answers, including other hosts' sessions.)
- **Admin merge can double-count (documented, not fixed):** if the target account already
  answered in a session the guest also played, `admin.merge_guest` leaves two rows for the same
  question there, both counted. The host path refuses that case with a 409.
- **Finding — host merge targets any netid (documented, not fixed):** a host can attribute their
  session's guest answers to *any* account with a netid, even one with no roster row or access
  in the session's course. It only affects the host's own session's rows, but it writes into
  that account's score history. Restricting targets to the course roster/access would be a
  separate authorization change.
