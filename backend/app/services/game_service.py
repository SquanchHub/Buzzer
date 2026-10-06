from __future__ import annotations

import math
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from rapidfuzz.distance import Levenshtein
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ConflictError, ForbiddenError, NotFoundError
from ..models.course import CourseRoster, UserCourseAccess
from ..models.game import Game, Question, UserGameAccess
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.admin import (
    hotspot_answer_error,
    is_hotspot_aspect_ratio,
    ordering_answer_error,
    ordering_config_error,
)
from ..schemas.game import ScoreResult
from . import state_service as state

logger = structlog.get_logger()

# Character set from spec: unambiguous alphanumeric (no 0/O/1/I/L)
_ROOM_CHARSET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_MAX_CODE_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Room code generation
# ---------------------------------------------------------------------------


async def generate_room_code(redis: Redis) -> str:
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = "".join(secrets.choice(_ROOM_CHARSET) for _ in range(6))
        if not await redis.exists(f"room:{code}"):
            return code
    raise ConflictError("Could not generate a unique room code — try again")


# ---------------------------------------------------------------------------
# Access validation helpers
# ---------------------------------------------------------------------------


async def assert_host_can_use_course(
    db: AsyncSession, user: User, course_id: int
) -> None:
    """Admin can use any course; USER must have HOST role in user_course_access."""
    if user.role == "ADMIN":
        from ..models.course import Course

        course = await db.get(Course, course_id)
        if not course:
            raise NotFoundError(f"Course {course_id} not found")
        return

    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == course_id,
            UserCourseAccess.role == "HOST",
        )
    )
    if not result.scalar_one_or_none():
        raise ForbiddenError("You do not have HOST access to this course")


async def assert_host_can_use_game(db: AsyncSession, user: User, game_id: int) -> None:
    """Admin can use any game. A USER needs BOTH a user_game_access grant AND the
    HOST role on the game's course, so revoking course HOST also revokes the game.
    Unassigned games (course_id NULL) are admin-only. Every non-admin failure gets
    the same message, so it doesn't reveal which grant is missing."""
    game = await db.get(Game, game_id)
    if not game:
        raise NotFoundError(f"Game {game_id} not found")
    if user.role == "ADMIN":
        return

    result = await db.execute(
        select(UserGameAccess)
        .join(
            UserCourseAccess,
            (UserCourseAccess.user_id == UserGameAccess.user_id)
            & (UserCourseAccess.course_id == game.course_id)
            & (UserCourseAccess.role == "HOST"),
        )
        .where(
            UserGameAccess.user_id == user.id,
            UserGameAccess.game_id == game_id,
        )
    )
    if game.course_id is None or not result.scalar_one_or_none():
        raise ForbiddenError("You do not have access to this game")


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


