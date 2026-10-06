"""
/api/images — question images (docs/plans/t8-image-support.md D4).

One router for every audience: any logged-in token (guests included) may fetch an
image's bytes (contract C3 in docs/plans/t7-hotspot.md §4); managing images needs
an admin or a HOST of the image's course (D3). Handlers only translate
image_service calls to HTTP.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from ..common.dependencies import get_current_user, require_user
from ..common.exceptions import NotFoundError
from ..database import DbSession
from ..models.image import Image
from ..models.user import User
from ..redis_client import get_redis
from ..schemas.image import ImageItem, ImagePage, ReplaceResult
from ..services import content_service, game_service, image_service

router = APIRouter(prefix="/images", tags=["images"])

# Contract C3: bytes under an ID never change (C1), so a cached copy is never stale;
# private because the request carries a bearer token.
_CACHE = "private, max-age=31536000, immutable"


async def _item(db: DbSession, image: Image) -> ImageItem:
    uploader = await db.get(User, image.uploaded_by) if image.uploaded_by else None
    return ImageItem(
        **image_service.item(
            image, uploader, await image_service.reference_count(db, image.id)
        )
    )


async def _managed_image(db: DbSession, user: User, image_id: int) -> Image:
    """The image, locked FOR UPDATE, if `user` may manage it (admin or HOST of its
    course): 404 unknown, 403 otherwise."""
    image = await image_service.lock_image(db, image_id)
    if image is None:
        raise NotFoundError(f"Image {image_id} not found")
    await game_service.assert_host_can_use_course(db, user, image.course_id)
    return image


@router.get("", response_model=ImagePage)
async def list_images(
    course_id: Annotated[int, Query(gt=0)],
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    unused: bool = False,
) -> dict:
    await game_service.assert_host_can_use_course(db, user, course_id)
    return await image_service.list_images(db, course_id, page, unused)


@router.post("", status_code=201, response_model=ImageItem)
async def upload_image(
    file: Annotated[UploadFile, File(description="PNG, JPEG or WebP, at most 2 MB")],
    course_id: Annotated[int, Form(gt=0, description="Course that owns the image")],
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
    response: Response,
) -> ImageItem:
    await game_service.assert_host_can_use_course(db, user, course_id)
    # Read one byte past the cap, so an oversized file is refused without holding it all.
    data = await file.read(image_service.MAX_BYTES + 1)
    image, created = await image_service.create_image(db, course_id, data, user.id)
    if created:
        # Load the server-set created_at. Only for our own insert: a reused row was
        # read with a locking read and may be invisible to a plain one (REPEATABLE READ).
        await db.refresh(image, ["created_at"])
    else:
        response.status_code = 200
    return await _item(db, image)


@router.get("/{image_id}")
async def get_image(
    image_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: DbSession,
) -> Response:
    found = await image_service.get_image(db, image_id)
    if found is None:
        raise NotFoundError(f"Image {image_id} not found")
    content_type, data = found
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": _CACHE, "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{image_id}", status_code=204)
async def delete_image(
    image_id: int,
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
) -> Response:
    image = await _managed_image(db, user, image_id)
    await image_service.delete_image(db, image)
    return Response(status_code=204)


@router.post("/{image_id}/replace", response_model=ReplaceResult)
async def replace_image(
    image_id: int,
    file: Annotated[UploadFile, File(description="PNG, JPEG or WebP, at most 2 MB")],
    user: Annotated[User, Depends(require_user)],
    db: DbSession,
    redis=Depends(get_redis),
) -> dict:
    image = await _managed_image(db, user, image_id)
    data = await file.read(image_service.MAX_BYTES + 1)
    return await content_service.replace_image(db, redis, user, image, data)
