# frontend/player/src/lib/

Framework-free helpers for the Player app: a thin HTTP client for the backend REST API, a
Tailwind class-name helper, and a client-side JWT expiry check. No React, no socket code — the
Socket.io connection is opened in `frontend/player/src/pages/game/GameLayout.tsx`.

## Files

| File | Purpose |
|---|---|
| `api.ts` | `api.get` / `api.post` — `fetch` wrappers that prefix `/api`, send JSON, attach the bearer token, and throw on non-2xx. |
| `utils.ts` | `cn(...classes)` (`clsx` + `tailwind-merge`) and `isTokenExpired(token)`, which decodes the JWT payload and compares `exp` to now. |
| `theme.ts` | T9 theme runtime (identical in all three apps): `useTheme()` (`useSyncExternalStore`; follows the OS preference until the user picks, then `localStorage['buzzer-theme']`, synced across tabs), `setTheme`, `effectiveTheme`, and `cssColor('--token', alpha?)` for canvas code. First paint is set by the inline script in `index.html`. |
| `images.ts` | `loadImageUrl(imageId)` — fetches `/api/images/{id}` with the bearer token and returns an object URL (caller revokes it); throws `ImageUnavailableError` on network error, non-2xx, or a non-image body. Copied in the host app. |
| `options.ts` | `optionLetter(i)`, `optionImageId(imageIds, i)`, `optionText(options, imageIds, i)` ("(image)" for an image-only option, T8 D5/D8), `hasOptionImages(imageIds)`. Identical copy in the other app. |

## Key entry points

- `api.get<T>(path)`, `api.post<T>(path, body?)`
  - `path` is relative to `/api`. Each call reads `localStorage.token` fresh and, if present,
    sends `Authorization: Bearer <token>`.
  - Success: the body is parsed as JSON; an empty body resolves to `{}` cast to `T`.
  - Failure: throws `Error(errorMessage(body, status))`, which picks the first of `message`
    (app errors), string `detail` (`HTTPException`), the 422 `detail` array joined as
    `field: msg; …`, the `error` code, or `HTTP <status>`.
  - `T` is a compile-time cast only; responses are not validated at runtime.
  - There is no `delete` (the host copy has one); the player app never needs it.
- `isTokenExpired(token: string | null): boolean` — `true` if the token is missing, can't be
  decoded, has no `exp`, or `exp` has passed. It does **not** verify the signature; it only
  decides whether to bother the server. The server re-verifies on every request and socket connect.
- `cn(...inputs)` — used by every component in `frontend/player/src/components/ui/`.

- `loadImageUrl(imageId)` — an `<img src>` can't send the bearer token, so images are fetched
  into a same-origin blob (no canvas tainting). Uses `fetch`'s default cache mode so T8's
  immutable `Cache-Control` serves repeats locally (`docs/plans/t7-hotspot.md` §4 C3). Until T8
  exists there is no `/api/images` route; in `vite` dev see the dev image route (stage C removes it).

## Depends on

- Browser `fetch`, `localStorage` (`token` key), `atob`.
- npm: `clsx`, `tailwind-merge`.
- Backend REST routes under `/api` (`backend/app/routers/`); same-origin, no base-URL config.

## Depended on by

- `frontend/player/src/pages/`:
  - `JoinPage.tsx` — `api.get('/game/rooms/:code/ping')`
  - `NamePage.tsx` — `api.post('/auth/guest')`, `api.post('/auth/login')`, `isTokenExpired`
  - `game/GameLayout.tsx` — `isTokenExpired` (redirects to `/name/:code` if expired)
- `frontend/player/src/components/ui/` — `button.tsx`, `card.tsx`, `input.tsx` import `cn`.
- (`LoginPage.tsx` calls `fetch('/api/auth/exchange-temp')` directly and does not use `api`.)

## Gotchas found while reading

- **Error parsing was fixed, but not everywhere.** `api.ts` originally read only `body.detail`,
  hiding the backend's `{"error", "message"}` bodies (`backend/app/common/exceptions.py`) behind
  `HTTP 409`/`HTTP 401`; `fix/frontend-error-messages` added `errorMessage()` here and in the host
  and admin clients. `LoginPage.tsx`'s direct `exchange-temp` fetch bypasses `api` and still reads
  only `detail`, so OAuth2 failures there fall back to "Sign-in failed".
- **Host, player and admin share one token.** All three apps read and write the same
  `localStorage` key `token`. In production they are served under `/host/`, `/player/` and
  `/admin/` on one origin (the OAuth2 redirects in `routers/auth.py` build `FRONTEND_URL` +
  `/host/login` or `/player/login`). As a result:
  - joining as a guest on the same browser replaces a signed-in host's token;
  - an instructor's host token makes `NamePage` skip identity selection and join as the
    instructor;
  - the player's "Play Again" (which removes `token`) signs the host out.
- **No refresh flow.** An expired token sends the player back to `NamePage`. Nothing calls
  `/api/auth/refresh`, even though login sets the refresh cookie.
- **Copies in each app.** The host and admin `api.ts`/`utils.ts` are separate copies (the host
  lacks `isTokenExpired`). A fix to error parsing has to be made in all three.
