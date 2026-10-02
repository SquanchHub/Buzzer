"""
Game and question business logic shared by the admin and host routers
(docs/plans/t4-ui-restructuring.md §6.2.2, §6.2.5).

The routers translate these functions to HTTP; access control happens before they
are called (route dependencies). Like every service here, functions only flush —
`get_db` commits when the request ends. Queries are explicit; relationships are never
lazy-loaded (async SQLAlchemy raises MissingGreenlet).

Phase 2 uses this from routers/host.py; phase 3 switches routers/admin.py over too.
"""

from __future__ import annotations

import structlog
from redis.asyncio import Redis
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ConflictError, NotFoundError
from ..models.course import Course, UserCourseAccess
from ..models.game import Game, UserGameAccess
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.admin import (
    GameMeta,
    GameResponse,
    GameUpdate,
    HostGameItem,
    HostGameUpdate,
)
from . import state_service as state

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Live sessions (D7)
# ---------------------------------------------------------------------------


async def has_live_session(db: AsyncSession, redis: Redis, game_id: int) -> bool:
    """A session is live if MySQL says LOBBY/IN_PROGRESS *and* its room key is
    still in Redis. MySQL alone isn't enough: a room that is never started stays
    LOBBY forever after its Redis TTL lapses, which would lock the game for good."""
    room_codes = (
        await db.execute(
            select(GameSession.room_code).where(
                GameSession.game_id == game_id,
                GameSession.status.in_(["LOBBY", "IN_PROGRESS"]),
            )
        )
    ).scalars()
    for code in room_codes:
        if await state.get_room_state(redis, code) is not None:
            return True
    return False


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


async def _get_game(db: AsyncSession, game_id: int) -> Game:
    game = await db.get(Game, game_id)
    if not game:
        raise NotFoundError(f"Game {game_id} not found")
    return game


async def list_course_games(
    db: AsyncSession, actor: User, course_id: int
) -> list[HostGameItem]:
    """Games in a course that `actor` can run (§6.2.5 d): admins see all of them; anyone
    else only those D1 allows — a game grant AND HOST on the course. Each item carries
    the number of the game's sessions in any status."""
    session_count = (
        select(func.count(GameSession.id))
        .where(GameSession.game_id == Game.id)
        .correlate(Game)
        .scalar_subquery()
    )
    query = select(Game, session_count.label("session_count")).where(
        Game.course_id == course_id
    )
    if actor.role != "ADMIN":
        query = query.join(
            UserGameAccess,
            (UserGameAccess.game_id == Game.id) & (UserGameAccess.user_id == actor.id),
        ).join(
            UserCourseAccess,
            (UserCourseAccess.course_id == Game.course_id)
            & (UserCourseAccess.user_id == actor.id)
            & (UserCourseAccess.role == "HOST"),
        )
    rows = (await db.execute(query.order_by(Game.title))).all()
    return [
        HostGameItem(
            **GameResponse.model_validate(game).model_dump(), session_count=count
        )
        for game, count in rows
    ]


async def create_game(
    db: AsyncSession, actor: User, meta: GameMeta, course_id: int
) -> Game:
    """404 for an unknown course. A non-admin creator is granted the game (D1 auto-grant)."""
    if not await db.get(Course, course_id):
        raise NotFoundError(f"Course {course_id} not found")
    game = Game(
        title=meta.title,
        description=meta.description,
        max_players=meta.max_players,
        course_id=course_id,
    )
    db.add(game)
    await db.flush()
    if actor.role != "ADMIN":
        db.add(UserGameAccess(user_id=actor.id, game_id=game.id))
        await db.flush()
    await db.refresh(game)  # load server defaults (created_at)
    logger.info("game_created", game_id=game.id, course_id=course_id, by=actor.id)
    return game


async def update_game(
    db: AsyncSession,
    redis: Redis,
    actor: User,
    game_id: int,
    patch: GameUpdate | HostGameUpdate,
) -> Game:
    """Apply title/description/max_players. `course_id` exists only on the admin schema:
    when present and different, 404 for an unknown course and 409 while live (D5)."""
    game = await _get_game(db, game_id)
    new_course = getattr(patch, "course_id", None)
    if new_course is not None and new_course != game.course_id:
        if not await db.get(Course, new_course):
            raise NotFoundError(f"Course {new_course} not found")
        # Completed sessions keep the course they were played in; only a live
        # room would end up running in a course that no longer owns the game.
        if await has_live_session(db, redis, game_id):
            raise ConflictError("This game has a live session")
        game.course_id = new_course
    if patch.title is not None:
        game.title = patch.title
    if patch.description is not None:
        game.description = patch.description
    if patch.max_players is not None:
        game.max_players = patch.max_players
    await db.flush()
    return game


async def delete_game(
    db: AsyncSession, redis: Redis, actor: User, game_id: int
) -> None:
    """D6. 409 while live (everyone). A non-admin may only delete a game whose sessions
    were all hosted by them — a session with no recorded host is not theirs. Then the
    sessions, their scores and the game go from MySQL, and each session's Redis state is
    cleared once those deletes have flushed."""
    game = await _get_game(db, game_id)
    if await has_live_session(db, redis, game_id):
        raise ConflictError("This game has a live session")
    if actor.role != "ADMIN":
        # `!=` alone would skip NULL hosts, hence the explicit IS NULL.
        foreign = await db.scalar(
            select(func.count(GameSession.id)).where(
                GameSession.game_id == game_id,
                or_(
                    GameSession.host_user_id.is_(None),
                    GameSession.host_user_id != actor.id,
                ),
            )
        )
        if foreign:
            raise ConflictError("This game has sessions you didn't host")

    sessions = (
        await db.execute(
            select(GameSession.id, GameSession.room_code).where(
                GameSession.game_id == game_id
            )
        )
    ).all()
    session_ids = [s.id for s in sessions]
    if session_ids:
        await db.execute(
            delete(SessionScore).where(SessionScore.session_id.in_(session_ids))
        )
        await db.execute(delete(GameSession).where(GameSession.id.in_(session_ids)))
    await db.delete(game)
    await db.flush()

    for s in sessions:
        await state.delete_room_state(redis, s.room_code, s.id)
    logger.info("game_deleted", game_id=game_id, sessions=len(session_ids), by=actor.id)
