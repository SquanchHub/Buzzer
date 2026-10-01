# backend/app/

The FastAPI + python-socketio application package. It serves the REST API under `/api` and the
live game loop over Socket.io at `/socket.io`, from one ASGI process, backed by MySQL (permanent
record) and Redis (live game state). Each subdirectory has its own README; this file summarizes
how they fit together and documents the top-level modules that live directly in this directory.

## Subdirectories

| Directory | Role | README highlights |
|---|---|---|
| `routers/` | REST endpoints: `auth`, `game` (host-facing), `admin` (admin-only CRUD), `health`. | Every `admin` endpoint is `require_admin`; host-owned checks are inlined per handler. |
| `websocket/` | Socket.io server: join, host-driven phase machine, answers, timers, host-disconnect grace. | Only place that emits events; per-player payloads go to `user:{id}` rooms. |
| `services/` | Business logic: auth/JWT, room lifecycle, scoring, Redis state, CSV/HTML exports, roster import. | Callers own the commit; scoring branches per question type. |
| `models/` | SQLAlchemy ORM models for all nine tables. | Each game belongs to one course (`games.course_id`, NULL = unassigned legacy); several FKs have no cascade. |
| `schemas/` | Pydantic request/response models, incl. per-type question validation. | Create validates question structure, update does not. |
| `common/` | Auth/role dependencies, error types and JSON error shapes, logging, rate limiter. | No course-scoped permission dependency exists yet. |
| `migrations/` | Alembic environment and versioned migrations `001`–`004` (linear chain). | Schema changes happen only here (`alembic upgrade head`). |

## Top-level modules

| File | Purpose |
|---|---|
| `main.py` | Builds the FastAPI `app` (lifespan: connect Redis, `bootstrap_admin()`), adds rate-limit and CORS middleware, registers error handlers, mounts the four routers at `/api`, then wraps it as `asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)`. Uvicorn serves `app.main:asgi_app`. Swagger at `/api/docs` in development only. |
| `config.py` | `settings` (pydantic-settings, reads env / `.env`): DB and Redis URLs, JWT keys, CORS origins, `MAX_ROOMS`, admin bootstrap credentials, `STRESS_TEST_KEY`. `APP_ENV=development` drives dev behaviour. |
| `database.py` | Async engine (`asyncmy`), `AsyncSessionLocal`, declarative `Base`, and the `get_db` dependency that **commits on success / rolls back on error** when the request ends. SQL is echoed to logs in development. |
| `redis_client.py` | Lazily created module-level async Redis client (`decode_responses=True`); `get_redis()` / `close_redis()`. |

## How a request flows

- **REST:** client → nginx `/api/*` → router handler → `common` dependency (token → `User`, role
  gate) → `schemas` validation → `services` / direct `models` queries → `get_db` commits →
  response (or a `common.exceptions` error rendered as `{"error", "message"}`).
- **Live game:** client socket → `websocket/middleware` authenticates the JWT on connect →
  `gateway` handler checks Redis state via `state_service` → `game_service` scores and writes a
  `SessionScore` row → gateway emits to the right audience (one sid, the host room, or each
  `user:{id}` room). See `docs/realtime.md` for the full answer trace.
- **Where state lives:** MySQL holds users, courses, rosters, games, questions, sessions and every
  answer. Redis holds only what is happening now: room status and phase, player list and running
  scores, current question, who has answered, answer distributions. Three per-process dicts in
  `gateway.py` hold socket context and timer tasks.

## Cross-cutting conventions

- **Layering:** routers and the gateway call services; services never emit socket events.
  `common/dependencies.py` imports `services/auth_service` (the one upward import).
- **Commits:** `get_db` (REST) and the gateway's `_db()` context manager commit at the end;
  services mostly `flush()`. `start_game` / `complete_game` commit early on purpose.
- **Roles:** `User.role` is `ADMIN | USER | GUEST`; per-course `HOST | PLAYER` lives in
  `user_course_access`; non-admin hosts run a game only with a `user_game_access` grant **and** HOST on the game's
  course. Admins bypass all checks except the room/game course match in `create_room`.
- **Answer secrecy:** `Question.answer_data` never leaves the server; clients get `config` plus a
  derived `answerReveal` after the question closes.

## Adding a question type touches

`schemas/admin.py` (type regex in create **and** update, `validate_structure`) →
`services/game_service.py` (`calculate_score`, `record_answer` distribution keys, both question
summary functions) → `websocket/gateway.py` (`_answer_reveal`, answer-shape check in
`on_submit_answer`, `_question_payload` if extra fields are needed) → `services/report_service.py`
(labels, chart, its own `_answer_reveal`). No migration unless it needs new columns. Outside this
package: all three frontends, `tests/integration/engine/scoring.py`, `scripts/simulate_players.py`.

## Depends on

- MySQL 8 (`DATABASE_URL`) and Redis 7 (`REDIS_URL`), both started by `docker-compose.yml`.
- Environment from `.env` (see `.env.template`); `backend/requirements.txt` for libraries.

## Depended on by

- Uvicorn in the `backend` container (`app.main:asgi_app`, `--reload` with `./backend` mounted).
- nginx (`nginx/nginx.dev.conf`) proxies `/api/` and `/socket.io/` here; Vite dev servers proxy the same.
- All three frontends, `scripts/*.py`, `tests/integration/` (over HTTP/Socket.io), and
  `tests/unit/test_auth.py` (imports `app.main` directly).

## Gotchas collected from the child READMEs

- **Redis leaks when MySQL rows are deleted.** `admin.delete_game` removes sessions from MySQL but
  never calls `state_service.delete_room_state`, so their `room:{code}` keys stay in `LOBBY` for up
  to 90 minutes and still count toward `MAX_ROOMS` in `create_room`; `session:{id}:*` keys never
  expire at all. Repeated test runs can hit the 50-room limit this way.
- **Validation is asymmetric:** question create is structurally validated, update is not.
- **Deleting a played question 500s** (no cascade on `session_scores.question_id`).
- **Duplicate-answer protection is Redis-only** — no unique constraint in MySQL.
- **Games are course-bound, but content management is still admin-only.** Hosts need a game grant
  **and** HOST on its course to run it, and rooms must open in the game's course; questions and
  rosters are still edited only through `/api/admin/*` (T4 phase 2 adds `/api/host/*`).
- **Question-type logic is duplicated** across `game_service`, `gateway` and `report_service`
  (three reveal builders, two Levenshtein implementations), and `report_service` lacks `multi_select`.
- **Disconnected players still count** toward `totalPlayers`, so "all answered" can't fire early.
