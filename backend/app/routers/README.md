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
| `game.py` | `/api/game/*` — host-facing: list hostable courses/games/active sessions, create/ping/get rooms, delete a session, list/merge guests, export session CSV. |
| `admin.py` | `/api/admin/*` — admin-only CRUD for courses, rosters, games, questions, users, access grants; game JSON import/export; guest merge; session list, CSV export, HTML report. |

## Key entry points

Other code only touches the module-level `router` object in each file
(`from .routers import admin, auth, game, health` in `main.py`). Endpoint groups:

- **auth.py** — `POST /login` (username/password → access token + `refresh_token` cookie;
  `{netid}` dev-only fallback → temp token), `GET /oauth2-callback` (reads Traefik's
  `X-Auth-Request-User` header, returns an HTML redirect carrying a temp token),
  `POST /exchange-temp`, `POST /guest` (requires a live room in Redis), `POST /refresh`,
  `POST /logout`. The refresh cookie is HttpOnly, scoped to `path=/api/auth`, 7 days.
- **game.py** — `GET /my-courses`, `/my-games`, `/my-active-sessions`; `POST /rooms`
  (delegates to `game_service.create_room`); `GET /rooms/{code}/ping` (public, no auth);
  `GET /rooms/{code}`; `DELETE /sessions/{id}`; `GET /sessions/{id}/guests`;
  `POST /sessions/{id}/merge-guest`; `GET /sessions/{id}/export`.
- **admin.py** — every endpoint depends on `require_admin`. Question prompts are sanitized
  with `bleach` (allowed tags: `b i br u`) on create, update, and import. Import/export use a
  `{"format": "buzzer/game", "version": 1}` JSON bundle.

## Conventions visible in the code

- DB sessions come from `database.get_db`, which **commits automatically** when the request
  finishes; many update/delete handlers therefore never call `db.commit()` themselves.
- Auth dependencies from `common/dependencies.py`: `require_admin` (ADMIN only),
  `require_user` (ADMIN or USER, rejects GUEST), `get_current_user` (any valid token).
- Host-owned session endpoints in `game.py` repeat the check "ADMIN or `session.host_user_id`";
  it is inlined per handler, not a shared dependency.
- Errors are raised as `common/exceptions.py` types (`NotFoundError`, `ConflictError`,
  `ForbiddenError`, `UnauthorizedError`); `import_game` raises `HTTPException(422)` directly.
- Rate limits via `common/rate_limit.limiter`: login 5/15min, exchange-temp 10/min, guest 10/15min.

## Depends on

- `backend/app/services/` — `auth_service` (tokens, password hashing, user lookup/creation),
  `game_service` (`create_room`, `get_session_by_code`), `state_service` (Redis room state,
  `delete_room_state`), `export_service`, `report_service`, `roster_service`.
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
  `/api/auth/*` and `/api/game/*`.

## Gotchas found while reading

- `health.py` counts players with `SCARD room:{code}:players`, but `state_service` stores the
  player set under `session:{session_id}:players`, so `activePlayers` looks like it is always 0.
- `merge_guest_for_session` in `game.py` looks up the netid with `.lower()` but no `.strip()`,
  and never promotes the guest if no real user exists; `admin.merge_guest` does both.
