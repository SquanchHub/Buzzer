# frontend/player/src/

Source of the Player app — a mobile-first React 18 + TypeScript + Tailwind single-page app that
students open on their phones. A player enters a room code (or scans the host's QR), picks an
identity (guest, NetID SSO, or local account), then answers questions live over Socket.io and sees
their own results and recap. Each subdirectory has its own README; this file covers how they fit
and the top-level files.

## Subdirectories

| Directory | Role | README highlights |
|---|---|---|
| `pages/` | `JoinPage`, `NamePage`, `LoginPage` (OAuth2 return) and `game/` — `GameLayout` (socket + context) with Lobby, Question, Feedback, Results and GameOver child pages. | Per-type answer UIs live inline in `QuestionPage`; the prompt is **not** shown to players; any `error` event strands the player on an error screen. |
| `components/` | `ui/` primitives with phone-sized touch targets: `Button`, `Card`, `Input`, `TimerBar` (no `initialSeconds`), and T9's `Stamp` and `Ticket`; `ThemeToggle`, `PageShell` (wordmark + toggle header). | Option tiles in `QuestionPage` hand-style their riso inks via static class maps; differs from host/admin copies. |
| `lib/` | `api` client (`get`/`post`), `cn`, and `isTokenExpired` (client-side JWT `exp` check). | No refresh flow; shared `localStorage.token` with host/admin. |
| `types/` *(no README)* | `game.ts` — payload types the player receives (`QuestionPayload`, `AnswerResultPayload`, `PlayerResultsPayload`, `PlayerGameOverPayload`, `PlayerAnswerReveal`, …) and the `PlayerPhase` union. | Hand-maintained; `SyncStatePayload` omits fields the backend sends (`currentQuestion`, `hasAnswered`, `yourScore`). |

## Top-level files

| File | Purpose |
|---|---|
| `main.tsx` | Mounts `<App />` in `StrictMode` into `#root` and imports `index.css`. |
| `App.tsx` | `BrowserRouter` (basename `/player/` in production). Routes: `/join`, `/login`, `/name/:code`, `/game/:code/{lobby,question,feedback,results,gameover}`; `*` → `/join`. No route guard — `GameLayout` checks token expiry itself. |
| `index.css` | Tailwind directives, the shared T9 token block (Paper/Night), paper grain, the global `:focus-visible` rule, `.halftone`, `.ticket`, reduced motion, and `-webkit-tap-highlight-color: transparent` for mobile. |

## How it fits together

- **Joining (REST):** `JoinPage` pings `/api/game/rooms/:code/ping` → `NamePage` obtains a token
  (`/api/auth/guest`, `/api/auth/login`, or the NetID SSO round-trip via `LoginPage`) and stores it
  in `localStorage.token`.
- **Live game (Socket.io):** `GameLayout` connects, emits `join_room` as PLAYER, and routes on
  server events. `QuestionPage` sends `submit_answer` with a type-specific `answer_data`
  (`{selectedIndex}`, `{selectedValue}`, `{text}`, `{selectedIndices}`) that must match the backend's
  scoring in `game_service.calculate_score`. After `game_over` the socket is disconnected.
- **Privacy:** results and game-over payloads are sent only to this player's `user:{id}` room, so a
  player sees their own score and rank but no one else's.

## Depends on

- Build config one level up in `frontend/player/`: `vite.config.ts` (dev port 5174, proxies `/api`
  and `/socket.io`, `base: '/player/'` in production), `tailwind.config.ts`, `package.json`
  (react, react-router-dom, socket.io-client, lucide-react, clsx, tailwind-merge).
- Backend `/api/auth/*`, `/api/game/rooms/*` and the Socket.io protocol in `backend/app/websocket/`.

## Depended on by

- `frontend/player/index.html`; `npm run build` outputs `frontend/player/dist/`, served by nginx at
  `/player/` (and `/` redirects there).
- The host app's QR code / join link (`/player/join?code=<ROOM>`).
- CI runs `tsc --noEmit` on this app for every merge request.

## Gotchas collected from the child READMEs

- **Error parsing:** `lib/api.ts` now reads `message`, string `detail` and validation-error arrays
  (`fix/frontend-error-messages`), but `LoginPage`'s direct `exchange-temp` fetch still reads only `detail`.
- **Shared token** with host/admin on the nginx origin: joining as a guest replaces a signed-in
  host's token, and "Play Again" signs the host out in the same browser.
- **Fragile game flow:** ordinary races ("Question is locked") end the game UI; reloads on results,
  locked questions or game over don't recover; the lobby player count is stale; the host-disconnected
  banner sticks until the next question.
- **"Correct!" uses `points > 0`**, so partial credit shows as correct while the backend's
  `is_correct` requires full points.
- **Players never see the prompt** — relevant to T8 prompt images and to new question types that
  need context on the phone (e.g. a canvas question).
- **Late joiners' timer bar starts full** (no `initialSeconds` on the player `TimerBar`).
- **Tokens only (T9):** the eight option colours are `opt-1…8` (same in both themes, dark
  `on-fill` text); tiles stay ≥ 72px tall; `HotspotCanvas` reads `cssColor()` and repaints on toggle.
