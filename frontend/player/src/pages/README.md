# frontend/player/src/pages/

Screens for the Player app, which runs on students' phones. Three pre-game pages (room code,
identity, OAuth2 return) and a `game/` subfolder where one layout owns the Socket.io connection
and five child pages render each phase. Routes are declared in `frontend/player/src/App.tsx`
(served under `/player/` in production).

## Files

| File | Route | Purpose |
|---|---|---|
| `JoinPage.tsx` | `/join` | Room-code entry; checks the room via `GET /game/rooms/:code/ping`; auto-submits when opened from the host's QR (`?code=`). |
| `NamePage.tsx` | `/name/:code` | Choose identity: guest (name + email → `POST /auth/guest`), UW NetID SSO, or local username/password. Skipped straight to "Join Game" if an unexpired token exists. |
| `LoginPage.tsx` | `/login` | OAuth2 return landing: exchanges the temp token, then returns to `/name/:code` using `sessionStorage.joinRoomCode`. |
| `game/GameLayout.tsx` | `/game/:code` | Checks token expiry, opens the socket, joins as PLAYER, handles server events, exposes state via context, routes between child pages, shows a "host disconnected" banner. |
| `game/LobbyPage.tsx` | `…/lobby` | Room code, spinner, "N players in room". |
| `game/QuestionPage.tsx` | `…/question` | Answer UI per type: MC colored buttons, True/False, fill-in-the-blank text box, multi-select checklist + Submit. Timer bar. Answer time measured from mount. |
| `game/FeedbackPage.tsx` | `…/feedback` | Static "Answer locked in!" screen shown after `answer_received`. |
| `game/ResultsPage.tsx` | `…/results` | Correct/Incorrect/Recorded, the player's answer, points earned, running total, rank. |
| `game/GameOverPage.tsx` | `…/gameover` | Final rank and score plus a per-question recap (your answer vs. correct answer). "Play Again" clears the token. |

## Key entry points

- Each file's default export is a page component, imported only by `App.tsx`.
- `useGame()` (from `game/GameLayout.tsx`) provides `phase`, `gameStatus`, `roomCode`,
  `playerCount`, `hostDisconnected`, `currentQuestion`, `questionLocked`, `lastAnswerData`,
  `answerResult`, `questionResults`, `gameOver`, and `emitAnswer(questionId, answerData, ms)`.
- `answer_data` shapes sent by `QuestionPage`: `{selectedIndex}`, `{selectedValue}`, `{text}`,
  `{selectedIndices}`. They must match `game_service.calculate_score` on the backend.
- Socket events handled: `sync_state`, `player_joined`, `new_question`, `question_locked`,
  `question_unlocked`, `answer_received`, `question_results`, `game_over` (then disconnects),
  `host_disconnected`, `game_abandoned`, `error`. Emitted: `join_room` (every connect), `submit_answer`.

## Depends on

- `frontend/player/src/lib/` — `api`, `isTokenExpired`.
- `frontend/player/src/components/ui/` — `Button`, `Card*`, `Input`, `TimerBar`.
- `frontend/player/src/types/game.ts` — payload types. npm: `react-router-dom`, `socket.io-client`.
- Backend `/api/auth/*`, `/api/game/rooms/*` and the Socket.io protocol (`backend/app/websocket/`).
- Storage keys: `localStorage` `token`, `playerName`, `playerEmail`; `sessionStorage` `joinRoomCode`.

## Depended on by

- `frontend/player/src/App.tsx` only. The host's QR code links to `/player/join?code=…`.

## Gotchas found while reading

- **Any `error` event ends the game UI.** `GameLayout` swaps in a full-screen error with only
  "Back to Join", and clears it only on socket reconnect. A normal race, such as submitting just
  as the host locks or advances ("Question is locked", "No active question"), strands the
  player for the rest of the game even though the socket is still connected.
- **Lobby count is stale.** The backend sends `player_joined` only to the host room, so a
  player's count never updates after their own `sync_state`.
- **The host-disconnected banner sticks.** It is cleared only by the next `new_question`, not
  when the host reconnects.
- **"Correct!" disagrees with the backend.** `ResultsPage` shows "Correct!" when `yourPoints > 0`,
  but the backend's `is_correct` requires full points, so partial credit (MC or multi-select)
  shows "Correct!". Also, `ResultsPage` shows the correct answer only for fill-in-the-blank, and
  `describeAnswer` has no multi-select case.
- **Reconnect gaps.** `sync_state`'s `currentQuestion`/`hasAnswered`/`yourScore` are ignored
  (and missing from the TS type). A reload on `/results`, or during a locked question, shows
  "Loading…" until the next phase. A reload on `/gameover` shows "This game is not accepting
  players".
- **The player never sees the prompt.** `QuestionPage` renders options but not the prompt (it
  appears only in the game-over recap), so players must read it on the host screen. This may be
  intentional. The fill-in-the-blank typo tolerance (`editDistance`) is also sent but not shown.
- **Unused / hidden problems.** `answerResult` (with `isCorrect`) is stored but no page reads it.
  `JoinPage` reports every ping failure, including "game already ended" and network errors, as
  "Room not found". Any unexpired token, even a guest token from an earlier game, hides the
  identity choice on `NamePage`.
