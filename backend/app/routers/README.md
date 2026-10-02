# backend/app/routers/

HTTP (REST) layer of the FastAPI backend. Each file defines one `APIRouter`; `backend/app/main.py`
mounts all four under the `/api` prefix. Routers handle request parsing, auth/role checks
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
| `admin.py` | `/api/admin/*` — admin-only CRUD for courses, rosters, games, questions, users, access grants; game JSON import/export; guest merge; session list, CSV export, HTML report. |

## Key entry points

Other code only touches the module-level `router` object in each file
(`from .routers import admin, auth, game, health` in `main.py`). Endpoint groups:

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
- **admin.py** — every endpoint depends on `require_admin`. Question prompts are sanitized
  with `bleach` (allowed tags: `b i br u`) on create, update, and import. Import/export use a
  `{"format": "buzzer/game", "version": 1}` JSON bundle that never contains `course_id`.
  Games are course-bound: `POST /games` needs `course_id` in the body and `POST /games/import`
  a `course_id` form field next to `file` (404 for an unknown course); `PUT /games/{id}` can move
  a game to another course except while it has a live session (409, `content_service.has_live_session`:
  MySQL `LOBBY/IN_PROGRESS` **and** the `room:{code}` key still in Redis);
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
  **Interim:** every mutating `host.py` handler commits before returning, because `get_db`'s
  commit runs after the response is sent (T4 §6.2.5 k); see the gotcha below.

## Conventions visible in the code

- DB sessions come from `database.get_db`, which **commits automatically** when the request
  finishes; many update/delete handlers therefore never call `db.commit()` themselves.
- Auth dependencies from `common/dependencies.py`: `require_admin` (ADMIN only),
  `require_user` (ADMIN or USER, rejects GUEST), `get_current_user` (any valid token).
- Host-owned session endpoints in `game.py` (delete session, list guests, merge guest, CSV
  export) depend on `require_session_host`: 404 unknown session, 403 "Only the session host can
  access this session" unless ADMIN or `session.host_user_id` (T4 §6.2.1).
- Errors are raised as `common/exceptions.py` types (`NotFoundError`, `ConflictError`,
  `ForbiddenError`, `UnauthorizedError`); `import_game` raises `HTTPException(422)` directly.
- Rate limits via `common/rate_limit.limiter`: login 5/15min, exchange-temp 10/min, guest 10/15min.

## Depends on

- `backend/app/services/` — `auth_service` (tokens, password hashing, user lookup/creation),
  `game_service` (`create_room`, `get_session_by_code`), `state_service` (Redis room state,
  `delete_room_state`), `export_service`, `report_service`, `roster_service`, and
  `content_service` (all of `host.py`'s game/question logic; `admin.py` uses only its
  `has_live_session` until phase 3).
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

- **`get_db` commits after the response is sent** (FastAPI 0.142 runs code after a dependency's
  `yield` once the response has gone out). A client that reads immediately after a write can see
  stale or missing data unless the handler commits itself — measured at 162/200 stale reads after
  `PUT /admin/games/{id}`. Admin create handlers and every mutating `host.py` handler commit
  in-handler; the app-wide fix is planned on `fix/get-db-commit-timing` (T4 §6.2.5 k).

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
