"""
Game and question business logic shared by the admin and host routers
(docs/plans/t4-ui-restructuring.md §6.2.2, §6.2.5).

The routers translate these functions to HTTP; access control happens before they
are called (route dependencies). Like every service here, functions only flush —
`get_db` (via `database.DbSession`) commits when the handler returns, before the response
is sent. Queries are explicit; relationships are never lazy-loaded (async SQLAlchemy raises
MissingGreenlet).

Phase 2 uses this from routers/host.py; phase 3 switches routers/admin.py over too.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json

import bleach
import structlog
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ConflictError, NotFoundError, RequestBodyInvalidError
from ..models.course import Course, UserCourseAccess
from ..models.game import Game, Question, UserGameAccess
from ..models.image import Image
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.admin import (
    GameMeta,
    GameResponse,
    GameUpdate,
    HostGameItem,
    OPTION_IMAGE_TYPES,
    HostGameUpdate,
    QuestionCreate,
    QuestionUpdate,
)
from . import image_service
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
        await _move_images(db, game_id, new_course)
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


# ---------------------------------------------------------------------------
# Questions (D6, D7, D8, §6.2.5 a)
# ---------------------------------------------------------------------------

# Prompt HTML allowed through the sanitizer (moved from routers/admin.py, which keeps
# its own copy until phase 3 switches it over).
PROMPT_TAGS = ["b", "i", "br", "u"]

# The QuestionCreate fields an update merges onto the stored question: all of them
# except order_index, which only reorder_questions changes (§6.2.5 a).
_MERGE_FIELDS = (
    "type",
    "grading_type",
    "prompt",
    "config",
    "answer_data",
    "time_limit_seconds",
    "points_value",
    "prompt_image_id",
)


def sanitize_prompt(prompt: str) -> str:
    """Strip every tag except b/i/br/u. Runs after validation, so a prompt that is only
    markup (e.g. "<script></script>") is stored empty — existing behaviour, see the
    services README gotcha."""
    return bleach.clean(prompt, tags=PROMPT_TAGS, attributes={}, strip=True)


async def _assert_not_live(db: AsyncSession, redis: Redis, game_id: int) -> None:
    if await has_live_session(db, redis, game_id):
        raise ConflictError("This game has a live session")


async def _get_question(db: AsyncSession, game_id: int, question_id: int) -> Question:
    question = await db.scalar(
        select(Question).where(Question.id == question_id, Question.game_id == game_id)
    )
    if not question:
        raise NotFoundError(f"Question {question_id} not found in game {game_id}")
    return question


async def _questions(db: AsyncSession, game_id: int) -> list[Question]:
    return list(
        (
            await db.execute(
                select(Question)
                .where(Question.game_id == game_id)
                .order_by(Question.order_index, Question.id)
            )
        ).scalars()
    )


async def list_questions(db: AsyncSession, game_id: int) -> list[Question]:
    await _get_game(db, game_id)
    return await _questions(db, game_id)


# ---------------------------------------------------------------------------
# Question images (docs/plans/t8-image-support.md D3, D5)
# ---------------------------------------------------------------------------


async def _check_images(db: AsyncSession, game: Game, question: QuestionCreate) -> None:
    """422 if a (structurally valid) question uses an image that doesn't exist or
    belongs to another course. Runs after QuestionCreate validation, so structural
    errors win."""
    await image_service.assert_usable(
        db,
        game.course_id,
        image_service.question_image_fields(
            question.type, question.config, question.prompt_image_id
        ),
    )


async def create_question(
    db: AsyncSession, redis: Redis, game_id: int, body: QuestionCreate
) -> Question:
    """409 while live. Always appended at max(order_index) + 1; a caller's order_index
    is ignored — reorder_questions is the only way to change position (§6.2.5 a)."""
    game = await _get_game(db, game_id)
    await _assert_not_live(db, redis, game_id)
    await _check_images(db, game, body)
    last = await db.scalar(
        select(func.max(Question.order_index)).where(Question.game_id == game_id)
    )
    question = Question(
        game_id=game_id,
        type=body.type,
        grading_type=body.grading_type,
        prompt=sanitize_prompt(body.prompt),
        config=body.config,
        answer_data=body.answer_data,
        time_limit_seconds=body.time_limit_seconds,
        points_value=body.points_value,
        order_index=0 if last is None else last + 1,
        prompt_image_id=body.prompt_image_id,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)
    return question


async def update_question(
    db: AsyncSession,
    redis: Redis,
    game_id: int,
    question_id: int,
    patch: QuestionUpdate,
) -> Question:
    """D8: 404 if not in this game; 409 while live; 422 for any explicit null and for
    order_index (§6.2.5 a); otherwise merge the sent fields onto the stored question
    and validate the result as a whole with QuestionCreate (422 VALIDATION_ERROR).
    prompt_image_id is the one field where null is allowed: it removes the image (T8 §5)."""
    question = await _get_question(db, game_id, question_id)
    await _assert_not_live(db, redis, game_id)

    sent = patch.model_dump(exclude_unset=True)
    nulls = [
        field
        for field, value in sent.items()
        if value is None and field != "prompt_image_id"
    ]
    if nulls:
        raise RequestBodyInvalidError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", field),
                    "msg": f"{field} cannot be null; omit it to keep the current value",
                    "input": None,
                }
                for field in nulls
            ]
        )
    if "order_index" in sent:
        raise RequestBodyInvalidError.for_field(
            "order_index",
            "order_index can't be changed here; use "
            f"POST /games/{game_id}/questions/reorder",
            sent["order_index"],
        )

    merged = {field: getattr(question, field) for field in _MERGE_FIELDS}
    merged.update(sent)
    try:
        valid = QuestionCreate(**merged)
    except ValidationError as exc:
        raise RequestBodyInvalidError.from_validation_error(exc) from exc
    # Checked on every update, even one that doesn't touch an image: D8 validates the
    # merged question as a whole (t7-hotspot.md §13.2 G7).
    await _check_images(db, await _get_game(db, game_id), valid)

    for field in _MERGE_FIELDS:
        setattr(question, field, getattr(valid, field))
    question.prompt = sanitize_prompt(valid.prompt)
    await db.flush()
    return question


async def delete_question(
    db: AsyncSession, redis: Redis, game_id: int, question_id: int
) -> None:
    """D6: 404; 409 while live; 409 if any answer was recorded for it (deleting scores
    would rewrite completed sessions). Then re-pack the rest to order_index 0..n-1."""
    question = await _get_question(db, game_id, question_id)
    await _assert_not_live(db, redis, game_id)
    answered = await db.scalar(
        select(func.count(SessionScore.id)).where(
            SessionScore.question_id == question_id
        )
    )
    if answered:
        raise ConflictError("Question has recorded answers")
    await db.delete(question)
    await db.flush()
    for index, q in enumerate(await _questions(db, game_id)):
        q.order_index = index
    await db.flush()


async def reorder_questions(
    db: AsyncSession, redis: Redis, game_id: int, order: list[int]
) -> None:
    """409 while live; 409 unless `order` is exactly this game's question ids."""
    await _get_game(db, game_id)
    await _assert_not_live(db, redis, game_id)
    questions = {q.id: q for q in await _questions(db, game_id)}
    if len(order) != len(questions) or set(order) != set(questions):
        raise ConflictError(
            "order list must contain exactly the IDs of all questions in this game"
        )
    for index, qid in enumerate(order):
        questions[qid].order_index = index
    await db.flush()


