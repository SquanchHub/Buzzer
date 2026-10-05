"""
Question images stored in MySQL (T8, docs/plans/t8-image-support.md).

Uploads are judged by their bytes, never by file name or declared type (D2):
PNG, JPEG and WebP only, at most MAX_BYTES and MAX_SIDE px per side. An image
carrying metadata (EXIF, XMP, text chunks) is rotated upright and re-saved
without it; otherwise its bytes are stored exactly as uploaded. Identical
stored bytes in one course reuse the existing row.

The bytes under an image ID never change (contract C1 in docs/plans/t7-hotspot.md
§4). Like every service here, this module flushes and never commits.
"""

from __future__ import annotations

import hashlib
import io
import warnings

from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ConflictError, RequestBodyInvalidError
from ..models.game import Game, Question
from ..models.image import Image
from ..models.user import User

MAX_BYTES = 2 * 1024 * 1024
MAX_SIDE = 4096
CONTENT_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}

# Decoding is refused well before a "decompression bomb" could exhaust memory; the
# per-side check below is the real limit, this is the backstop for odd headers.
PILImage.MAX_IMAGE_PIXELS = MAX_SIDE * MAX_SIDE

PAGE_SIZE = 24

_METADATA_KEYS = ("exif", "xmp", "XML:com.adobe.xmp", "comment")


def _invalid(msg: str, field: str = "file") -> RequestBodyInvalidError:
    return RequestBodyInvalidError.for_field(field, msg)


def _has_metadata(img: PILImage.Image) -> bool:
    if len(img.getexif()) or any(k in img.info for k in _METADATA_KEYS):
        return True
    return bool(getattr(img, "text", None))  # PNG tEXt/iTXt/zTXt chunks


def normalize(data: bytes, field: str = "file") -> tuple[bytes, str, int, int]:
    """Validate an upload per D2 → (stored bytes, content type, width, height).

    Raises RequestBodyInvalidError (422) with a message the editors show as is.
    """
    if not data:
        raise _invalid("File is empty", field)
    if len(data) > MAX_BYTES:
        raise _invalid(
            f"Image is {len(data) / 1048576:.1f} MB; the limit is 2 MB", field
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PILImage.DecompressionBombWarning)
            img = PILImage.open(io.BytesIO(data))
            fmt = img.format
            if fmt not in CONTENT_TYPES:
                raise _invalid("File is not a PNG, JPEG or WebP image", field)
            width, height = img.size
            if width > MAX_SIDE or height > MAX_SIDE:
                raise _invalid(
                    f"Image is {width} × {height} px; "
                    f"the limit is {MAX_SIDE} px per side",
                    field,
                )
            if getattr(img, "n_frames", 1) > 1:
                raise _invalid("Animated images are not supported", field)
            img.load()  # full decode: catches truncated or corrupt files
    except RequestBodyInvalidError:
        raise
    except UnidentifiedImageError:
        raise _invalid("File is not a PNG, JPEG or WebP image", field)
    except (
        OSError,
        SyntaxError,
        ValueError,
        PILImage.DecompressionBombError,
        PILImage.DecompressionBombWarning,
    ):
        raise _invalid("Image file is damaged or incomplete", field)

    if not _has_metadata(img):
        return data, CONTENT_TYPES[fmt], width, height

    # Apply the rotation tag so the stored pixels match what browsers show (a phone
    # portrait photo is stored sideways), then save again without metadata.
    upright = ImageOps.exif_transpose(img)
    out = io.BytesIO()
    save: dict = {}
    if "icc_profile" in img.info:  # colour profile, not personal data: keep it
        save["icc_profile"] = img.info["icc_profile"]
    if fmt in ("JPEG", "WEBP"):
        save["quality"] = 90
    upright.save(out, fmt, **save)
    stored = out.getvalue()
    if len(stored) > MAX_BYTES:
        raise _invalid("Image is over 2 MB after removing its metadata", field)
    return stored, CONTENT_TYPES[fmt], upright.width, upright.height