async def create_room(
    db: AsyncSession,
    redis: Redis,
    host: User,
    game_id: int,
    course_id: int,
    max_rooms: int = 50,
) -> GameSession:
    # Validate access
    await assert_host_can_use_course(db, host, course_id)
    await assert_host_can_use_game(db, host, game_id)

    # Invariant (admins included): a session is played in its game's course, so
    # the unchanged roster check in authorise_player admits that course's players.
    game = await db.get(Game, game_id)
    if game.course_id is None:
        raise ConflictError(
            "This game is not assigned to a course; an admin must assign one first"
        )
    if game.course_id != course_id:
        raise ConflictError("This game belongs to a different course")

    # Enforce global room limit — count only LOBBY/IN_PROGRESS rooms.
    # COMPLETED/ABANDONED rooms may linger in Redis briefly for reconnection
    # but do not consume a concurrent-room slot.
    all_room_keys = await redis.keys("room:*")
    room_count = 0
    for key in all_room_keys:
        key_str = key if isinstance(key, str) else key.decode()
        if len(key_str) != 11:  # "room:" (5 chars) + 6-char code
            continue
        room_state_data = await state.get_room_state(redis, key_str[5:])
        if room_state_data and room_state_data.get("status") in (
            "LOBBY",
            "IN_PROGRESS",
        ):
            room_count += 1
    if room_count >= max_rooms:
        raise ConflictError(f"Maximum of {max_rooms} concurrent rooms reached")

    room_code = await generate_room_code(redis)

    session = GameSession(
        id=str(uuid.uuid4()),
        room_code=room_code,
        game_id=game_id,
        course_id=course_id,
        host_user_id=host.id,
        status="LOBBY",
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # Store room state in Redis
    await state.set_room_state(
        redis,
        room_code,
        {
            "session_id": session.id,
            "game_id": game_id,
            "course_id": course_id,
            "host_user_id": host.id,
            "status": "LOBBY",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    logger.info(
        "room_created",
        room_code=room_code,
        session_id=session.id,
        host_id=host.id,
        game_id=game_id,
        course_id=course_id,
    )
    return session


async def get_session_by_code(
    db: AsyncSession, redis: Redis, room_code: str
) -> tuple[GameSession, dict | None]:
    """
    Return (session, redis_state). redis_state is None if Redis has no record
    (session may still be in MySQL as COMPLETED/ABANDONED).
    """
    redis_state = await state.get_room_state(redis, room_code)

    result = await db.execute(
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(selectinload(GameSession.game))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError(f"Room '{room_code}' not found or has expired")

    return session, redis_state


async def start_game(
    db: AsyncSession, redis: Redis, session: GameSession
) -> list[Question]:
    """Transition LOBBY → IN_PROGRESS. Returns ordered question list."""
    if session.status != "LOBBY":
        raise ConflictError(f"Cannot start a game in '{session.status}' state")

    result = await db.execute(
        select(Question)
        .where(Question.game_id == session.game_id)
        .order_by(Question.order_index)
    )
    questions = result.scalars().all()
    if not questions:
        raise ConflictError(
            "This game has no questions — add questions before starting"
        )

    session.status = "IN_PROGRESS"
    # Commit immediately so concurrent on_submit_answer handlers in separate DB
    # sessions see IN_PROGRESS rather than the unflushed LOBBY status.
    await db.commit()

    # Update Redis status
    room_state = await state.get_room_state(redis, session.room_code)
    if room_state:
        room_state["status"] = "IN_PROGRESS"
        await state.set_room_state(redis, session.room_code, room_state)

    logger.info("game_started", session_id=session.id, question_count=len(questions))
    return list(questions)


async def complete_game(db: AsyncSession, redis: Redis, session: GameSession) -> None:
    session.status = "COMPLETED"
    session.completed_at = datetime.now(timezone.utc)
    # Commit so player join attempts racing with game_over see COMPLETED.
    await db.commit()
    logger.info("game_completed", session_id=session.id)
    # Keep Redis state 10 more minutes for reconnection, then let it expire naturally


async def abandon_game(db: AsyncSession, redis: Redis, session: GameSession) -> None:
    session.status = "ABANDONED"
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await state.delete_room_state(redis, session.room_code, session.id)
    logger.info("game_abandoned", session_id=session.id)


# ---------------------------------------------------------------------------
# Player authorisation at join time
# ---------------------------------------------------------------------------


async def authorise_player(db: AsyncSession, user: User, session: GameSession) -> str:
    """
    Check whether the player is permitted to join this session.
    Returns the display name to use for the player.
    Raises ForbiddenError / NotFoundError if not authorised.
    """
    if user.role == "GUEST":
        return user.display_name or "Guest"

    if user.role == "ADMIN":
        return user.display_name or user.username or "Admin"

    # OAuth2 user — check course roster
    if user.netid:
        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == session.course_id,
                CourseRoster.netid == user.netid,
                CourseRoster.is_active == True,  # noqa: E712
            )
        )
        roster_entry = result.scalar_one_or_none()
        if roster_entry:
            return roster_entry.full_name  # first name from CSV

    # Local account with explicit PLAYER role for this course
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == session.course_id,
            UserCourseAccess.role == "PLAYER",
        )
    )
    if result.scalar_one_or_none():
        return user.display_name or user.username or "Player"

    # Local account with HOST role can also join as player
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == session.course_id,
            UserCourseAccess.role == "HOST",
        )
    )
    if result.scalar_one_or_none():
        return user.display_name or user.username or "Host"

    raise ForbiddenError("You are not enrolled in the course roster for this game")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