# ---------------------------------------------------------------------------
# Import / export (D10: bundles never carry course_id; T8 D7: images travel as bytes)
# ---------------------------------------------------------------------------

BUNDLE_FORMAT = "buzzer/game"
# Version 1: no images. Version 2 (docs/plans/t7-hotspot.md §6, docs/plans/
# t8-image-support.md D7): a top-level `images` list, and questions refer to its entries
# by `ref` — `prompt_image_ref`, `config.optionImageRefs`, hotspot `config.imageRef` —
# never by image id, which only means something in the database that wrote it.
BUNDLE_VERSIONS = (1, 2)
_PLACEHOLDER_IMAGE_ID = 1  # stands in for a ref during structural validation


def _exported_question(q: Question, ref) -> dict:
    """One question as a bundle entry; `ref(image_id)` names an image (version 2)."""
    config = dict(q.config or {})
    if q.type in OPTION_IMAGE_TYPES and isinstance(config.get("optionImageIds"), list):
        config["optionImageRefs"] = [
            None if v is None else ref(v) for v in config.pop("optionImageIds")
        ]
    if q.type == "hotspot" and "imageId" in config:
        config = {"imageRef": ref(config["imageId"]), **_without(config, "imageId")}
    item = {
        "type": q.type,
        "grading_type": q.grading_type,
        "prompt": q.prompt,
        "config": config,
        "answer_data": q.answer_data,
        "time_limit_seconds": q.time_limit_seconds,
        "points_value": q.points_value,
    }
    if q.prompt_image_id is not None:
        item["prompt_image_ref"] = ref(q.prompt_image_id)
    return item


