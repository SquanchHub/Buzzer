# frontend/

The three browser apps. Each is an independent Vite + React 18 + TypeScript + Tailwind project
with its own `package.json`, lockfile, build config and `src/`; they share **no code** — common
pieces (UI primitives, the API client, `cn`) are copied into each. All three call the same backend
under `/api`; host and player also hold a Socket.io connection. See each app's `src/README.md` for
its architecture and the subdirectory READMEs for detail.

## Apps

| App | Users | Talks to backend via | Served at (nginx) | Dev port |
|---|---|---|---|---|
| `host/` | Instructor on the big screen: create a room, run the game, see aggregate results. | REST `/api/auth/*`, `/api/game/*` + Socket.io as HOST | `/host/` | 5173 |
| `player/` | Students on phones: join a room, answer, see own results and recap. | REST `/api/auth/*`, `/api/game/rooms/*` + Socket.io as PLAYER | `/player/` (and `/`) | 5174 |
| `admin/` | Admins: courses, rosters, users, access grants, games/questions, sessions and exports. | REST only: `/api/admin/*`, login, session delete | `/admin/` | 5175 |

## Shared structure (per app)

- `index.html` → `src/main.tsx` → `src/App.tsx` (router, basename `/<app>/` in production builds).
- `src/pages/` screens; `src/components/ui/` primitives (`Button`, `Card`, `Input`, plus `TimerBar`
  in host/player); `src/lib/` (`api.ts`, `utils.ts`); `src/types/game.ts` in host/player.
- `vite.config.ts` proxies `/api` (and `/socket.io` for host/player) to `localhost:8000` in dev.
- `tailwind.config.ts` defines only a font stack; colors are raw Tailwind utilities in components.
- Auth: the access token lives in `localStorage.token`; the API client sends it as a bearer header
  and the socket sends it in the connect `auth` payload.

## How the apps relate during a game

Admin sets up courses, rosters, users, access and games → host signs in, opens a room for a
course + game, and shows a QR/room code → players join at `/player/join?code=…` → the host's
`host_advance` drives every phase; the server pushes `new_question` / `question_results` /
`game_over` to both apps, with per-player payloads only to that player → afterwards, session exports
and reports are downloaded from the admin app (T4 adds them to the host app).

## Running

- From the repo root: `npm run install:all` once, then `npm run dev` (all three, labeled output) or
  `npm run dev:host|player|admin`. Vite may pick a different port if one is taken.
- `npm run build` builds all three into `frontend/*/dist/`, which nginx (`docker compose up`) serves
  at `localhost:8080`. Some behaviour (shared origin, admin→host links, WebSocket through nginx)
  only matches production there.
- CI runs `npm install` and `tsc --noEmit` for each app on every merge request.

## Gotchas collected from the app READMEs

- **`npm run build` leaves a compiled `vite.config.js` that shadows `vite.config.ts`.** `tsc -b`
  emits `vite.config.js` / `.d.ts` next to each app's `vite.config.ts` (the composite
  `tsconfig.node.json`; both are gitignored), and Vite loads `vite.config.js` first. So a dev
  server runs whatever config the last build compiled: after changing `vite.config.ts`, rebuild
  (or delete the `.js`) before restarting `npm run dev`.

- **No shared code:** primitives and API clients are copied three times and have already drifted
  (player button sizing, `TimerBar` props, API client methods). Fixes and theming (T9) must be
  applied per app. The hotspot canvas layout rule is copied too: player `HotspotCanvas`, host
  `HotspotView` and `HotspotEditor` (host, plus an identical admin copy since T4 phase 3).
- **One token for three apps:** on the nginx origin, signing in or joining as a guest in one app
  replaces the token in the others; nothing refreshes expired tokens.
- **Hardcoded dark palette** everywhere, including each `index.css` `body` background (T9).
- **Fragile live screens** in host and player: socket `error` events replace the whole UI, and
  reloads mid-results or after game over don't recover.
- **Payload types are hand-written** in `host/src/types/game.ts` and `player/src/types/game.ts`;
  new question types (T7) or image fields (T8) must be added to both, matching the backend gateway.
