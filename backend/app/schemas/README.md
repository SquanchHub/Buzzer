# backend/app/schemas/

Pydantic v2 models for request validation and response shaping in the REST layer. This is also
where the structure of each question type's `config` / `answer_data` JSON is enforced — the DB
stores those columns as free-form JSON (see `backend/app/models/`), so these validators are the
only gate. Socket.io payloads do **not** go through these schemas; the gateway builds and checks
its dicts by hand.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Empty package marker. |
| `admin.py` | Admin API bodies and responses: courses, roster, games, questions (with per-type validation), users, access grants, admin session list. |
| `auth.py` | Login, token responses, guest join. |
| `game.py` | Host-facing room/session/resource-list models, plus the internal `ScoreResult`. |

## Key entry points

- **`QuestionCreate`** (`admin.py`) — the central validator. Allowed `type` is a regex:
  `multiple_choice | true_false | fill_in_the_blank | multi_select | hotspot`. `validate_structure`
  (model validator) checks per type:
  - `multiple_choice` — `config.options` list with ≥2 items; if ACCURACY, `answer_data.answer_points`
    same length, non-negative numbers.
  - `true_false` — if ACCURACY, `answer_data.answer_points` is a dict with exactly `true` and `false` keys.
  - `fill_in_the_blank` — if ACCURACY, non-empty `acceptedAnswers` strings, `answerPoints` of the
    same length (non-negative), optional non-negative integer `editDistance`.
  - `multi_select` — `config.options` ≥2; if ACCURACY, `answer_points` same length, numbers
    (**negatives allowed** — they are penalties).
  - `hotspot` — `config` is exactly `{imageId, aspectRatio}` (positive int; finite number in
    [0.2, 5]) under **both** grading types; if ACCURACY, `answer_data` is exactly
    `{x, y, innerRadius, outerRadius, partialFraction}` (finite numbers; `x`, `y` in [0, 1];
    0.02 ≤ inner ≤ 0.5; inner ≤ outer ≤ 1; fraction in [0, 1]). Bool is rejected everywhere.
    camelCase keys. Spec: `docs/plans/t7-hotspot.md` §5.1. Whether `imageId` exists is not checked
    here (needs the DB).
  - Field bounds: `prompt` 1–2000 chars, `time_limit_seconds` 2–300, `points_value` 0–100000.
  Also reused by `admin.import_game` to validate every question in an imported JSON bundle.
- **Hotspot checker** (`admin.py`, module level) — `hotspot_config_error(config)` and
  `hotspot_answer_error(answer_data)` return an error message or `None`;
  `is_hotspot_aspect_ratio(value)`. The one implementation of the §5.1 rules: `QuestionCreate`
  raises with these messages, and scoring code reuses them to detect bad stored data. Never
  raise, whatever JSON they are given.
- **`QuestionUpdate`** — all fields optional, same `type` regex, **no structural validation**.
- **`GameMeta`** — a game's own fields (`title`, `description`, `max_players`); validates the
  `game` block of an import bundle, which never carries a course.
- **`GameCreate(GameMeta)`** — adds a required positive `course_id`.
- **`GameUpdate`** — all optional; `course_id` (admin move) must be positive, and an explicit
  `null` is a 422 rather than "unassign". `GameResponse` and `MyGameItem` expose `course_id`
  (`None` = unassigned legacy game).
- **`LoginRequest`** (`auth.py`) — requires `username`+`password` or a dev-only `netid`.
- **`RoomCreateRequest`** (`game.py`) — positive `game_id` and `course_id`.
- **`ScoreResult`** (`game.py`) — `{points_awarded, is_correct}`, returned by
  `game_service.calculate_score`; not an HTTP schema.

## Conventions visible in the code

- Request bodies set `ConfigDict(extra="forbid")`, so unknown fields are a 422 — except
  `GuestJoinRequest`, which allows them.
- Response models use `from_attributes=True` so handlers can return ORM objects directly.
- Usernames are lowercased by a `field_validator` on create and update.
- Naming is mixed by type: MC/TF/multi-select use snake_case `answer_points`; FITB uses camelCase
  `acceptedAnswers` / `answerPoints` / `editDistance`. New types should pick one deliberately.

## Depends on

- `pydantic` (with `email` extra for `EmailStr`). No imports from the rest of the app.

## Depended on by

- `backend/app/routers/admin.py` — nearly all of `schemas/admin.py`.
- `backend/app/routers/auth.py` — `schemas/auth.py`.
- `backend/app/routers/game.py` — the room/session/list models in `schemas/game.py`.
- `backend/app/services/roster_service.py` — `RosterUploadResult`.
- `backend/app/services/game_service.py` — `ScoreResult`; the hotspot checker
  (`is_hotspot_aspect_ratio`, `hotspot_answer_error`) via `hotspot_target`.

## Gotchas found while reading

- **Updates bypass validation.** `QuestionUpdate` has no `validate_structure`, and
  `admin.update_question` writes `config` / `answer_data` as given. A PUT can store a
  multiple-choice question with one option, mismatched `answer_points`, or a type change with the
  old type's data — and `game_service.calculate_score` will then award wrong points or raise
  mid-game. Any new
  type must add validation to both paths (T7 calls this out).
- **The type list is duplicated** — the same regex appears in `QuestionCreate` and
  `QuestionUpdate`; adding a type means editing both.
- **TF points aren't type-checked:** `answer_points` values for `true_false` can be any JSON value.
- **COMPLETENESS skips answer checks but not config checks:** a COMPLETENESS multiple-choice
  question still needs ≥2 options, while COMPLETENESS FITB needs nothing.
- **`QuestionPublic` is unused.** The gateway builds the client-safe question payload itself
  (`_question_payload` in `websocket/gateway.py`), so changing this schema changes nothing.
- **Guest merge has no schema:** both merge-guest endpoints take a raw `dict` body.
- `MyCourseItem.role` is always `"HOST"` for the `/my-courses` endpoint.
