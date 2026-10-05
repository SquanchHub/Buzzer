from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import (
    get_current_user,
    require_session_host,
    require_user,
)
from ..common.exceptions import ConflictError, NotFoundError
from ..config import settings
from ..database import DbSession
from ..models.course import Course, UserCourseAccess
from ..models.game import Game, Question, UserGameAccess
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..redis_client import get_redis
from ..schemas.game import (
    ActiveSessionItem,
    MyCourseItem,
    MyGameItem,
    MySessionItem,
    RoomCreateRequest,
    RoomCreateResponse,
    RoomInfoResponse,
)
from ..services import game_service
from ..services import state_service as state

router = APIRouter(prefix="/game", tags=["game"])
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Host resource discovery
# ---------------------------------------------------------------------------


@router.get("/my-courses", response_model=list[MyCourseItem])
async def my_courses(
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> list[dict]:
    """
    Returns courses the authenticated user can host.
    ADMIN sees all courses; USER sees courses with HOST role in user_course_access.
    """
    if user.role == "ADMIN":
        result = await db.execute(
            select(Course).order_by(Course.semester.desc(), Course.name)
        )
        return [
            {"id": c.id, "name": c.name, "semester": c.semester, "role": "HOST"}
            for c in result.scalars().all()
        ]

    result = await db.execute(
        select(Course, UserCourseAccess)
        .join(UserCourseAccess, UserCourseAccess.course_id == Course.id)
        .where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.role == "HOST",
        )
        .order_by(Course.semester.desc(), Course.name)
    )
    return [
        {"id": c.id, "name": c.name, "semester": c.semester, "role": uca.role}
        for c, uca in result.all()
    ]