def _without(d: dict, key: str) -> dict:
    return {k: v for k, v in d.items() if k != key}


async def export_game(db: AsyncSession, game_id: int) -> tuple[str, bytes]:
    """The game as a bundle: (filename, JSON bytes). No course_id. A game using no
    images is a version-1 bundle exactly as before T8; otherwise version 2, with refs
    img1, img2, … in first-use order (prompt, options, hotspot, question by question)."""
    game = await _get_game(db, game_id)
    refs: dict[int, str] = {}

    def ref(image_id: int) -> str:
        return refs.setdefault(image_id, f"img{len(refs) + 1}")

    questions = [_exported_question(q, ref) for q in await _questions(db, game_id)]
    bundle: dict = {
        "format": BUNDLE_FORMAT,
        "version": 2 if refs else 1,
        "game": {
            "title": game.title,
            "description": game.description,
            "max_players": game.max_players,
        },
    }
    if refs:
        images = []
        for image_id, name in refs.items():
            found = await image_service.get_image(db, image_id)
            if found is None:  # impossible while deletes are refused (C7)
                raise ConflictError(f"A question references missing image {image_id}")
            content_type, data = found
            images.append(
                {
                    "ref": name,
                    "content_type": content_type,
                    "data_base64": base64.b64encode(data).decode("ascii"),
                }
            )
        bundle["images"] = images
    bundle["questions"] = questions
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in game.title)
    return f"{safe_title}.json", json.dumps(
        bundle, indent=2, ensure_ascii=False
    ).encode()


def _invalid_file(msg: str) -> RequestBodyInvalidError:
    # §6.2.5 b: the same messages as the admin import route, as one error on "file".
    return RequestBodyInvalidError.for_field("file", msg)


def _bundle_images(raw_images: object) -> dict[str, tuple[int, bytes]]:
    """Check a v2 `images` list (t7-hotspot.md §6.3.4.1) → {ref: (1-based K, bytes)}.
    `content_type` must be a string but is not trusted: the bytes decide (T8 D7)."""
    if not isinstance(raw_images, list):
        raise _invalid_file("images must be a list")
    images: dict[str, tuple[int, bytes]] = {}
    for k, entry in enumerate(raw_images, start=1):
        if not isinstance(entry, dict):
            raise _invalid_file(f"Image {k}: must be an object")
        name = entry.get("ref")
        if not isinstance(name, str) or not name:
            raise _invalid_file(f"Image {k}: ref must be a non-empty string")
        if name in images:
            raise _invalid_file(f"Image {k}: duplicate ref {name!r}")
        if not isinstance(entry.get("content_type"), str):
            raise _invalid_file(f"Image {k}: content_type must be a string")
        data = entry.get("data_base64")
        try:
            if not isinstance(data, str):
                raise ValueError
            decoded = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            raise _invalid_file(f"Image {k}: data_base64 is not valid base64")
        images[name] = (k, decoded)
    return images


def _bundle_refs(n: int, q: dict, version: int, images: dict) -> dict:
    """Check one question's image fields (T8 D7) → {location: ref} for its refs, where a
    location is "prompt", ("option", i) or "hotspot". Raw image ids are refused in every
    version; refs only exist in version 2 and must name an `images` entry."""
    config = q.get("config") if isinstance(q.get("config"), dict) else {}
    hotspot = q.get("type") == "hotspot"
    if (
        q.get("prompt_image_id") is not None
        or "optionImageIds" in config
        or (version == 2 and hotspot and "imageId" in config)
    ):
        raise _invalid_file(
            f"Question {n}: image IDs can't be imported; export the game "
            "again to get a version 2 file"
        )
    found: dict = {}
    if q.get("prompt_image_ref") is not None:
        found["prompt"] = q["prompt_image_ref"]
    if "optionImageRefs" in config:
        option_refs, options = config["optionImageRefs"], config.get("options")
        if (
            not isinstance(option_refs, list)
            or not isinstance(options, list)
            or len(option_refs) != len(options)
        ):
            raise _invalid_file(
                f"Question {n}: optionImageRefs must be a list the same length as options"
            )
        for i, name in enumerate(option_refs):
            if name is not None:
                found[("option", i)] = name
    if hotspot and "imageRef" in config:
        found["hotspot"] = config["imageRef"]
    if found and version == 1:
        raise _invalid_file(
            f"Question {n}: image references require a version 2 bundle"
        )
    for name in found.values():
        if not isinstance(name, str) or name not in images:
            raise _invalid_file(f"Question {n}: unknown image reference {name!r}")
    return found


