# backend/app/models/

SQLAlchemy 2.0 ORM models — the MySQL schema as Python classes. Every class inherits
`database.Base`, uses typed `Mapped[...]` columns, and maps one table. The schema itself is
created and changed only by Alembic migrations in `backend/app/migrations/versions/`; editing a
model here does nothing to the database until a matching migration is written and applied.

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Imports every model in FK-dependency order so `Base.metadata` is complete (Alembic autogenerate and relationship resolution rely on this). |
| `user.py` | `User` — one table for all identities: admins, local accounts, OAuth2/NetID users and guests. |
| `course.py` | `Course`, `CourseRoster` (imported student list per course), `UserCourseAccess` (per-course HOST/PLAYER grant). |
| `game.py` | `Game`, `Question` (ordered, typed, JSON config/answer data), `UserGameAccess` (per-user game grant). |
| `session.py` | `GameSession` (one played instance of a game, keyed by room code) and `SessionScore` (one row per player answer). |

## Tables and key columns

- **`users`** — `id` is a UUID string. Identity depends on which columns are set:
  local account = `username` + `password_hash`; OAuth2 user = `netid`; guest = `email` +
  `role="GUEST"`. `role` is `ADMIN | USER | GUEST`. `netid`, `email` and `username` are each unique.
- **`courses`** — `name`, `semester`. **`course_rosters`** — `(course_id, netid)` unique,
  `full_name`, `email`, `is_active` (deactivated rather than deleted on re-upload).
- **`user_course_access`** — composite PK `(user_id, course_id)`, `role` is `HOST | PLAYER`.
- **`games`** — `title`, `description`, `max_players`. **No link to a course.**
- **`questions`** — `game_id`, `type` (free `String(50)`), `grading_type`
  (`ACCURACY | COMPLETENESS`), `prompt`, `config` (JSON, sent to clients),
  `answer_data` (JSON, server-only), `time_limit_seconds`, `points_value` (float), `order_index`.
- **`user_game_access`** — composite PK `(user_id, game_id)`; this is how a non-admin host is
  allowed to run a game today.
- **`game_sessions`** — `id` UUID, `room_code` (6 chars, unique), `game_id`, `course_id`,
  `host_user_id` (nullable), `status` (`LOBBY | IN_PROGRESS | COMPLETED | ABANDONED`), `completed_at`.
- **`session_scores`** — `session_id`, `user_id`, `question_id`, `points_awarded` (float),
  `answer_time_ms`, `is_correct`, `answer_data` (the player's raw submission as JSON).

## Cascades

- ORM `cascade="all, delete-orphan"`: Course → roster, course access; Game → questions, game access;
  User → course access, game access; GameSession → scores.
- DB `ON DELETE CASCADE`: roster/access rows → their course/user/game; questions → game;
  session_scores → session.
- **No cascade:** `game_sessions.game_id`, `game_sessions.course_id`, `session_scores.user_id`,
  `session_scores.question_id`. Code that deletes those parents must remove children by hand
  (`routers/admin.py` does this for `delete_game` and `delete_user`).

## Depends on

- `backend/app/database.py` — `Base` (declarative base). Nothing else.

## Depended on by

- `backend/app/routers/` (`admin.py`, `game.py`) — query models directly in handlers.
- `backend/app/services/` — every service reads/writes models (`bootstrap` creates the first admin
  `User`); `state_service` uses them only for the Redis-loss fallback (`restore_from_mysql`).
- `backend/app/websocket/` — `gateway.py` (`Question`, `GameSession`), `middleware.py` (`User`).
- `backend/app/common/dependencies.py` — `User` as the return type of the auth dependencies.
- `backend/app/migrations/env.py` — imports all models for autogenerate.

## Gotchas found while reading

- **Deleting a question that has been played fails.** `Question.scores` has no cascade and
  `session_scores.question_id` is `NOT NULL` with no `ON DELETE`, so when `admin.delete_question`
  deletes a question that any session has answered, SQLAlchemy tries to null out the scores'
  `question_id` and the database rejects it (surfaced as a 500). Scores must be deleted first.
- **Nothing in the schema prevents a player answering twice.** There is no unique constraint on
  `(session_id, user_id, question_id)`; duplicate-answer protection lives only in Redis
  (`session:{id}:answered:{qid}` checked in the gateway). If Redis is flushed mid-question a
  second answer would be stored and double-counted.
- **Games are global.** `Game` has no `course_id`; T4's "course-specific games" needs a new column
  and migration, and a decision on what replaces or complements `user_game_access`.
- **Courses can't be deleted** — there is no endpoint, and `game_sessions.course_id` has no cascade.
- **Adding a question type needs no migration.** `type` is a free string and `config` /
  `answer_data` are schemaless JSON; the allowed values and shapes are enforced only by
  `schemas/admin.py` (and per-type branches in services). A migration is needed only for new
  columns or tables (e.g. images).
- **Default mismatch:** the model default for `points_value` is `1.0`, but the DB
  `server_default` (from migration 001, kept by 003) is `1000`. It only matters for rows
  inserted outside the ORM.
- **Async lazy-loading:** relationships load lazily, which raises `MissingGreenlet` under async
  SQLAlchemy. Use `selectinload(...)` or select columns explicitly (see the comment in
  `gateway.py`'s results phase) instead of touching relationship attributes.
