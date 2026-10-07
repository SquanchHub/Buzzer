# frontend/admin/src/

Source of the Admin app — a React 18 + TypeScript + Tailwind single-page app for course, roster,
user, access, game/question and session management. It talks to the backend only over REST
(`/api/admin/*` plus login and session delete); it has no Socket.io connection. Each subdirectory
has its own README; this file covers how they fit and the top-level files.

## Subdirectories

| Directory | Role | README highlights |
|---|---|---|
| `pages/` | One component per screen (login, courses, roster, users, user detail, guests, games, question editor, sessions). | Question editor is the only authoring UI; roster import is a client-side CSV mapping wizard. |
| `components/` | `ui/` primitives: `Button`, `Card`, `Input` (denser than host/player: 1px borders, `shadow-hard-sm`), `ThemeToggle`, plus the hotspot/ordering editors and image picker. | Token classes only (T9); the hotspot editor is a copy of the host's. |
| `lib/` | `api` client (JSON, multipart upload, file download, error parsing) and `cn`. | Most complete of the three apps' clients; no 401/refresh handling. |

## Top-level files

| File | Purpose |
|---|---|
| `main.tsx` | Mounts `<App />` in `StrictMode` into `#root` and imports `index.css`. |
| `App.tsx` | `BrowserRouter` (basename `/admin/` in production builds). `RequireAdmin` redirects to `/login` when no token is stored or its `role` claim isn't ADMIN; `AdminLayout` renders the admin-first sidebar — an ink `.slab` with the `ThemeToggle` (`onSlab`) in its footer — (Administration: Users, Courses, Guests; Content & hosting: Games, Sessions; footer: Open Host app, Open Player app, Logout) around an `<Outlet />`. Defines every route; `*` → `/users`. |
| `index.css` | Tailwind directives, the shared T9 token block (Paper/Night), paper grain, the global `:focus-visible` rule, `.slab` (sidebar: focus in `canvas`; in Night `ink`/`canvas` remap to `surface`/`line`), `.halftone`, `.ticket`, reduced motion. |

## How it fits together

- **Flow:** `LoginPage` stores the access token in `localStorage.token` → protected routes render
  inside `AdminLayout` → each page calls `api.*` on mount and after every mutation, keeping state
  locally (no global store or cache).
- **Navigation (T4 phase 3):** admin tasks first — users, courses (with a detail page for
  members and access) and guests; games and sessions follow in a visually secondary group; the
  full host and player experiences are one click away in the Host and Player apps (same origin
  and token under nginx).

## Depends on

- Build config one level up in `frontend/admin/`: `vite.config.ts` (dev port 5175, proxies `/api`
  only, `base: '/admin/'` in production), `tailwind.config.ts` (T9 token colours, `hard` shadows, Bricolage Grotesque / JetBrains Mono),
  `tsconfig.json`, `package.json` (react, react-router-dom, lucide-react, clsx, tailwind-merge).
- Backend routes in `backend/app/routers/admin.py`, `POST /api/auth/login`, and
  `DELETE /api/game/sessions/{id}`.

## Depended on by

- `frontend/admin/index.html` (loads `main.tsx`); `npm run build` outputs to `frontend/admin/dist/`,
  which nginx serves at `/admin/`.
- CI runs `tsc --noEmit` on this app for every merge request.

## Gotchas collected from the child READMEs

- `RequireAdmin` checks the token's `role` claim client-side only (UX); the server enforces admin access.
- Tokens are shared with the host and player apps via the same `localStorage` key on the nginx origin.
- Write `…` / `·` / `±` as characters in JSX text: `\u2026` escapes only work inside JS strings
  (T9 fixed the pages that rendered them literally).
- Colours are T9 tokens only; `tests/unit/test_theme_tokens.py` rejects raw palette utilities.
- Roster, game and question management and the hotspot editor are copied into the host app
  (T4 phase 2, T7); fixes must be repeated in both copies.
