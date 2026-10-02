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
  - Failure: throws `Error(errorMessage(body, status))`, which picks the first of `message`
    (app errors), string `detail` (`HTTPException`), the 422 `detail` array joined as
    `field: msg; …`, the `error` code, or `HTTP <status>`.
  - `T` is only a compile-time cast; responses are not validated at runtime.
- `api.put`, `api.patch` (JSON, same behaviour), `api.postForm<T>(path, FormData)` (multipart,
  no JSON `Content-Type`, for the game import) and `api.download(path)` (fetches with the bearer
  token and saves the response as a file named from `Content-Disposition` — an `<a href>` can't
  send the token). Added for T4 phase 2's management pages, copied from the admin client.
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

- **Error parsing was fixed, but not everywhere.** `api.ts` originally read only `body.detail`,
  so `{"error", "message"}` bodies from `backend/app/common/exceptions.py` (e.g. "Invalid
  credentials", "Maximum of N concurrent rooms reached") reached the host as bare `HTTP 401` /
  `HTTP 409`. `fix/frontend-error-messages` added `errorMessage()` to all three clients.
  `LoginPage`'s direct `exchange-temp` fetch bypasses `api` and still reads only `detail`.
- **No token refresh or 401 handling.** Access tokens expire after 2h (`auth_service.py`), and
  nothing in the host app calls `/api/auth/refresh` or clears the token on 401. An expired
  token still passes `App.tsx`'s `RequireAuth` (which only checks that it exists), so pages load
  and every call fails until the host signs out manually. A socket reconnect also fails, since
  the gateway verifies the same token.
- **Copies in each app:** the player `api.ts` has only `get`/`post`. The host and admin
  `api.ts` both have `put`, `patch`, `delete`, `postForm` and `download` (the host's were copied
  from admin in T4 phase 2). The player `utils.ts` adds `isTokenExpired()`, which the host lacks.
  Fixes to error parsing have to be repeated in all three.
- **`download` revokes its blob URL right after `a.click()`** (as the admin copy does). Chrome
  handles this; some browsers can cancel the download when the URL is revoked that early.
- **Non-JSON success bodies:** a 2xx response that isn't JSON makes `JSON.parse` throw a
  `SyntaxError`. No current host call hits this.
