# frontend/host/src/

Source of the Host app — a React 18 + TypeScript + Tailwind single-page app that runs on the
instructor's big screen. The host signs in, picks a course and game to open a room, then drives
the game live over Socket.io (lobby → question → results → … → game over) while players answer on
their phones. Each subdirectory has its own README; this file covers how they fit and the
top-level files.

## Subdirectories

| Directory | Role | README highlights |
|---|---|---|
| `pages/` | `LoginPage`, `HomePage` (create/rejoin rooms) and `game/` — `GameLayout` (socket + context) with Lobby, Question, Results and GameOver child pages. | URL follows server events; any `error` event replaces the whole game screen; reloads after results/game over hang on "Loading…". |
| `components/` | `ui/` primitives: `Button`, `Card`, `Input`, and `TimerBar` (the host copy supports `initialSeconds` for reconnects). | Copies of the admin primitives; `TimerBar` reads props once and must be remounted per question. |
| `lib/` | `api` client (`get`/`post`/`delete`) and `cn`. | No `put`/`patch`/upload/download yet; no 401/refresh handling. |
| `types/` *(no README)* | `game.ts` — TypeScript shapes of every socket payload the host receives (`SyncStatePayload`, `QuestionPayload`, `HostResultsPayload`, `HostGameOverPayload`, `AnswerReveal`, …) and the `HostPhase` union. | Hand-maintained mirror of `backend/app/websocket/gateway.py` payloads; not generated. |

## Top-level files

| File | Purpose |
|---|---|
| `main.tsx` | Mounts `<App />` in `StrictMode` into `#root` and imports `index.css`. |
| `App.tsx` | `BrowserRouter` (basename `/host/` in production). Routes: `/login`; `/home` and `/game/:code/{lobby,question,results,gameover}` wrapped in `RequireAuth` (token exists — expiry not checked); `*` → `/login`. |
| `index.css` | Tailwind directives plus a hardcoded dark `body` background (`#0f172a`) and text color. |

## How it fits together

- **Setup (REST):** `LoginPage` stores `localStorage.token` → `HomePage` loads
  `/api/game/my-courses`, `/my-games`, `/my-active-sessions` and posts `/api/game/rooms` to create a room.
- **Live game (Socket.io):** `GameLayout` connects with the token, emits `join_room` as HOST,
  turns server events into context state and `navigate()` calls, and exposes `emitAdvance()` /
  `emitLockQuestion()` to the child pages via `useGame()`. The host sees prompts, aggregate answer
  distributions and an anonymous score histogram — never individual player scores.
- **What the host can't do today:** download a session's CSV or HTML report, manage rosters,
  or create/edit games and questions. Those exist only in the admin app (T4 moves them here).

## Depends on

- Build config one level up in `frontend/host/`: `vite.config.ts` (dev port 5173, proxies `/api`
  and `/socket.io` with WebSocket upgrade, `base: '/host/'` in production), `tailwind.config.ts`
  (font stack only, no theme colors), `package.json` (react, react-router-dom, socket.io-client,
  qrcode.react, lucide-react, clsx, tailwind-merge).
- Backend `/api/auth/*`, `/api/game/*` and the Socket.io protocol in `backend/app/websocket/`.

## Depended on by

- `frontend/host/index.html`; `npm run build` outputs `frontend/host/dist/`, served by nginx at `/host/`.
- Players reach the game through the QR code / link it renders: `/player/join?code=<ROOM>`.
- CI runs `tsc --noEmit` on this app for every merge request.

## Gotchas collected from the child READMEs

- **Error messages now readable:** the `lib/api.ts` `detail`-only parsing described in
  `lib/README.md` was fixed on `main` (`fix/frontend-error-messages`) — `api.ts` now reads
  `message`, string `detail` and validation-error arrays.
- **Shared token** with the player and admin apps on the nginx origin (`localStorage.token`), and
  no token refresh — an expired token passes `RequireAuth` and every call fails.
- **Fragile game screens:** recoverable socket errors take over the whole screen; reloads on
  results/game over never recover; the player count never drops when players leave.
- **Prompts render as plain text**, so the allowed `<b>/<i>/<u>/<br>` tags show literally.
- **Hardcoded palette** across components, pages and `index.css` (T9); the host screen must also
  stay readable from the back of a classroom in both themes.
