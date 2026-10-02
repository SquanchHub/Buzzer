"""
/api/host — course content management for hosts (docs/plans/t4-ui-restructuring.md §6.2.3).

Every endpoint is gated by a course/game dependency from common/dependencies.py (or by
require_user plus assert_host_can_use_course for the two that take the course in the
body); none uses require_admin, and admins pass every check. Handlers only translate
content_service / roster_service calls to HTTP.

INTERIM (T4 §6.2.5 k): every mutating handler commits before it returns. get_db's own commit
runs only after the response has been sent (FastAPI 0.142), so a client that reads right
after a write could miss it. Services still only flush. Once fix/get-db-commit-timing makes
get_db commit before the response, these commits are harmless no-ops (nothing left to flush).
"""

from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import (
    require_course_host,
    require_game_access,
    require_user,
)
from ..common.exceptions import NotFoundError
from ..database import get_db
from ..models.course import CourseRoster
from ..models.game import Game, Question
from ..models.user import User
from ..redis_client import get_redis
from ..schemas.admin import (
    GameCreate,
    GameMeta,
    GameResponse,
    HostGameItem,
    HostGameUpdate,
    QuestionCreate,
    QuestionReorder,
    QuestionResponse,
    QuestionUpdate,
    RosterEntryPatch,
    RosterEntryResponse,
    RosterImportPayload,
    RosterUploadResult,
)
from ..services import content_service, game_service
from ..services.roster_service import process_roster_rows

router = APIRouter(prefix="/host", tags=["host"])

CourseHost = Annotated[User, Depends(require_course_host)]
GameAccess = Annotated[User, Depends(require_game_access)]
Db = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Course roster
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/roster", response_model=list[RosterEntryResponse])
async def list_roster(course_id: int, _: CourseHost, db: Db) -> list[CourseRoster]:
    result = await db.execute(
        select(CourseRoster)
        .where(CourseRoster.course_id == course_id)
        .order_by(CourseRoster.full_name)
    )
    return list(result.scalars())


@router.post("/courses/{course_id}/roster/import", response_model=RosterUploadResult)
async def import_roster(
    course_id: int, payload: RosterImportPayload, _: CourseHost, db: Db
) -> RosterUploadResult:
    """Upsert the uploaded rows; netids missing from the upload are deactivated."""
    rows = [
        {"netid": r.netid, "full_name": r.full_name, "email": r.email}
        for r in payload.rows
    ]
    result = await process_roster_rows(db, course_id, rows)
    await db.commit()  # interim, see module docstring
    return result


@router.patch(
    "/courses/{course_id}/roster/{roster_id}", response_model=RosterEntryResponse
)
async def patch_roster_entry(
    course_id: int,
    roster_id: int,
    body: RosterEntryPatch,
    _: CourseHost,
    db: Db,
) -> CourseRoster:
    # Query on BOTH ids: a HOST of course A must not edit course B's roster by row id.
    entry = await db.scalar(
        select(CourseRoster).where(
            CourseRoster.id == roster_id, CourseRoster.course_id == course_id
        )
    )
    if not entry:
        raise NotFoundError(f"Roster entry {roster_id} not found in course {course_id}")
    if body.is_active is not None:
        entry.is_active = body.is_active
    if body.netid is not None:
        entry.netid = body.netid.strip().lower()
    if body.full_name is not None:
        entry.full_name = body.full_name.strip()
    if body.email is not None:
        entry.email = str(body.email).lower()
    await db.commit()  # interim, see module docstring
    return entry


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/games", response_model=list[HostGameItem])
async def list_course_games(
    course_id: int, user: CourseHost, db: Db
) -> list[HostGameItem]:
    return await content_service.list_course_games(db, user, course_id)


@router.post("/games", response_model=GameResponse, status_code=201)
async def create_game(
    body: GameCreate, user: Annotated[User, Depends(require_user)], db: Db
) -> Game:
    # A non-admin is never HOST of a nonexistent course, so an unknown course_id is a
    # 403 here, not content_service's 404 (§6.4).
    await game_service.assert_host_can_use_course(db, user, body.course_id)
    meta = GameMeta(**body.model_dump(exclude={"course_id"}))
    game = await content_service.create_game(db, user, meta, body.course_id)
    await db.commit()  # interim, see module docstring
    return game


@router.post("/games/import", status_code=201)
async def import_game(
    file: Annotated[UploadFile, File(description="buzzer/game JSON bundle")],
    course_id: Annotated[int, Form(gt=0, description="Course to attach the game to")],
    user: Annotated[User, Depends(require_user)],
    db: Db,
) -> dict:
    await game_service.assert_host_can_use_course(db, user, course_id)
    game = await content_service.import_game(db, user, await file.read(), course_id)
    await db.commit()  # interim, see module docstring
    return {"game_id": game.id}


@router.get("/games/{game_id}", response_model=GameResponse)
async def get_game(game_id: int, _: GameAccess, db: Db) -> Game:
    return await db.get(Game, game_id)  # existence checked by require_game_access


@router.put("/games/{game_id}", response_model=GameResponse)
async def update_game(
    game_id: int,
    body: HostGameUpdate,
    user: GameAccess,
    db: Db,
    redis=Depends(get_redis),
) -> Game:
    game = await content_service.update_game(db, redis, user, game_id, body)
    await db.commit()  # interim, see module docstring
    return game


@router.delete("/games/{game_id}", status_code=204)
async def delete_game(
    game_id: int, user: GameAccess, db: Db, redis=Depends(get_redis)
) -> None:
    await content_service.delete_game(db, redis, user, game_id)
    await db.commit()  # interim, see module docstring


@router.get("/games/{game_id}/export")
async def export_game(game_id: int, _: GameAccess, db: Db) -> StreamingResponse:
    filename, content = await content_service.export_game(db, game_id)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@router.get("/games/{game_id}/questions", response_model=list[QuestionResponse])
async def list_questions(game_id: int, _: GameAccess, db: Db) -> list[Question]:
    return await content_service.list_questions(db, game_id)


@router.post(
    "/games/{game_id}/questions", response_model=QuestionResponse, status_code=201
)
async def create_question(
    game_id: int,
    body: QuestionCreate,
    _: GameAccess,
    db: Db,
    redis=Depends(get_redis),
) -> Question:
    question = await content_service.create_question(db, redis, game_id, body)
    await db.commit()  # interim, see module docstring
    return question


@router.put("/games/{game_id}/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    game_id: int,
    question_id: int,
    body: QuestionUpdate,
    _: GameAccess,
    db: Db,
    redis=Depends(get_redis),
) -> Question:
    question = await content_service.update_question(
        db, redis, game_id, question_id, body
    )
    await db.commit()  # interim, see module docstring
    return question


@router.delete("/games/{game_id}/questions/{question_id}", status_code=204)
async def delete_question(
    game_id: int,
    question_id: int,
    _: GameAccess,
    db: Db,
    redis=Depends(get_redis),
) -> None:
    await content_service.delete_question(db, redis, game_id, question_id)
    await db.commit()  # interim, see module docstring


@router.post("/games/{game_id}/questions/reorder", status_code=204)
async def reorder_questions(
    game_id: int,
    body: QuestionReorder,
    _: GameAccess,
    db: Db,
    redis=Depends(get_redis),
) -> None:
    await content_service.reorder_questions(db, redis, game_id, body.order)
    await db.commit()  # interim, see module docstring
