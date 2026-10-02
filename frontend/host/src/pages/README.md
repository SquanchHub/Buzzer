# frontend/host/src/pages/

Screens for the Host app, the big-screen display an instructor runs. Two top-level pages
(sign-in, room setup) and a `game/` subfolder where one layout owns the Socket.io connection
and four child pages render each game phase. Routes are declared in `frontend/host/src/App.tsx`.

## Files

| File | Route | Purpose |
|---|---|---|
| `LoginPage.tsx` | `/login` | NetID SSO link plus username/password form; exchanges the OAuth2 temp token (from the URL hash) via `/api/auth/exchange-temp`; stores the access token in `localStorage.token`. |
| `HomePage.tsx` | `/home` | Lists the host's courses, games and active sessions; creates a room (`POST /game/rooms`), rejoins or deletes an active session. |
| `game/GameLayout.tsx` | `/game/:code` | Opens the socket, joins as HOST, handles every server event, holds all game state in a React context, and routes between the child pages. Also shows a small QR/room-code panel in the corner. |
| `game/LobbyPage.tsx` | `…/lobby` | Large QR code and room code, player count, auto-advance toggle, Start Game button. |
| `game/QuestionPage.tsx` | `…/question` | Prompt, timer bar, "answered / total" counter, Lock/Unlock and Show Results buttons; when auto-advance is on, advances 1.5s after the answer phase ends. Hotspot adds the image (`HotspotView`) with no rings or taps while open (`docs/plans/t7-hotspot.md` H5). |
| `game/ResultsPage.tsx` | `…/results` | Per-question bar chart (MC, T/F, multi-select), word cloud (fill-in-the-blank) or hotspot view (image, rings, every tap coloured by band, band legend; COMPLETENESS: neutral taps + "N taps") with correct answers highlighted; 10s countdown to the next question when auto-advance is on. |
| `game/GameOverPage.tsx` | `…/gameover` | Anonymous score histogram, average/high score, per-question breakdown cards (hotspot cards draw `HotspotView` from the summary's `taps`). |

## Key entry points

- Each file's default export is a page component, imported only by `App.tsx`.
- `useGame()` (exported from `game/GameLayout.tsx`) — the context hook the four child pages
  use. It gives them `phase`, `roomCode`, `gameTitle`, `playerCount`, `currentQuestion`,
  `answeredCount`, `allAnswered`, `answerPhaseEnded`, `questionLocked`, `lockedTimerSeconds`,
  `questionResults`, `gameOver`, `autoAdvance`/`setAutoAdvance`, `emitAdvance()`, `emitLockQuestion()`.
- Socket events handled in `GameLayout`: `sync_state`, `player_joined`, `player_left`,
  `new_question`, `answer_status`, `answer_phase_ended`, `question_locked`, `question_unlocked`,
  `question_results`, `game_over`, `game_abandoned`, `error`. Emitted: `join_room` (on every
  connect), `host_advance`, `host_lock_question`.
- Page changes follow server events: each handler calls `navigate()`, so the URL tracks the game phase.

## Depends on

- `frontend/host/src/lib/` — `api` (`get`/`post`/`delete` wrapper around `fetch('/api' + path)`).
- `frontend/host/src/components/ui/` — `Button`, `Card`/`CardHeader`/`CardContent`, `Input`, `TimerBar`.
- `frontend/host/src/components/HotspotView.tsx` — hotspot display (`HotspotView`, `ringsFromReveal`).
- `frontend/host/src/types/game.ts` — socket payload types (`QuestionPayload`, `HostResultsPayload`, …).
- npm: `react-router-dom`, `socket.io-client`, `qrcode.react`, `lucide-react`.
- Backend: `/api/auth/*`, `/api/game/*` (`backend/app/routers/`) and the Socket.io protocol
  (`backend/app/websocket/`).

## Depended on by

- `frontend/host/src/App.tsx` — the only importer; wraps `/home` and `/game/:code` in `RequireAuth`
  (which only checks that `localStorage.token` exists, not whether it has expired).

## Gotchas found while reading

- **Reloading after the game ends:** a reload on `/gameover` shows "Loading final results…"
  forever. `sync_state` with status `COMPLETED` is ignored, and `game_over` is not sent again.
  The same happens on `/results`: `sync_state` does not carry the results payload.
- **Any `error` event replaces the whole game screen** (`GameLayout` error branch). A recoverable
  error, such as "This game has no questions" on Start, leaves the host on an error page with
  only a "Back to Home" link.
- **Player list key mismatch:** the backend's host `sync_state.players` are Redis records with
  snake_case keys (`user_id`, `display_name`), but `PlayerInfo` expects `userId`/`displayName`.
  The `player_joined` duplicate check therefore never matches them. `players` is currently
  unused by any page, so nothing visible breaks yet.
- **Unused type fields:** `AnswerStatusPayload` declares `displayName` and `answered`, which the
  backend never sends.
- **HTML shown as text:** prompts are rendered as plain text, so the `<b>`/`<i>`/`<u>`/`<br>` tags
  the admin editor allows (bleach whitelist in `routers/admin.py`) appear literally.
- **Player count can't go down:** on `player_left`, `playerCount` is set from the server, but the
  server still counts disconnected players, so the counter does not drop.
- **Duplicated code:** the player join URL (`/player/join?code=…`) is built in both `GameLayout`
  and `LobbyPage`, so the lobby shows two QR codes. `LoginPage` calls `fetch` directly for
  `exchange-temp` instead of `lib/api`.
