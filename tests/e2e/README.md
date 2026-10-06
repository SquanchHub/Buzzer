# tests/e2e — browser end-to-end tests

Real Chromium (Python Playwright, sync API) driving the **built** host, player and admin apps
through nginx, against the live Docker stack. Integration tests (`tests/integration/`) prove the
HTTP/Socket.io protocol; these prove what only a browser can: layout on a phone, the authoring
UI's round trip through the API, and what the host screen shows.

## Run

```bash
docker compose up -d                      # stack: nginx on http://localhost:8080
npm run build                             # nginx serves frontend/*/dist — rebuild after UI changes
pip install -r tests/e2e/requirements.txt
python -m playwright install chromium
pytest tests/e2e
```

`E2E_BASE_URL` overrides the default `http://localhost:8080`. The admin login comes from
`ADMIN_USERNAME` / `ADMIN_PASSWORD` (environment, else `.env`). Not run in CI: it needs the stack.

## How the fixtures work (`conftest.py`)

- `browser` (session): one headless Chromium; exits early if `/api/health` is unreachable.
- `api`: the REST API as the admin. Creates courses, games, questions and rooms over HTTP so a
  test drives only the UI under test; deletes sessions (clears Redis) and games on teardown.
  Courses have no delete endpoint and stay behind as inert rows (as in `tests/integration/`).
- `new_context(token=None, phone=False)`: a fresh browser context — its own `localStorage`, so
  host and players can share one origin. `phone=True` is 375 × 667 with touch. `token` is put in
  `localStorage.token` before any page script runs. Console errors and failed requests are
  collected in `context.problems`.

Selectors use `data-testid`s and visible text only.

## Gotchas

- Plain Playwright, **not** `pytest-playwright`: its `pytest-base-url` dependency registers a
  `--base-url` option that clashes with `tests/integration/conftest.py` in a shared virtualenv.
- Stale `dist/` builds make UI tests fail confusingly; rebuild after frontend changes.
- A crashed run can leave open rooms that count toward `MAX_ROOMS` until their Redis keys expire.