async def _same_bytes(
    db: AsyncSession, course_id: int, sha: str, *, latest: bool = False
) -> Image | None:
    query = select(Image).where(Image.course_id == course_id, Image.sha256 == sha)
    if latest:
        # A locking read sees rows committed after this transaction's snapshot, which
        # a plain SELECT under REPEATABLE READ would miss. Only used once the row is
        # known to exist: on a missing row it would take a gap lock, and two uploads
        # holding gap locks and then inserting deadlock each other.
        query = query.with_for_update(read=True)
    return (await db.execute(query)).scalar_one_or_none()


async def create_image(
    db: AsyncSession,
    course_id: int,
    data: bytes,
    uploaded_by: str | None,
    field: str = "file",
) -> tuple[Image, bool]:
    """Store an image in `course_id` → (row, created). Contract C6: validates per D2,
    raises the 422 error type, flushes, never commits. Identical stored bytes already
    in the course return the existing row with created=False."""
    stored, content_type, width, height = normalize(data, field)
    sha = hashlib.sha256(stored).hexdigest()
    existing = await _same_bytes(db, course_id, sha)
    if existing:
        return existing, False
    image = Image(
        course_id=course_id,
        content_type=content_type,
        data=stored,
        byte_size=len(stored),
        width=width,
        height=height,
        sha256=sha,
        uploaded_by=uploaded_by,
    )
    try:
        async with db.begin_nested():
            db.add(image)
            await db.flush()
    except IntegrityError:
        # Two uploads of the same bytes at once: the other one won the unique key.
        existing = await _same_bytes(db, course_id, sha, latest=True)
        if existing is None:
            raise
        return existing, False
    return image, True


# ---------------------------------------------------------------------------
# Which images a question uses (D5) — the one place that knows the image fields
# ---------------------------------------------------------------------------

ImageField = tuple[tuple, int]  # (location under "body", image id)


def question_image_fields(
    question_type: str, config: object, prompt_image_id: object
) -> list[ImageField]:
    """Every image a question uses, with the request-body location of each: the prompt
    image, option images (multiple_choice / multi_select) and the hotspot image. Never
    raises — malformed data contributes nothing. A new question type with image fields
    registers them here and nowhere else."""
    fields: list[ImageField] = []

    def add(loc: tuple, value: object) -> None:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            fields.append((loc, value))

    add(("prompt_image_id",), prompt_image_id)
    if isinstance(config, dict):
        if question_type in ("multiple_choice", "multi_select"):
            ids = config.get("optionImageIds")
            if isinstance(ids, list):
                for i, value in enumerate(ids):
                    add(("config", "optionImageIds", i), value)
        elif question_type == "hotspot":
            add(("config", "imageId"), config.get("imageId"))
    return fields


def question_image_ids(
    question_type: str, config: object, prompt_image_id: object
) -> set[int]:
    return {
        image_id
        for _, image_id in question_image_fields(question_type, config, prompt_image_id)
    }


async def assert_usable(
    db: AsyncSession, course_id: int | None, fields: list[ImageField]
) -> None:
    """422 unless every image in `fields` exists (contract C4) and belongs to
    `course_id`, the game's course (D3). Locks the image rows FOR SHARE in ascending id
    order, so a concurrent delete or replace of one of them waits for this transaction
    (and two transactions can't each hold a lock the other wants)."""
    if not fields:
        return
    if course_id is None:
        loc, image_id = fields[0]
        raise _field_error(
            loc, "Assign the game to a course before adding images", image_id
        )
    ids = sorted({image_id for _, image_id in fields})
    owners = dict(
        (
            await db.execute(
                select(Image.id, Image.course_id)
                .where(Image.id.in_(ids))
                .order_by(Image.id)
                .with_for_update(read=True)
            )
        ).all()
    )
    for loc, image_id in fields:
        if image_id not in owners:
            raise _field_error(loc, f"Image {image_id} does not exist", image_id)
        if owners[image_id] != course_id:
            raise _field_error(
                loc, f"Image {image_id} belongs to a different course", image_id
            )


def _field_error(loc: tuple, msg: str, value: object) -> RequestBodyInvalidError:
    return RequestBodyInvalidError(
        [{"type": "value_error", "loc": ("body", *loc), "msg": msg, "input": value}]
    )


