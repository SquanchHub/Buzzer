# frontend/admin/src/lib/

Framework-free helpers for the Admin app: an HTTP client for the backend REST API (the most
complete of the three apps' clients — it adds PUT/PATCH, multipart upload and file download) and
a Tailwind class-name helper. The admin app has no Socket.io connection at all.

## Files

| File | Purpose |
|---|---|
| `api.ts` | `api.get/post/put/patch/delete` JSON wrappers, `api.postForm` for multipart uploads, `api.download` for file downloads; all prefix `/api`, attach the bearer token, and throw readable errors. |
| `utils.ts` | `cn(...classes)` — `clsx` + `tailwind-merge`. Identical to the host app's copy. |

## Key entry points

- `api.get<T>(path)`, `api.post<T>(path, body?)`, `api.put<T>(path, body?)`,
  `api.patch<T>(path, body?)`, `api.delete<T>(path)`
  - `path` is relative to `/api` (e.g. `api.get('/admin/courses')`).
  - Sends `Content-Type: application/json` and `Authorization: Bearer <localStorage.token>`
    (read fresh on each call). Empty bodies (204s) resolve to `{}` cast to `T`.
- `api.postForm<T>(path, formData)` — POST without a `Content-Type` header so the browser sets
  the multipart boundary. Used for game JSON import.
- `api.download(path)` — fetches with the bearer token, reads the filename from
  `Content-Disposition: attachment; filename="…"`, and triggers a browser download via a blob URL.
  Used for game export, session CSV export and the HTML session report. (Plain `<a href>` links
  wouldn't work because they can't carry the bearer header.)
- `errorMessage(body, status)` (internal) — turns any backend error body into a message, in order:
  `message` (app errors) → string `detail` (`HTTPException`) → array `detail` joined as
  `field: msg; …` (422 validation) → `error` code → `HTTP <status>`.
  See `backend/app/common/README.md` for the shapes.

## Depends on

- Browser `fetch`, `localStorage` (`token` key, written by `pages/LoginPage.tsx`), `URL.createObjectURL`.
- npm: `clsx`, `tailwind-merge` (`utils.ts` only).
- Backend REST routes under `/api/admin/*`, `/api/auth/login`, and `DELETE /api/game/sessions/{id}`
  (`backend/app/routers/`).

## Depended on by

- Every page in `frontend/admin/src/pages/` imports `api`.
- `frontend/admin/src/components/ui/` — `button.tsx`, `card.tsx`, `input.tsx` import `cn`.

## Gotchas found while reading

- **No 401 handling or refresh.** Nothing calls `/api/auth/refresh` or clears the token on 401;
  after the 2-hour access token expires every page shows an error until the admin logs out.
- **Shared token across apps.** All three apps use the same `localStorage` key `token`. Under nginx
  (`localhost:8080`) they share an origin, so joining as a guest in the player app overwrites the
  admin's token in the same browser (and vice versa). Under `npm run dev` each app has its own port,
  so this only shows up in the built version.
- **Non-JSON success bodies:** `apiFetch` calls `JSON.parse` on any non-empty 2xx body; a text
  response would throw. `download` avoids this by reading a blob.
- **Three copies of the client.** Host and player `api.ts` are smaller subsets (no `put`/`patch`/
  `postForm`/`download`). When the host app gains game/roster management and downloads (T4) it will
  need these methods; error-handling changes have to be made in all three copies.