# Most taps sent to the host per hotspot question (first N in answer order, §7.2).
HOTSPOT_TAP_CAP = 500


@dataclass(frozen=True)
class HotspotTarget:
    """A hotspot question's validated target (docs/plans/t7-hotspot.md §5.2)."""

    x: float
    y: float
    inner_radius: float
    outer_radius: float
    partial_fraction: float
    aspect_ratio: float


def hotspot_target(
    question_id: int, config: object, answer_data: object
) -> HotspotTarget | None:
    """
    Parse an ACCURACY hotspot question's stored target. Returns None — and logs —
    if the stored data breaks the §5.1 rules, so callers score a miss instead of
    crashing mid-game (§5.4). Never raises. A bad imageId is not checked here:
    clients handle that as "Image unavailable".
    """
    aspect = config.get("aspectRatio") if isinstance(config, dict) else None
    if not is_hotspot_aspect_ratio(aspect) or hotspot_answer_error(answer_data):
        logger.warning("hotspot_target_invalid", question_id=question_id)
        return None
    # Both checks passed, so every value below is a bounded finite number.
    return HotspotTarget(
        x=float(answer_data["x"]),
        y=float(answer_data["y"]),
        inner_radius=float(answer_data["innerRadius"]),
        outer_radius=float(answer_data["outerRadius"]),
        partial_fraction=float(answer_data["partialFraction"]),
        aspect_ratio=float(aspect),
    )


def hotspot_band(target: HotspotTarget, px: float, py: float) -> str:
    """
    Band of a tap at normalised (px, py): "inner", "outer" or "miss".
    Distance is measured in units of the image's longer side (§5.2), so the
    rings are true circles on screen. Both boundaries are inclusive.
    """
    a = target.aspect_ratio
    if a >= 1:  # landscape or square: width is the longer side
        dx = px - target.x
        dy = (py - target.y) / a
    else:  # portrait: height is the longer side
        dx = (px - target.x) * a
        dy = py - target.y
    d = math.sqrt(dx * dx + dy * dy)
    if d <= target.inner_radius:
        return "inner"
    if d <= target.outer_radius:
        return "outer"
    return "miss"


def hotspot_reveal(target: HotspotTarget | None) -> dict:
    """
    The client-safe ACCURACY hotspot reveal, shared by every reveal builder
    (§7.4, §13.1 b). partialFraction is never revealed. With an invalid target
    there is nothing to draw, so the reveal carries no target fields (§5.4).
    """
    if target is None:
        return {"type": "hotspot"}
    return {
        "type": "hotspot",
        "x": target.x,
        "y": target.y,
        "innerRadius": target.inner_radius,
        "outerRadius": target.outer_radius,
    }


def _is_unit_coordinate(value: object) -> bool:
    """int or float (not bool), finite, in [0, 1]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 0 <= value <= 1 and (isinstance(value, int) or math.isfinite(value))


def hotspot_tap(answer_data: object) -> tuple[float, float] | None:
    """A player's tap as (x, y), or None if it is missing or malformed (§7.4)."""
    if not isinstance(answer_data, dict):
        return None
    x, y = answer_data.get("x"), answer_data.get("y")
    if not (_is_unit_coordinate(x) and _is_unit_coordinate(y)):
        return None
    return float(x), float(y)


def hotspot_tap_band(
    grading_type: str, target: HotspotTarget | None, tap: tuple[float, float]
) -> str | None:
    """
    The band shown for one tap: None under COMPLETENESS (there is no target),
    "miss" when the ACCURACY target is invalid (§5.4), otherwise hotspot_band.
    Callers get `target` from hotspot_target only under ACCURACY.
    """
    if grading_type == "COMPLETENESS":
        return None
    if target is None:
        return "miss"
    return hotspot_band(target, *tap)


