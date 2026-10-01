# backend/app/websocket/

Real-time layer: a python-socketio `AsyncServer` that runs the live game loop — joining rooms,
host-driven phase transitions, answer submission, question timers, and host-disconnect
handling. It is the only place that emits events to clients. `backend/app/main.py` wraps the
FastAPI app with `socketio.ASGIApp(sio, other_asgi_app=app)`, so `/socket.io/*` lands here.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Empty package marker. |
| `events.py` | String constants for every Socket.io event name, grouped by direction and audience. |
| `middleware.py` | `authenticate_socket(auth, db)` — validates the JWT from the socket `auth` dict (access or temp token) and returns the `User`, or raises `ValueError`. |
| `gateway.py` | The `sio` server, all event handlers, payload builders, and background timer/abandon tasks. |

## Key entry points

- **`gateway.sio`** — imported by `main.py`; the only symbol used outside this directory.
- **Handlers** (client → server, names from `events.py`):
  - `connect` — per-IP rate limit in Redis (`ws_rate:{ip}`, 10 per 10s, non-dev only, bypassable
    with `STRESS_TEST_KEY`), then JWT auth; stores `user_id` in the socket session.
  - `disconnect` — host: auto-lock the open question, emit `host_disconnected`, start a 5-min
    abandon task. Player: mark disconnected in Redis, emit `player_left` to host.
  - `join_room {room_code, role}` — HOST or PLAYER join; replies `sync_state`; late-joining
    players get the open question with remaining time (min 5s).
  - `rejoin_room {room_code}` — same, but role is inferred (host if `host_user_id` or ADMIN).
  - `host_advance` — state machine on `room_state.question_phase`:
    `None` → `start_game` + first `new_question`; `QUESTION` → `question_results`;
    `RESULTS` → next `new_question`, or `game_over` when out of questions.
  - `submit_answer {question_id, answer_data, answer_time_ms}` — validate, then
    `game_service.record_answer`, then `answer_received` / `answer_status` / `answer_phase_ended`.
  - `host_lock_question` — toggles lock; pauses/resumes the timer by storing
    `timer_remaining_seconds` and shifting `started_at`.
- **Audiences** — three kinds of Socket.io room: `{room_code}` (everyone),
  `{room_code}:host` (host only, `_host_room`), `user:{user_id}` (one player, `_user_room`).
  Results and game-over payloads are sent per player to `user:{id}` so players never see others' scores.
- **Payload safety** — `_question_payload` never includes `answer_data`; `_answer_reveal`
  derives only the facts clients need (correct indices/value, accepted answers).
  **Adding a question type** means updating both, plus the `multi_select`-style shape check in `on_submit_answer`.

## In-process state (not in Redis or MySQL)

`_sid_ctx` (sid → user/role/room/session), `_timer_tasks` (session → question timer),
`_abandon_tasks` (session → host grace task). These live in one Python process only. In
non-dev mode `AsyncRedisManager` routes emits across instances, but these dicts do not follow.

## Depends on

- `backend/app/services/` — `game_service` (sessions, scoring, leaderboard, summaries),
  `state_service` (all Redis game state), `auth_service` (`decode_token`, `get_user_by_id`).
- `backend/app/models/` — `Question`, `GameSession`, `SessionScore`, `User`.
- `backend/app/` top level — `config.settings`, `database.AsyncSessionLocal`, `redis_client.get_redis`.
- Within the directory: `gateway` → `events`, `middleware`.

## Depended on by

- `backend/app/main.py` — imports `sio` and mounts it.
- Clients that speak the protocol (by event name, not import): `frontend/host/src/pages/game/GameLayout.tsx`,
  `frontend/player/src/pages/game/GameLayout.tsx`, `scripts/smoke_test_websocket.py`,
  `scripts/simulate_players.py`, `tests/integration/engine/`.

## Gotchas found while reading

- A player who disconnects stays in `session:{id}:players`, so `totalPlayers` and
  `all_players_answered` still count them; the early "all answered" signal never fires.
- No frontend or script emits `rejoin_room`; clients re-send `join_room` on every reconnect.
- In `rejoin_room`, any ADMIN is treated as host, even one who joined the room as a player.
- `gateway.socket_app` (line 61) is unused; `main.py` builds its own `ASGIApp`.
- In `on_submit_answer`, the MySQL commit happens when `_db()` exits, after the socket emits;
  the `has_answered` check is not atomic with `record_answer`'s `mark_answered`.
