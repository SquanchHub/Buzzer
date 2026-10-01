# backend/

Everything the Python backend needs to build and run: the application package, its dependencies,
its container image, the Alembic config, and a key-generation helper. All application code is in
`app/` — see `app/README.md` for the architecture summary and its subdirectory READMEs for detail.

## Contents

| Path | Purpose |
|---|---|
| `app/` | The FastAPI + Socket.io application (routers, websocket, services, models, schemas, common, migrations). |
| `requirements.txt` | Python dependencies for the app and its tests (FastAPI, python-socketio, SQLAlchemy async + asyncmy, Alembic, redis, python-jose, passlib/bcrypt<4, bleach, rapidfuzz, slowapi, structlog, pytest, httpx, locust). |
| `Dockerfile` | `python:3.12-slim` + build deps for asyncmy/cryptography; installs requirements and copies the code. The run command comes from `docker-compose.yml`. |
| `alembic.ini` | Alembic config pointing at `app/migrations`; the DB URL is injected from `DATABASE_URL` in `app/migrations/env.py`. |
| `scripts/generate_keys.py` | Prints a base64 RS256 key pair as `JWT_PRIVATE_KEY=` / `JWT_PUBLIC_KEY=` lines for `.env`. |

## How it runs

- `docker compose up` builds this directory into the `backend` service, mounts `./backend` at `/app`,
  and runs `uvicorn app.main:asgi_app --reload --host 0.0.0.0 --port 8000`. Python edits reload instantly.
- Migrations run in the same image: `docker compose run --rm backend alembic upgrade head`
  (or `docker compose exec backend alembic …` once it is up). On a fresh DB the app waits, logging
  `admin_bootstrap_waiting_for_schema`, until migrations exist.
- CI (`.gitlab-ci.yml`) runs `ruff check backend/ scripts/` and `ruff format --check backend/ scripts/`
  on every merge request — run `ruff format` on touched files before pushing.

## Depends on

- MySQL and Redis containers from `docker-compose.yml`; configuration from the repo-root `.env`.

## Depended on by

- nginx and the three Vite dev servers (proxy `/api` and `/socket.io` to port 8000).
- Repo-root `scripts/` and `tests/` talk to it over HTTP/Socket.io; `tests/unit/` imports `app` directly.

## Gotchas

- `passlib` 1.7 is incompatible with `bcrypt>=4`, hence the pin in `requirements.txt`.
- Changing `requirements.txt` or the `Dockerfile` needs `docker compose up --build`.
- If JWT keys are missing or malformed the app silently generates ephemeral keys
  (`services/auth_service.py`), so every token dies on restart.
