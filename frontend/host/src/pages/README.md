# frontend/host/src/pages/

Screens for the Host app, the big-screen display an instructor runs: sign-in; the management
pages (room setup and, from T4 phase 2, course content), which share a top bar from
`ManagementLayout`; and a `game/` subfolder where one layout owns the Socket.io connection and
four child pages render each game phase. Routes are declared in `frontend/host/src/App.tsx`.

## Files

| File | Route | Purpose |
|---|---|---|
| `LoginPage.tsx` | `/login` | NetID SSO link plus username/password form; exchanges the OAuth2 temp token (from the URL hash) via `/api/auth/exchange-temp`; stores the access token in `localStorage.token`. |
| `ManagementLayout.tsx` | (layout) | Top bar for the non-game pages — Home · Sessions · Sign out (clears `localStorage.token`) — around an `<Outlet/>`. |
| `HomePage.tsx` | `/home` | Active sessions (rejoin/delete); room creation, where the quiz list shows only the selected course's games (`MyGameItem.course_id`; unassigned games never match, T4 D4); a "Your courses" card list linking to `/courses/:courseId`. |
| `CoursePage.tsx` | `/courses/:courseId` | The course's games the host can run (`GET /host/courses/:id/games`): create (→ editor), import JSON (`postForm` with `course_id`, → editor), edit link, export (`api.download`), delete with an inline confirm naming the session count ("…permanently deletes its N sessions and all their scores", T4 D6); a 409 shows on the game's row. Course name from `/game/my-courses`; link to the roster. |
| `RosterPage.tsx` | `/courses/:courseId/roster` | **Ported from the admin app**: roster table with inline edit (`PATCH /host/courses/:id/roster/:rid`) and the CSV column-mapping wizard (`POST …/roster/import`; netids missing from the upload are deactivated). Heading names the course; back link to the course page. |
| `QuestionEditorPage.tsx` | `/games/:gameId/edit` | **Ported from the admin app**: add/edit/delete/reorder questions (`/host/games/:id/questions*`), export JSON; plus a host-only **Game details** form (title, description, max players → `PUT /host/games/:id`, no course field — T4 D5). Errors such as the live-session 409 show inline above the content. The admin copy's literal `\u2026`/`\u00b7`/`\u00b1` text is fixed here. Back link to the game's course. |
| `SessionsPage.tsx` | `/sessions` | The host's COMPLETED sessions, newest first (`GET /game/my-sessions`), each with **Download summary (HTML)** (`/game/sessions/:id/report`) and **Download scores (CSV)** (`/game/sessions/:id/export`) via `api.download` (T4 D9). |
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

- `frontend/host/src/App.tsx` — the only importer; wraps the `ManagementLayout` routes and
  `/game/:code` in `RequireAuth` (which only checks that `localStorage.token` exists, not whether
  it has expired).

## Gotchas found while reading

- **Ported pages have copies in the admin app (T4 §6.3).** `RosterPage.tsx` and
  `QuestionEditorPage.tsx` are ports of `frontend/admin/src/pages/` files; each
  starts with a comment listing what changed. A fix in one copy must be repeated in the other.
  Inherited from admin: after a roster import the result card must be dismissed with its icon-only
  ✕ (no accessible label) before "Upload CSV" appears again.

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
