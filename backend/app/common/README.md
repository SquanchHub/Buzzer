# backend/app/common/

Cross-cutting backend plumbing used by the routers and app setup: the auth/role dependencies
FastAPI injects into endpoints, the application error types and their JSON error format,
logging configuration, and the rate limiter. This is where any new role or permission check
(e.g. "is this user a HOST of this course?") belongs if it is to be shared across routers.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Empty package marker. |
| `dependencies.py` | FastAPI dependencies: extract the JWT, load the current `User`, and gate by role (`require_admin`, `require_user`). |
| `exceptions.py` | `BuzzerError` and subclasses, plus `register_exception_handlers(app)` which maps errors to JSON responses. |
| `logging.py` | `configure_logging()` — structlog setup (pretty console in dev, JSON in prod). |
| `rate_limit.py` | The shared slowapi `limiter` and its key function. |

## Key entry points

- **`get_current_user`** — reads the token from `Authorization: Bearer …` or an `access_token`
  cookie, verifies it with `auth_service.decode_token`, accepts `token_type` `access` **or** `temp`,
  then loads the `User` from MySQL. Raises `UnauthorizedError` (401) on any failure.
- **`require_admin`** — `user.role == "ADMIN"`, else `ForbiddenError` (403).
- **`require_user`** — any role except `GUEST`, else 403.
- **`get_refresh_token`** — reads the HttpOnly `refresh_token` cookie (used by `/api/auth/refresh`).
- **Errors** (`exceptions.py`): `NotFoundError` 404, `ForbiddenError` 403, `UnauthorizedError` 401,
  `ConflictError` 409, or `BuzzerError(code, message, status)` for anything else.
  `RequestBodyInvalidError(errors)` (not a `BuzzerError`) is for a **service** that finds a
  request body invalid — e.g. T4 D8's re-validated question update. Build it with
  `.from_validation_error(pydantic_exc)` (prefixes each `loc` with `"body"`, drops `url`) or
  `.for_field(field, msg, input)`; it renders exactly like FastAPI's own 422.
- **Error response shapes** produced by the handlers:
  - `BuzzerError` → `{"error": "<CODE>", "message": "<text>"}`
  - request validation → 422 `{"error": "VALIDATION_ERROR", "detail": [ {loc, msg, …}, … ]}`
    — FastAPI's `RequestValidationError` and `RequestBodyInvalidError` both go through
    `_validation_error_response`, so the two can't drift apart
  - uncaught exception → 500 `{"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"}`
  - FastAPI `HTTPException` (not handled here, e.g. `import_game`) → `{"detail": "<text>"}`
- **`limiter`** — apply with `@limiter.limit("5/15minutes")` on an endpoint that takes a `request` arg.

## Depends on

- `backend/app/services/auth_service.py` — `decode_token`, `get_user_by_id` (note: `common`
  imports from `services`, not the other way round).
- `backend/app/database.py` (`get_db`), `backend/app/models/user.py` (`User`),
  `backend/app/config.py` (`settings`).
- Libraries: `fastapi`, `python-jose`, `structlog`, `slowapi`.

## Depended on by

- `backend/app/main.py` — `configure_logging()`, `register_exception_handlers(app)`, and
  `app.state.limiter` / `SlowAPIMiddleware`.
- `backend/app/routers/admin.py` — `require_admin` on every endpoint; exception types.
- `backend/app/routers/game.py` — `require_user`, `get_current_user`; exception types.
- `backend/app/routers/auth.py` — `_token_from_request`, `get_refresh_token`, `limiter`, exceptions.
- `backend/app/services/game_service.py` — raises `ConflictError` / `ForbiddenError` / `NotFoundError`.
- Frontends parse the error shapes above in each app's `src/lib/api.ts`.

## Gotchas found while reading

- **Only two role gates exist, and neither is course-aware.** There is no "host of this course"
  or "host of this game" dependency; `routers/game.py` inlines "ADMIN or session host" checks per
  handler, and course/game access is checked inside `game_service.assert_host_can_use_*`. T4's host
  capabilities need a shared course-scoped dependency here rather than more inline copies.
- **Roles come from the database, not the token.** The JWT carries a `role` claim, but
  `require_admin` / `require_user` check the freshly loaded `User.role`, so promotions and
  demotions take effect on the next request.
- **Temp tokens act as full access tokens.** `get_current_user` accepts `token_type="temp"`
  (meant only for the 15-minute OAuth2 exchange), so a temp token can call any authenticated endpoint.
- **The `access_token` cookie path is dead code** — nothing in the backend sets that cookie; every
  frontend sends the bearer header.
- **Rate limits never fire in development.** `_rate_limit_key` returns a fresh UUID per request when
  `APP_ENV=development`, so the login/guest limits can't be exercised against the local stack.
- **`HTTPException` responses don't use the app error shape** — they return `{"detail": …}`, so
  client error parsing has to handle both `message` and `detail`.
- **422 bodies echo the rejected input, which can contain NaN/Infinity.** Python's JSON parser
  accepts `NaN` and `Infinity` in request bodies, but `JSONResponse` refuses to render them. The
  validation handler therefore replaces non-finite floats in `detail` with strings (`"nan"`,
  `"inf"`, `"-inf"`); without that, a body rejected *for* containing NaN came back as a 500. Any
  new handler that echoes request data needs the same treatment.
