# frontend/host/src/lib/

Framework-free helpers for the Host app: one thin HTTP client for the backend REST API and
one Tailwind class-name helper. No React, no socket code — the Socket.io connection is opened
directly in `frontend/host/src/pages/game/GameLayout.tsx`, not here.

## Files

| File | Purpose |
|---|---|
| `api.ts` | `api.get` / `api.post` / `api.delete` — `fetch` wrappers that prefix `/api`, send JSON, attach the bearer token, and throw on non-2xx. |
| `utils.ts` | `cn(...classes)` — combines `clsx` (conditional classes) with `tailwind-merge` (later Tailwind classes override earlier conflicting ones). |

## Key entry points

- `api.get<T>(path)`, `api.post<T>(path, body?)`, `api.delete<T>(path)`
  - `path` is relative to `/api`, e.g. `api.get('/game/my-courses')` → `GET /api/game/my-courses`.
  - Every request sends `Content-Type: application/json` and, if `localStorage.token` is set,
    `Authorization: Bearer <token>`. The token is read fresh on each call.
  - Success: the body is parsed as JSON; an empty body resolves to `{}` cast to `T` (e.g. 204s).
  - Failure: throws `Error(body.detail ?? "HTTP <status>")`.
  - `T` is only a compile-time cast; responses are not validated at runtime.
- `cn(...inputs: ClassValue[])` — used by every component in `frontend/host/src/components/ui/`.

## Depends on

- Browser `fetch` and `localStorage` (`token` key, written by `pages/LoginPage.tsx`).
- npm: `clsx`, `tailwind-merge` (`utils.ts` only).
- Backend REST routes under `/api` (`backend/app/routers/`); in dev/prod the frontend and API
  share an origin, so there is no base-URL configuration.

## Depended on by

- `frontend/host/src/pages/`:
  - `LoginPage.tsx` — `api.post('/auth/login')`
  - `HomePage.tsx` — `api.get` for my-courses, my-games and my-active-sessions;
    `api.post('/game/rooms')`; `api.delete('/game/sessions/:id')`
  - `game/GameLayout.tsx` — `api.get('/game/rooms/:code')`
- `frontend/host/src/components/ui/` — `button.tsx`, `card.tsx`, `input.tsx` import `cn`.

## Gotchas found while reading

- **Server error messages are almost never shown.** `api.ts` reads `body.detail`, but
  `backend/app/common/exceptions.py` returns `{"error": code, "message": text}` for every
  `BuzzerError` (`NotFoundError`, `ConflictError`, …) and for unhandled 500s. For example,
  "Invalid credentials" on login or "Maximum of N concurrent rooms reached" on Create Room
  reach the host as a bare `HTTP 401` / `HTTP 409`. Request validation errors (422) do send
  `detail`, but as an array, so the message becomes `[object Object]`. `LoginPage`'s direct
  `exchange-temp` fetch has the same `detail` assumption.
- **No token refresh or 401 handling.** Access tokens expire after 2h (`auth_service.py`), and
  nothing in the host app calls `/api/auth/refresh` or clears the token on 401. An expired
  token still passes `App.tsx`'s `RequireAuth` (which only checks that it exists), so pages load
  and every call fails until the host signs out manually. A socket reconnect also fails, since
  the gateway verifies the same token.
- **Copies in each app:** the player `api.ts` is identical minus `delete`. The admin `api.ts`
  adds `put`, `patch`, `postForm` and `download`. The player `utils.ts` adds `isTokenExpired()`,
  which the host lacks. Fixes to error parsing have to be repeated in all three.
- **Non-JSON success bodies:** a 2xx response that isn't JSON makes `JSON.parse` throw a
  `SyntaxError`. No current host call hits this.
