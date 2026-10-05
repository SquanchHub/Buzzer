"""Image API responses (T8, docs/plans/t8-image-support.md D4)."""

from datetime import datetime

from pydantic import BaseModel


class ImageItem(BaseModel):
    """An image's metadata — never its bytes, which are only served by GET /images/{id}."""

    id: int
    course_id: int
    content_type: str
    width: int
    height: int
    byte_size: int
    created_at: datetime | None
    uploaded_by_name: str | None
    reference_count: int


class ImagePage(BaseModel):
    items: list[ImageItem]
    total: int
    page: int
    page_size: int


class ReplaceResult(BaseModel):
    id: int  # the image the questions now use
    replaced_id: int
    repointed_questions: int
    old_deleted: bool