# ---------------------------------------------------------------------------
# Ordering (docs/plans/t7-ordering.md §4, §6.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrderingKey:
    """An ACCURACY ordering question's validated answer key (§4.1).
    correct_order[k] is the display index of the item that belongs at position k."""

    correct_order: tuple[int, ...]
    partial_credit: bool


@dataclass(frozen=True)
class OrderingResult:
    """How one submitted order compares with the key (§4.3)."""

    in_order: int  # L: length of the longest run in correct relative order
    total: int  # n
    out_of_place: tuple[int, ...]  # display indices, in submission order

    @property
    def exact(self) -> bool:
        return self.in_order == self.total


def ordering_item_count(question_id: int, config: object) -> int | None:
    """Number of items in a stored ordering config, or None (logged) if it is invalid."""
    if ordering_config_error(config) is not None:
        logger.warning("ordering_config_invalid", question_id=question_id)
        return None
    return len(config["items"])


def ordering_key(
    question_id: int, config: object, answer_data: object
) -> OrderingKey | None:
    """
    Parse an ACCURACY ordering question's stored key. Returns None — and logs — if the
    stored data breaks the §4.1 rules, so callers score a miss instead of crashing
    mid-game (§4.6). Never raises. Call only under ACCURACY.
    """
    if ordering_answer_error(config, answer_data) is not None:
        logger.warning("ordering_key_invalid", question_id=question_id)
        return None
    return OrderingKey(
        correct_order=tuple(answer_data["correctOrder"]),
        partial_credit=answer_data["partialCredit"],
    )


def ordering_submission(answer_data: object, n: int) -> tuple[int, ...] | None:
    """A player's submitted order, or None unless it is a permutation of 0..n-1 (§4.2)."""
    if not isinstance(answer_data, dict):
        return None
    order = answer_data.get("order")
    if not isinstance(order, list) or not all(
        isinstance(i, int) and not isinstance(i, bool) for i in order
    ):
        return None
    if sorted(order) != list(range(n)):
        return None
    return tuple(order)