def _with_image_ids(q: dict, found: dict, image_ids: dict) -> dict:
    """The question with each ref replaced by an image id (`image_ids[ref]`, or the
    placeholder when validating before any image exists)."""
    q = _without(q, "prompt_image_ref")
    if not found:
        return q
    config = dict(q.get("config") or {})

    def image_id(name: str) -> int:
        return image_ids.get(name, _PLACEHOLDER_IMAGE_ID)

    if "prompt" in found:
        q["prompt_image_id"] = image_id(found["prompt"])
    if "optionImageRefs" in config:
        config["optionImageIds"] = [
            None if name is None else image_id(name)
            for name in config.pop("optionImageRefs")
        ]
    if "hotspot" in found:
        config = {"imageId": image_id(found["hotspot"]), **_without(config, "imageRef")}
    q["config"] = config
    return q


async def import_game(
    db: AsyncSession, actor: User, raw: bytes, course_id: int
) -> Game:
    """Create a new game in `course_id` from a version 1 or 2 bundle (never overwrites).
    404 for an unknown course; every structural problem is a 422 RequestBodyInvalidError
    raised before anything is written; a bad image (checked when it is created) raises
    after, and get_db rolls the whole import back. Referenced images are created in the
    target course, reusing identical ones (T8 D2). Same auto-grant rule as create_game."""
    if not await db.get(Course, course_id):
        raise NotFoundError(f"Course {course_id} not found")
    try:
        bundle = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _invalid_file(f"Invalid JSON: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("format") != BUNDLE_FORMAT:
        raise _invalid_file("Unrecognised file format")
    version = bundle.get("version")
    if isinstance(version, bool) or version not in BUNDLE_VERSIONS:
        raise _invalid_file(
            f"Unsupported version {version!r}; server supports versions 1 and 2"
        )
    try:
        meta = GameMeta(**bundle.get("game", {}))
    except (ValidationError, TypeError) as exc:
        raise _invalid_file(f"Invalid game metadata: {exc}") from exc
    images = _bundle_images(bundle.get("images", [])) if version == 2 else {}
    questions_raw = bundle.get("questions", [])
    if not isinstance(questions_raw, list):
        raise _invalid_file("questions must be a list")

    checked: list[tuple[dict, dict]] = []
    for i, q in enumerate(questions_raw):
        if not isinstance(q, dict):
            raise _invalid_file(f"Question {i + 1} invalid: must be an object")
        # A v1 bundle's imageId would point at an arbitrary image on this server
        # (t7-hotspot.md §6.3.3).
        if version == 1 and q.get("type") == "hotspot":
            raise _invalid_file(
                f"Question {i + 1}: hotspot questions require a version 2 bundle"
            )
        found = _bundle_refs(i + 1, q, version, images)
        try:
            QuestionCreate(**_with_image_ids(q, found, {}))  # schema only
        except (ValidationError, TypeError) as exc:
            raise _invalid_file(f"Question {i + 1} invalid: {exc}") from exc
        checked.append((q, found))

    # Create only the referenced images, in bundle order.
    used = {name for _, found in checked for name in found.values()}
    image_ids: dict[str, int] = {}
    for name, (k, data) in images.items():
        if name not in used:
            continue
        try:
            image, _ = await image_service.create_image(db, course_id, data, actor.id)
        except RequestBodyInvalidError as exc:
            raise _invalid_file(f"Image {k}: {exc.errors[0]['msg']}") from exc
        image_ids[name] = image.id

    game = await create_game(db, actor, meta, course_id)
    for index, (q, found) in enumerate(checked):
        valid = QuestionCreate(**_with_image_ids(q, found, image_ids))
        db.add(
            Question(
                game_id=game.id,
                type=valid.type,
                grading_type=valid.grading_type,
                prompt=sanitize_prompt(valid.prompt),
                config=valid.config,
                answer_data=valid.answer_data,
                time_limit_seconds=valid.time_limit_seconds,
                points_value=valid.points_value,
                order_index=index,
                prompt_image_id=valid.prompt_image_id,
            )
        )
    await db.flush()
    logger.info(
        "game_imported",
        game_id=game.id,
        questions=len(checked),
        images=len(image_ids),
        by=actor.id,
    )
    return game


async def _move_images(db: AsyncSession, game_id: int, course_id: int) -> None:
    """A question may only use its game's course's images (T8 D3), so a game moving to
    another course takes copies of every image it uses, and its questions are repointed.
    The originals stay in the old course."""
    questions = await _questions(db, game_id)
    used: set[int] = set()
    for q in questions:
        used |= image_service.question_image_ids(q.type, q.config, q.prompt_image_id)
    mapping = await image_service.copy_to_course(db, used, course_id)
    for q in questions:
        if q.prompt_image_id in mapping:
            q.prompt_image_id = mapping[q.prompt_image_id]
        q.config = _remapped(q, mapping)
    await db.flush()


def _remapped(question: Question, mapping: dict[int, int]) -> dict:
    """A new config dict with option and hotspot image ids mapped (never mutate the
    loaded JSON in place)."""
    config = dict(question.config or {})
    if question.type in OPTION_IMAGE_TYPES and isinstance(
        config.get("optionImageIds"), list
    ):
        config["optionImageIds"] = [
            mapping.get(v, v) if v is not None else None
            for v in config["optionImageIds"]
        ]
    if question.type == "hotspot" and config.get("imageId") in mapping:
        config["imageId"] = mapping[config["imageId"]]
    return config


# ---------------------------------------------------------------------------
# Image replace (docs/plans/t8-image-support.md D6) — here, not in image_service,
# because it needs games, questions and the live check.
# ---------------------------------------------------------------------------

# Hotspot targets are fractions of the image, so they only stay put if the new image
# has the same shape (relative aspect-ratio difference at most this).
_HOTSPOT_SHAPE_TOLERANCE = 0.01


async def _editable_game_ids(
    db: AsyncSession, actor: User, course_id: int, game_ids: set[int]
) -> set[int]:
    """The games among `game_ids` the actor may edit: all of them for an admin; for a host
    the T4 rule — a game grant and HOST of the game's course (the caller checked HOST of
    `course_id`, and a question may only use its own course's images)."""
    if actor.role == "ADMIN" or not game_ids:
        return set(game_ids)
    rows = await db.execute(
        select(Game.id)
        .join(UserGameAccess, UserGameAccess.game_id == Game.id)
        .where(
            Game.id.in_(game_ids),
            Game.course_id == course_id,
            UserGameAccess.user_id == actor.id,
        )
    )
    return {gid for (gid,) in rows}


def _repointed(question: Question, old: int, new: int, aspect: float) -> dict:
    """Like _remapped for one image; a repointed hotspot also takes the new aspect ratio."""
    config = _remapped(question, {old: new})
    if question.type == "hotspot" and config.get("imageId") == new:
        config["aspectRatio"] = aspect
    return config


async def replace_image(
    db: AsyncSession, redis: Redis, actor: User, old: Image, data: bytes
) -> dict:
    """D6 steps 2–9. `old` is locked and the actor may manage it. Any refusal raises
    before anything is written, and get_db rolls back the transaction anyway."""
    stored, _, width, height = image_service.normalize(data)
    if hashlib.sha256(stored).hexdigest() == old.sha256:
        raise RequestBodyInvalidError.for_field(
            "file", "The new file is identical to the current image"
        )

    references = await image_service.find_references(db, old.id)
    editable = await _editable_game_ids(
        db, actor, old.course_id, {gid for _, gid in references}
    )
    mine = [qid for qid, gid in references if gid in editable]
    if references and not mine:
        n = len(references)
        raise ConflictError(
            "You can't edit the question that uses this image"
            if n == 1
            else f"You can't edit any of the {n} questions that use this image"
        )
    for game_id in sorted(editable):
        await _assert_not_live(db, redis, game_id)

    questions = list(
        (await db.execute(select(Question).where(Question.id.in_(mine)))).scalars()
    )
    old_ratio, new_ratio = old.width / old.height, width / height
    if any(q.type == "hotspot" for q in questions) and (
        abs(new_ratio - old_ratio) / old_ratio > _HOTSPOT_SHAPE_TOLERANCE
    ):
        raise ConflictError(
            "A hotspot question uses this image, and the new image has a different "
            "shape: its target would move"
        )

    target, _ = await image_service.create_image(db, old.course_id, data, actor.id)
    for q in questions:
        if q.prompt_image_id == old.id:
            q.prompt_image_id = target.id
        q.config = _repointed(q, old.id, target.id, target.width / target.height)
    await db.flush()

    old_deleted = not await image_service.find_references(db, old.id)
    if old_deleted:
        await db.delete(old)
        await db.flush()
    logger.info(
        "image_replaced", old=old.id, new=target.id, questions=len(mine), by=actor.id
    )
    return {
        "id": target.id,
        "replaced_id": old.id,
        "repointed_questions": len(mine),
        "old_deleted": old_deleted,
    }