async def get_image(db: AsyncSession, image_id: int) -> tuple[str, bytes] | None:
    """Contract C5: (content_type, bytes), or None if there is no such image."""
    row = (
        await db.execute(
            select(Image.content_type, Image.data).where(Image.id == image_id)
        )
    ).one_or_none()
    return (row.content_type, row.data) if row else None


async def image_exists(db: AsyncSession, image_id: int) -> bool:
    """Contract C4."""
    return (
        await db.execute(select(Image.id).where(Image.id == image_id))
    ).scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# References, listing and deletion (D4, D5, contract C7)
# ---------------------------------------------------------------------------

# Reverse of question_image_fields, across every question (not only the image's course)
# as a safety net. The type filters matter: other types' config may hold integers that
# are not image ids. tests/integration test 19 checks the two agree.
_REFERENCES_SQL = text(
    """
    SELECT id, game_id FROM questions
    WHERE prompt_image_id = :id
       OR (type = 'hotspot' AND JSON_EXTRACT(config, '$.imageId') = :id)
       OR (type IN ('multiple_choice', 'multi_select')
           AND JSON_CONTAINS(JSON_EXTRACT(config, '$.optionImageIds'), CAST(:id AS JSON)))
    """
)


async def find_references(db: AsyncSession, image_id: int) -> list[tuple[int, int]]:
    """(question_id, game_id) of every question that uses the image."""
    rows = await db.execute(_REFERENCES_SQL, {"id": image_id})
    return [(r.id, r.game_id) for r in rows]


async def course_reference_counts(db: AsyncSession, course_id: int) -> dict[int, int]:
    """How many questions use each image, for the questions of one course's games — all
    the questions that may use the course's images (D3). One query, not one per image."""
    rows = await db.execute(
        select(Question.type, Question.config, Question.prompt_image_id)
        .join(Game, Game.id == Question.game_id)
        .where(Game.course_id == course_id)
    )
    counts: dict[int, int] = {}
    for r in rows:
        for image_id in question_image_ids(r.type, r.config, r.prompt_image_id):
            counts[image_id] = counts.get(image_id, 0) + 1
    return counts


def display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or user.username or user.netid or user.email


def item(image: Image, uploader: User | None, reference_count: int) -> dict:
    return {
        "id": image.id,
        "course_id": image.course_id,
        "content_type": image.content_type,
        "width": image.width,
        "height": image.height,
        "byte_size": image.byte_size,
        "created_at": image.created_at,
        "uploaded_by_name": display_name(uploader),
        "reference_count": reference_count,
    }


async def list_images(
    db: AsyncSession, course_id: int, page: int, unused_only: bool
) -> dict:
    """One page of a course's images, newest first, each with its reference count."""
    counts = await course_reference_counts(db, course_id)
    rows = (
        await db.execute(
            select(Image, User)
            .outerjoin(User, User.id == Image.uploaded_by)
            .where(Image.course_id == course_id)
            .order_by(Image.created_at.desc(), Image.id.desc())
        )
    ).all()
    items = [item(image, user, counts.get(image.id, 0)) for image, user in rows]
    if unused_only:
        items = [i for i in items if i["reference_count"] == 0]
    start = (page - 1) * PAGE_SIZE
    return {
        "items": items[start : start + PAGE_SIZE],
        "total": len(items),
        "page": page,
        "page_size": PAGE_SIZE,
    }


async def lock_image(db: AsyncSession, image_id: int) -> Image | None:
    """The image row, locked FOR UPDATE: a concurrent question save that uses it
    (assert_usable, FOR SHARE) waits until this transaction ends."""
    return (
        await db.execute(select(Image).where(Image.id == image_id).with_for_update())
    ).scalar_one_or_none()


def used_by(n: int) -> ConflictError:
    return ConflictError(f"Image is used by {n} question{'' if n == 1 else 's'}")


async def delete_image(db: AsyncSession, image: Image) -> None:
    """Contract C7: 409 while any question uses the image. Call with a locked row."""
    references = await find_references(db, image.id)
    if references:
        raise used_by(len(references))
    await db.delete(image)
    await db.flush()


async def reference_count(db: AsyncSession, image_id: int) -> int:
    return len(await find_references(db, image_id))