def ordering_result(key: OrderingKey, order: tuple[int, ...]) -> OrderingResult:
    """
    Longest in-order run of a valid submission, with the §4.3 tie-break deciding which
    items count as out of place: start at the earliest index that begins a longest run,
    then repeatedly take the earliest later index that continues one.
    """
    rank = {d: k for k, d in enumerate(key.correct_order)}
    r = [rank[d] for d in order]
    n = len(r)
    best = [1] * n  # best[i]: longest increasing run starting at i
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, n):
            if r[j] > r[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
    length = max(best)
    chosen: set[int] = set()
    i = next(k for k in range(n) if best[k] == length)
    chosen.add(i)
    while best[i] > 1:
        i = next(j for j in range(i + 1, n) if r[j] > r[i] and best[j] == best[i] - 1)
        chosen.add(i)
    out = tuple(order[k] for k in range(n) if k not in chosen)
    return OrderingResult(in_order=length, total=n, out_of_place=out)


def ordering_points(
    key: OrderingKey, result: OrderingResult, points_value: float
) -> ScoreResult:
    """§4.4: exact → full points; else (L−1)/(n−1) of them with partial credit, or 0."""
    if result.exact:
        return ScoreResult(points_awarded=points_value, is_correct=True)
    if key.partial_credit:
        fraction = (result.in_order - 1) / (result.total - 1)
        return ScoreResult(
            points_awarded=round(points_value * fraction, 2), is_correct=False
        )
    return ScoreResult(points_awarded=0, is_correct=False)


def ordering_reveal(key: OrderingKey | None) -> dict:
    """The client-safe ACCURACY ordering reveal, shared by every reveal builder.
    partialCredit is never revealed; an invalid key reveals no order (§4.6)."""
    if key is None:
        return {"type": "ordering"}
    return {"type": "ordering", "correctOrder": list(key.correct_order)}


def ordering_outcome(result: OrderingResult | None) -> dict | None:
    """A player's own result label data (O10), or None."""
    if result is None:
        return None
    return {
        "inOrder": result.in_order,
        "total": result.total,
        "outOfPlace": list(result.out_of_place),
    }


def ordering_dist_key(result: OrderingResult) -> str:
    """Distribution bucket: number of items out of place ("0" = perfect)."""
    return str(result.total - result.in_order)


def ordering_mean_positions(
    n: int, orders: list[tuple[int, ...]]
) -> list[float | None]:
    """For each display index, the average 1-based position players gave it (O9)."""
    if not orders:
        return [None] * n
    return [
        round(sum(order.index(d) + 1 for order in orders) / len(orders), 2)
        for d in range(n)
    ]


def calculate_score(question: Question, answer_data: dict) -> ScoreResult:
    """
    Calculate points for a player's answer.
    COMPLETENESS: any answer = full points, no answer = 0
    ACCURACY:     points come from answer_data.answer_points per selected option
    """
    if not answer_data:
        return ScoreResult(points_awarded=0, is_correct=False)

    if question.grading_type == "COMPLETENESS":
        return ScoreResult(points_awarded=question.points_value, is_correct=True)

    # ACCURACY
    if question.type == "multiple_choice":
        selected = answer_data.get("selectedIndex")
        if selected is None:
            return ScoreResult(points_awarded=0, is_correct=False)
        pts_list: list[float] = question.answer_data.get("answer_points", [])
        if not (0 <= selected < len(pts_list)):
            return ScoreResult(points_awarded=0, is_correct=False)
        points = pts_list[selected]
        return ScoreResult(
            points_awarded=points,
            is_correct=(points == question.points_value),
        )

    if question.type == "true_false":
        selected = answer_data.get("selectedValue")
        if selected is None:
            return ScoreResult(points_awarded=0, is_correct=False)
        pts_map: dict = question.answer_data.get("answer_points", {})
        key = "true" if selected else "false"
        points = pts_map.get(key, 0)
        return ScoreResult(
            points_awarded=points,
            is_correct=(points == question.points_value),
        )

    if question.type == "fill_in_the_blank":
        text = " ".join((answer_data.get("text") or "").lower().split())
        if not text:
            return ScoreResult(points_awarded=0, is_correct=False)
        accepted = [
            " ".join(a.lower().split())
            for a in question.answer_data.get("acceptedAnswers", [])
        ]
        answer_pts: list[float] = question.answer_data.get("answerPoints", [])
        max_dist = int(question.answer_data.get("editDistance", 0))
        best: float = 0.0
        for i, a in enumerate(accepted):
            if Levenshtein.distance(text, a) <= max_dist:
                pts = answer_pts[i] if i < len(answer_pts) else question.points_value
                best = max(best, pts)
        return ScoreResult(
            points_awarded=best,
            is_correct=(best >= question.points_value),
        )

    if question.type == "multi_select":
        selected = answer_data.get("selectedIndices")
        if not isinstance(selected, list):
            return ScoreResult(points_awarded=0, is_correct=False)
        pts_list: list[float] = question.answer_data.get("answer_points", [])
        raw = sum(
            pts_list[i]
            for i in selected
            if isinstance(i, int) and 0 <= i < len(pts_list)
        )
        score = max(0.0, raw)
        return ScoreResult(
            points_awarded=score,
            is_correct=(score >= question.points_value and question.points_value > 0),
        )

    if question.type == "hotspot":
        tap = hotspot_tap(answer_data)
        if tap is None:  # defensive: the gateway already rejects malformed taps
            return ScoreResult(points_awarded=0, is_correct=False)
        target = hotspot_target(question.id, question.config, question.answer_data)
        if target is None:  # bad stored target: score as a miss (§5.4)
            return ScoreResult(points_awarded=0, is_correct=False)
        band = hotspot_band(target, *tap)
        if band == "inner":
            return ScoreResult(points_awarded=question.points_value, is_correct=True)
        if band == "outer":
            return ScoreResult(
                points_awarded=question.points_value * target.partial_fraction,
                is_correct=False,
            )
        return ScoreResult(points_awarded=0, is_correct=False)

    if question.type == "ordering":
        key = ordering_key(question.id, question.config, question.answer_data)
        if key is None:  # bad stored key: score as a miss (§4.6)
            return ScoreResult(points_awarded=0, is_correct=False)
        order = ordering_submission(answer_data, len(key.correct_order))
        if order is None:  # defensive: the gateway already rejects these
            return ScoreResult(points_awarded=0, is_correct=False)
        return ordering_points(key, ordering_result(key, order), question.points_value)

    return ScoreResult(points_awarded=0, is_correct=False)


async def record_answer(
    db: AsyncSession,
    redis: Redis,
    session_id: str,
    user_id: str,
    question: Question,
    answer_data: dict,
    answer_time_ms: int | None,
) -> ScoreResult:
    """
    Score an answer, write it to MySQL immediately, and update Redis score.
    Returns the score result.
    """
    result = calculate_score(question, answer_data)

    # Persist to MySQL immediately (per-question persistence guarantee)
    score_row = SessionScore(
        session_id=session_id,
        user_id=user_id,
        question_id=question.id,
        points_awarded=result.points_awarded,
        answer_time_ms=answer_time_ms,
        is_correct=result.is_correct,
        answer_data=answer_data or None,
    )
    db.add(score_row)
    await db.flush()

    # Update Redis running score and answered set
    await state.update_player_score(redis, session_id, user_id, result.points_awarded)
    await state.mark_answered(redis, session_id, question.id, user_id)

    # Increment per-option distribution counter for the results bar chart
    dist_key: str | None = None
    if question.type == "multiple_choice":
        idx = answer_data.get("selectedIndex")
        if idx is not None:
            dist_key = str(idx)
    elif question.type == "true_false":
        val = answer_data.get("selectedValue")
        if val is not None:
            dist_key = "true" if val else "false"
    elif question.type == "fill_in_the_blank":
        text = " ".join((answer_data.get("text") or "").lower().split())
        if text:
            dist_key = text
    elif question.type == "multi_select":
        indices = answer_data.get("selectedIndices")
        if isinstance(indices, list):
            for idx in indices:
                if isinstance(idx, int):
                    await state.increment_answer_dist(
                        redis, session_id, question.id, str(idx)
                    )
    elif question.type == "hotspot" and question.grading_type == "ACCURACY":
        # Band counts; under COMPLETENESS there is no target, so no key.
        tap = hotspot_tap(answer_data)
        if tap is not None:
            target = hotspot_target(question.id, question.config, question.answer_data)
            dist_key = hotspot_tap_band(question.grading_type, target, tap)
    elif question.type == "ordering" and question.grading_type == "ACCURACY":
        # "Items out of place" counts; no key under COMPLETENESS or a bad stored key.
        key = ordering_key(question.id, question.config, question.answer_data)
        if key is not None:
            order = ordering_submission(answer_data, len(key.correct_order))
            if order is not None:
                dist_key = ordering_dist_key(ordering_result(key, order))
    if dist_key is not None:
        await state.increment_answer_dist(redis, session_id, question.id, dist_key)

    return result


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


async def get_leaderboard(db: AsyncSession, session_id: str) -> list[dict]:
    """
    Aggregate session_scores from MySQL to produce a leaderboard.
    Used for QUESTION_RESULTS and GAME_OVER broadcasts.
    """
    from sqlalchemy import func as sqlfunc

    rows = await db.execute(
        select(
            SessionScore.user_id,
            sqlfunc.sum(SessionScore.points_awarded).label("total_score"),
        )
        .where(SessionScore.session_id == session_id)
        .group_by(SessionScore.user_id)
        .order_by(sqlfunc.sum(SessionScore.points_awarded).desc())
    )
    return [{"user_id": r.user_id, "score": float(r.total_score or 0)} for r in rows]


async def get_player_question_summary(
    db: AsyncSession, session_id: str, user_id: str
) -> list[dict]:
    """
    Per-question breakdown for a single player — used in GAME_OVER payload.
    """
    rows = await db.execute(
        select(
            Question.id.label("question_id"),
            Question.prompt,
            Question.points_value,
            Question.type.label("q_type"),
            Question.grading_type,
            Question.config,
            Question.answer_data.label("q_answer_data"),
            SessionScore.points_awarded,
            SessionScore.answer_time_ms,
            SessionScore.answer_data.label("player_answer"),
        )
        .join(GameSession, GameSession.game_id == Question.game_id)
        .outerjoin(
            SessionScore,
            (SessionScore.question_id == Question.id)
            & (SessionScore.session_id == session_id)
            & (SessionScore.user_id == user_id),
        )
        .where(GameSession.id == session_id)
        .order_by(Question.order_index)
    )

    result = []
    for r in rows:
        q_type = r.q_type
        grading_type = r.grading_type
        q_ans = r.q_answer_data or {}
        pts_val = r.points_value

        if grading_type == "COMPLETENESS":
            reveal: dict = {"type": "completeness"}
        elif q_type == "multiple_choice":
            pts = q_ans.get("answer_points", [])
            correct_indices = [i for i, p in enumerate(pts) if p >= pts_val]
            reveal = {"type": "multiple_choice", "correctIndices": correct_indices}
        elif q_type == "true_false":
            pts_map = q_ans.get("answer_points", {})
            correct_true = pts_map.get("true", 0) >= pts_val
            reveal = {"type": "true_false", "correctValue": correct_true}
        elif q_type == "fill_in_the_blank":
            reveal = {
                "type": "fill_in_the_blank",
                "acceptedAnswers": q_ans.get("acceptedAnswers", []),
                "editDistance": q_ans.get("editDistance", 0),
            }
        elif q_type == "multi_select":
            reveal = {
                "type": "multi_select",
                "answerPoints": q_ans.get("answer_points", []),
            }
        elif q_type == "hotspot":
            reveal = hotspot_reveal(hotspot_target(r.question_id, r.config, q_ans))
        else:
            reveal = {}

        result.append(
            {
                "questionId": r.question_id,
                "prompt": r.prompt,
                "type": q_type,
                "gradingType": grading_type,
                "config": r.config or {},
                "pointsAwarded": r.points_awarded or 0,
                "maxPoints": pts_val,
                "answerTimeMs": r.answer_time_ms,
                "playerAnswer": r.player_answer,
                "answerReveal": reveal,
            }
        )

    return result


async def get_host_question_summary(
    db: AsyncSession, session_id: str, total_players: int
) -> list[dict]:
    """Per-question breakdown for the host game-over screen.
    Returns prompt, answer reveal, distribution, and correct/answered counts."""
    from collections import defaultdict

    rows = await db.execute(
        select(
            Question.id.label("question_id"),
            Question.order_index,
            Question.prompt,
            Question.type.label("q_type"),
            Question.grading_type,
            Question.config,
            Question.answer_data.label("q_answer_data"),
            Question.points_value,
            SessionScore.id.label("score_id"),
            SessionScore.user_id,
            SessionScore.points_awarded,
            SessionScore.answer_data.label("player_answer"),
            SessionScore.answer_time_ms,
            SessionScore.is_correct,
        )
        .join(GameSession, GameSession.game_id == Question.game_id)
        .outerjoin(
            SessionScore,
            (SessionScore.question_id == Question.id)
            & (SessionScore.session_id == session_id),
        )
        .where(GameSession.id == session_id)
        .order_by(Question.order_index)
    )

    questions_meta: dict[int, dict] = {}
    questions_order: list[int] = []
    scores_by_q: dict[int, list[dict]] = defaultdict(list)

    for r in rows:
        qid = r.question_id
        if qid not in questions_meta:
            questions_meta[qid] = {
                "order_index": r.order_index,
                "prompt": r.prompt,
                "type": r.q_type,
                "grading_type": r.grading_type,
                "config": r.config or {},
                "answer_data": r.q_answer_data or {},
                "points_value": r.points_value,
            }
            questions_order.append(qid)
        if r.user_id is not None:
            scores_by_q[qid].append(
                {
                    "score_id": r.score_id,
                    "player_answer": r.player_answer,
                    "is_correct": bool(r.is_correct),
                    "answer_time_ms": r.answer_time_ms,
                }
            )

    result = []
    for qnum, qid in enumerate(questions_order, start=1):
        q = questions_meta[qid]
        scores = scores_by_q[qid]
        q_type = q["type"]
        q_ans = q["answer_data"]
        pts_val = q["points_value"]
        grading_type = q["grading_type"]
        hs_target: HotspotTarget | None = None
        if q_type == "hotspot" and grading_type == "ACCURACY":
            hs_target = hotspot_target(qid, q["config"], q_ans)

        if grading_type == "COMPLETENESS":
            reveal: dict = {"type": "completeness"}
        elif q_type == "multiple_choice":
            pts_list = q_ans.get("answer_points", [])
            reveal = {
                "type": "multiple_choice",
                "correctIndices": [i for i, p in enumerate(pts_list) if p >= pts_val],
            }
        elif q_type == "true_false":
            pts_map = q_ans.get("answer_points", {})
            reveal = {
                "type": "true_false",
                "correctValue": pts_map.get("true", 0) >= pts_val,
            }
        elif q_type == "fill_in_the_blank":
            reveal = {
                "type": "fill_in_the_blank",
                "acceptedAnswers": q_ans.get("acceptedAnswers", []),
                "editDistance": q_ans.get("editDistance", 0),
            }
        elif q_type == "multi_select":
            reveal = {
                "type": "multi_select",
                "answerPoints": q_ans.get("answer_points", []),
            }
        elif q_type == "hotspot":
            reveal = hotspot_reveal(hs_target)
        else:
            reveal = {}

        dist: dict[str, int] = {}
        hs_taps: list[tuple[int, dict]] = []  # (score_id, tap) for hotspot
        correct_count = 0
        total_time = 0
        time_count = 0
        for s in scores:
            ans = s["player_answer"]
            if ans:
                if q_type == "multiple_choice":
                    idx = ans.get("selectedIndex")
                    if idx is not None:
                        k = str(idx)
                        dist[k] = dist.get(k, 0) + 1
                elif q_type == "true_false":
                    val = ans.get("selectedValue")
                    if val is not None:
                        k = "true" if val else "false"
                        dist[k] = dist.get(k, 0) + 1
                elif q_type == "fill_in_the_blank":
                    text = (ans.get("text") or "").strip().lower()
                    if text:
                        dist[text] = dist.get(text, 0) + 1
                elif q_type == "multi_select":
                    indices = ans.get("selectedIndices")
                    if isinstance(indices, list):
                        for idx in indices:
                            if isinstance(idx, int):
                                k = str(idx)
                                dist[k] = dist.get(k, 0) + 1
                elif q_type == "hotspot":
                    tap = hotspot_tap(ans)
                    if tap is not None:
                        band = hotspot_tap_band(grading_type, hs_target, tap)
                        if band is not None:  # band counts cover every row
                            dist[band] = dist.get(band, 0) + 1
                        hs_taps.append(
                            (s["score_id"], {"x": tap[0], "y": tap[1], "band": band})
                        )
            if s["is_correct"]:
                correct_count += 1
            if s["answer_time_ms"] is not None:
                total_time += s["answer_time_ms"]
                time_count += 1

        result.append(
            {
                "questionId": qid,
                "questionNumber": qnum,
                "prompt": q["prompt"],
                "type": q_type,
                "gradingType": grading_type,
                "config": q["config"],
                "pointsValue": pts_val,
                "answerReveal": reveal,
                "answerDistribution": dist,
                "totalAnswered": len(scores),
                "totalPlayers": total_players,
                "correctCount": correct_count,
                "avgAnswerTimeMs": round(total_time / time_count)
                if time_count
                else None,
            }
        )
        if q_type == "hotspot":
            hs_taps.sort(key=lambda t: t[0])  # answer order
            result[-1]["taps"] = [tap for _, tap in hs_taps[:HOTSPOT_TAP_CAP]]

    return result