@router.get("/my-games", response_model=list[MyGameItem])
async def my_games(
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> list[Game]:
    """
    Returns games the authenticated user can run.
    ADMIN sees all games, unassigned ones included. USER sees games they hold a
    user_game_access grant for AND whose course they HOST (same rule as
    game_service.assert_host_can_use_game).
    """
    if user.role == "ADMIN":
        result = await db.execute(select(Game).order_by(Game.title))
        return result.scalars().all()

    result = await db.execute(
        select(Game)
        .join(UserGameAccess, UserGameAccess.game_id == Game.id)
        .join(
            UserCourseAccess,
            (UserCourseAccess.course_id == Game.course_id)
            & (UserCourseAccess.user_id == UserGameAccess.user_id)
            & (UserCourseAccess.role == "HOST"),
        )
        .where(UserGameAccess.user_id == user.id)
        .order_by(Game.title)
    )
    return result.scalars().all()


@router.get("/my-active-sessions", response_model=list[ActiveSessionItem])
async def my_active_sessions(
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> list[dict]:
    """Returns LOBBY/IN_PROGRESS sessions hosted by the current user."""
    result = await db.execute(
        select(GameSession)
        .where(
            GameSession.host_user_id == user.id,
            GameSession.status.in_(["LOBBY", "IN_PROGRESS"]),
        )
        .order_by(GameSession.created_at.desc())
    )
    sessions = result.scalars().all()

    rows = []
    for s in sessions:
        game = await db.get(Game, s.game_id)
        course = await db.get(Course, s.course_id)
        rows.append(
            {
                "session_id": s.id,
                "room_code": s.room_code,
                "status": s.status,
                "game_title": game.title if game else "Unknown",
                "course_name": course.name if course else "Unknown",
                "course_semester": course.semester if course else "",
            }
        )
    return rows


@router.get("/my-sessions", response_model=list[MySessionItem])
async def my_sessions(
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> list[dict]:
    """COMPLETED sessions hosted by the current user, newest first (T4 §6.2.4) — the
    host app's Sessions page lists them with their downloads."""
    player_count = (
        select(func.count(func.distinct(SessionScore.user_id)))
        .where(SessionScore.session_id == GameSession.id)
        .correlate(GameSession)
        .scalar_subquery()
    )
    rows = await db.execute(
        select(
            GameSession.id,
            GameSession.room_code,
            GameSession.completed_at,
            Game.title,
            Course.name,
            Course.semester,
            player_count.label("player_count"),
        )
        .join(Game, Game.id == GameSession.game_id)
        .join(Course, Course.id == GameSession.course_id)
        .where(
            GameSession.host_user_id == user.id,
            GameSession.status == "COMPLETED",
        )
        .order_by(GameSession.completed_at.desc(), GameSession.created_at.desc())
    )
    return [
        {
            "session_id": r.id,
            "room_code": r.room_code,
            "game_title": r.title,
            "course_name": r.name,
            "course_semester": r.semester,
            "completed_at": r.completed_at,
            "player_count": r.player_count,
        }
        for r in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: Annotated[User, Depends(require_session_host)],
    db: DbSession,
    redis=Depends(get_redis),
) -> None:
    """Permanently delete a session and all associated scores. Host or admin only."""
    session = await db.get(GameSession, session_id)  # exists: require_session_host

    # Wipe Redis state (room key, player keys, question key, answered sets, dist hashes)
    await state.delete_room_state(redis, session.room_code, session_id)

    # Delete from MySQL — cascade="all, delete-orphan" removes session_scores automatically
    await db.delete(session)
    await db.commit()

    logger.info("session_deleted", session_id=session_id, deleted_by=user.id)


# ---------------------------------------------------------------------------
# Room management
# ---------------------------------------------------------------------------


@router.post("/rooms", response_model=RoomCreateResponse, status_code=201)
async def create_room(
    body: RoomCreateRequest,
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
    redis=Depends(get_redis),
) -> dict:
    session = await game_service.create_room(
        db=db,
        redis=redis,
        host=user,
        game_id=body.game_id,
        course_id=body.course_id,
        max_rooms=settings.MAX_ROOMS,
    )
    return {"room_code": session.room_code, "session_id": session.id}


@router.get("/rooms/{room_code}/ping")
async def ping_room(
    room_code: str,
    redis=Depends(get_redis),
) -> dict:
    """Public endpoint — no auth required. Confirms a room is joinable."""
    from ..services.state_service import get_room_state
    from ..common.exceptions import NotFoundError as _NF, ConflictError as _CE

    state = await get_room_state(redis, room_code.upper())
    if not state:
        raise _NF(f"Room '{room_code}' not found")
    if state.get("status") not in ("LOBBY", "IN_PROGRESS"):
        raise _CE("This game has already ended")
    return {"status": state.get("status")}


@router.get("/rooms/{room_code}", response_model=RoomInfoResponse)
async def get_room(
    room_code: str,
    _: Annotated[User, Depends(get_current_user)],
    db: DbSession,
    redis=Depends(get_redis),
) -> dict:
    """Get session metadata for reconnection. Any authenticated user can call this."""
    session, _ = await game_service.get_session_by_code(db, redis, room_code.upper())

    # Fetch related records for the response
    game = await db.get(Game, session.game_id)
    course = await db.get(Course, session.course_id)

    q_count_result = await db.execute(
        select(Question).where(Question.game_id == session.game_id)
    )
    question_count = len(q_count_result.scalars().all())

    return {
        "session_id": session.id,
        "room_code": session.room_code,
        "status": session.status,
        "game_title": game.title if game else "Unknown",
        "course_id": session.course_id,
        "course_name": course.name if course else "Unknown",
        "course_semester": course.semester if course else "",
        "question_count": question_count,
    }


# ---------------------------------------------------------------------------
# Post-game guest reconciliation (host-facing)
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/guests")
async def list_session_guests(
    session_id: str,
    _: Annotated[User, Depends(require_session_host)],
    db: DbSession,
) -> list[dict]:
    """List unmerged guest players from a completed session."""
    from ..models.session import SessionScore
    from ..models.user import User as UserModel

    result = await db.execute(
        select(UserModel)
        .join(SessionScore, SessionScore.user_id == UserModel.id)
        .where(
            SessionScore.session_id == session_id,
            UserModel.role == "GUEST",
        )
        .distinct()
    )
    guests = result.scalars().all()
    return [
        {
            "id": g.id,
            "display_name": g.display_name,
            "email": g.email,
        }
        for g in guests
    ]


@router.post("/sessions/{session_id}/merge-guest", status_code=204)
async def merge_guest_for_session(
    session_id: str,
    body: dict,
    _: Annotated[User, Depends(require_session_host)],
    db: DbSession,
) -> None:
    """Host-initiated guest merge, scoped to THIS session: re-attribute the guest's answers
    in this session to the real account with `target_netid`.

    Unlike admin.merge_guest (a global identity merge an admin may do across every
    session), a host may only move rows of a session they hosted. The guest account is
    deleted only once it has no answers left anywhere; it is never promoted here, since
    promotion would change the guest's identity in other hosts' sessions too.
    """
    from ..models.session import SessionScore
    from ..models.user import User as UserModel

    # Existence and "ADMIN or this session's host" are checked by require_session_host.
    session = await db.get(GameSession, session_id)
    # A live session's scores also live in Redis under the guest's id; merging mid-game
    # would split the guest's state between the two stores.
    if session.status != "COMPLETED":
        raise ConflictError("Guests can only be merged once the session has finished")

    guest_user_id: str = body.get("guest_user_id", "")
    target_netid: str = (body.get("target_netid") or "").strip().lower()

    if not guest_user_id or not target_netid:
        raise ConflictError("guest_user_id and target_netid are required")

    guest = await db.get(UserModel, guest_user_id)
    if not guest or guest.role != "GUEST":
        raise NotFoundError(f"Guest user {guest_user_id} not found")

    real_user = await db.scalar(
        select(UserModel).where(UserModel.netid == target_netid)
    )
    if not real_user:
        raise NotFoundError(f"No user with netid '{target_netid}' found")

    # Two rows for the same player and question would count twice (nothing in the
    # schema prevents it), so refuse if the account already answered in this session.
    already = await db.scalar(
        select(func.count(SessionScore.id)).where(
            SessionScore.session_id == session_id,
            SessionScore.user_id == real_user.id,
        )
    )
    if already:
        raise ConflictError(f"'{target_netid}' already has answers in this session")

    rows = (
        (
            await db.execute(
                select(SessionScore).where(
                    SessionScore.session_id == session_id,
                    SessionScore.user_id == guest_user_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise NotFoundError(f"Guest {guest_user_id} has no answers in this session")
    for score in rows:
        score.user_id = real_user.id
    await db.flush()

    # Answers in other sessions stay with the guest (their hosts, or an admin, can merge
    # them). session_scores.user_id has no ON DELETE, so the guest can only be deleted
    # once nothing references it.
    remaining = await db.scalar(
        select(func.count(SessionScore.id)).where(SessionScore.user_id == guest_user_id)
    )
    if not remaining:
        await db.delete(guest)
    logger.info(
        "guest_merged_by_host",
        guest_id=guest_user_id,
        real_user_id=real_user.id,
        session_id=session_id,
        moved=len(rows),
        guest_deleted=not remaining,
    )


# ---------------------------------------------------------------------------
# Session score export
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/export")
async def export_session_scores(
    session_id: str,
    _: Annotated[User, Depends(require_session_host)],
    db: DbSession,
) -> StreamingResponse:
    """Download session scores as a CSV. Accessible by the session host or an admin,
    once the session is COMPLETED (T4 D9)."""
    from ..services.export_service import build_session_csv

    await _assert_completed(db, session_id)

    filename, content = await build_session_csv(db, session_id)

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/report")
async def session_report(
    session_id: str,
    _: Annotated[User, Depends(require_session_host)],
    db: DbSession,
) -> Response:
    """Download the standalone, PII-free HTML report of a COMPLETED session (T4 D9)."""
    from ..services.report_service import build_session_report

    await _assert_completed(db, session_id)
    filename, content = await build_session_report(db, session_id)
    return Response(
        content=content,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _assert_completed(db: AsyncSession, session_id: str) -> None:
    # Existence was checked by require_session_host.
    session = await db.get(GameSession, session_id)
    if session.status != "COMPLETED":
        raise ConflictError("Session has not finished yet")
