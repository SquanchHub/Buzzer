from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from ..common.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from ..database import DbSession
from ..models.course import Course
from ..models.session import GameSession
from ..models.user import User
from ..services import game_service
from ..services.auth_service import decode_token, get_user_by_id

logger = structlog.get_logger()

_bearer = HTTPBearer(auto_error=False)


async def _token_from_request(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Extract JWT from Authorization header or access_token cookie."""
    if credentials:
        return credentials.credentials
    return access_token


async def get_current_user(
    token: Annotated[str | None, Depends(_token_from_request)],
    db: DbSession,
) -> User:
    if not token:
        raise UnauthorizedError("Authentication required")
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")

    token_type = payload.get("token_type")
    if token_type not in ("access", "temp"):
        raise UnauthorizedError("Invalid token type")

    user = await get_user_by_id(db, payload["sub"])
    if not user:
        raise UnauthorizedError("User not found")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != "ADMIN":
        raise ForbiddenError("Admin access required")
    return user


async def require_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Allow ADMIN and USER roles; reject GUEST."""
    if user.role == "GUEST":
        raise ForbiddenError("Authenticated account required")
    return user


# ---------------------------------------------------------------------------
# Course / game / session scoped checks (docs/plans/t4-ui-restructuring.md §6.2.1)
#
# Each reads its id from the route's path parameter of the same name and returns the
# User. Admins pass every check (they bypass the course and game layers everywhere).
# ---------------------------------------------------------------------------


async def require_course_host(
    course_id: int,
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> User:
    """404 if the course doesn't exist — for everyone, admins included, so a path-based
    course endpoint never answers 403 for a nonexistent course (this confirms course
    ids exist to any signed-in user; courses are not secret). Then 403 unless HOST."""
    if not await db.get(Course, course_id):
        raise NotFoundError(f"Course {course_id} not found")
    await game_service.assert_host_can_use_course(db, user, course_id)
    return user


async def require_game_access(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> User:
    """404 if the game doesn't exist; otherwise a non-admin needs both the game grant and
    HOST on the game's course (D1), with one 403 message for every missing piece."""
    await game_service.assert_host_can_use_game(db, user, game_id)
    return user


async def require_session_host(
    session_id: str,
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> User:
    """404 if the session doesn't exist; 403 unless ADMIN or the session's host."""
    session = await db.get(GameSession, session_id)
    if not session:
        raise NotFoundError(f"Session {session_id} not found")
    if user.role != "ADMIN" and session.host_user_id != user.id:
        raise ForbiddenError("Only the session host can access this session")
    return user


async def get_refresh_token(
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> str:
    if not refresh_token:
        raise UnauthorizedError("No refresh token")
    return refresh_token
