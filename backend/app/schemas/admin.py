from __future__ import annotations

import math
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=255)
    semester: str = Field(..., min_length=1, max_length=50)


class CourseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=255)
    semester: str | None = Field(None, min_length=1, max_length=50)


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    semester: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


class RosterEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    course_id: int
    netid: str
    full_name: str
    email: str
    is_active: bool
    imported_at: datetime


class RosterUploadResult(BaseModel):
    imported: int
    updated: int
    deactivated: int
    errors: list[str]


class RosterEntryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    netid: str | None = Field(None, min_length=1, max_length=100)
    full_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None


class RosterRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    netid: str = Field(..., min_length=1, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)


class RosterImportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[RosterRowIn] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class GameMeta(BaseModel):
    """A game's own fields; also validates an import bundle's `game` block,
    which never carries a course (course ids are instance-specific)."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=5000)
    max_players: int = Field(150, ge=1, le=500)


class GameCreate(GameMeta):
    course_id: int = Field(..., gt=0)


class GameUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    max_players: int | None = Field(None, ge=1, le=500)
    # Admin-only move to another course. Omit to keep; null is rejected
    # (unassigning a game is not supported).
    course_id: int | None = Field(None, gt=0)

    @field_validator("course_id", mode="before")
    @classmethod
    def course_id_not_null(cls, v: object) -> object:
        if v is None:
            raise ValueError("course_id cannot be null; omit it to keep the course")
        return v


class HostGameUpdate(BaseModel):
    """A host's game edit (T4 §6.2.3): GameUpdate without course_id. Only admins move a
    game between courses (D5), so extra="forbid" makes a host's course_id a 422."""

    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    max_players: int | None = Field(None, ge=1, le=500)


class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    max_players: int
    course_id: int | None
    created_at: datetime


class HostGameItem(GameResponse):
    """A game in a host's course list (T4 §6.2.3), with the number of its sessions in any
    status — the host app's delete confirmation names it (§6.3)."""

    session_count: int


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

# Hotspot rules (docs/plans/t7-hotspot.md §5.1). The single checker for these
# rules: QuestionCreate uses it to reject bad input, and game_service uses it to
# detect bad *stored* data at scoring time (§5.4, §13.1 i).
_HOTSPOT_CONFIG_KEYS = {"imageId", "aspectRatio"}
_HOTSPOT_ANSWER_KEYS = {"x", "y", "innerRadius", "outerRadius", "partialFraction"}


def _is_finite_number(value: object) -> bool:
    """True for int or float, excluding bool (an int subclass), NaN and infinity."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    # math.isfinite would overflow on huge ints; ints are always finite anyway.
    return isinstance(value, int) or math.isfinite(value)


def is_hotspot_aspect_ratio(value: object) -> bool:
    return _is_finite_number(value) and 0.2 <= value <= 5


def hotspot_config_error(config: object) -> str | None:
    """Why a hotspot config breaks §5.1, or None if it is valid."""
    if not isinstance(config, dict) or set(config) != _HOTSPOT_CONFIG_KEYS:
        return "hotspot config must have exactly 'imageId' and 'aspectRatio'"
    image_id = config["imageId"]
    if isinstance(image_id, bool) or not isinstance(image_id, int) or image_id < 1:
        return "hotspot imageId must be a positive integer"
    if not is_hotspot_aspect_ratio(config["aspectRatio"]):
        return "hotspot aspectRatio must be a finite number between 0.2 and 5"
    return None


def hotspot_answer_error(answer_data: object) -> str | None:
    """Why ACCURACY hotspot answer_data breaks §5.1, or None if it is valid."""
    if not isinstance(answer_data, dict) or set(answer_data) != _HOTSPOT_ANSWER_KEYS:
        return (
            "ACCURACY hotspot answer_data must have exactly 'x', 'y', "
            "'innerRadius', 'outerRadius' and 'partialFraction'"
        )
    if not all(_is_finite_number(answer_data[k]) for k in _HOTSPOT_ANSWER_KEYS):
        return "hotspot answer_data values must be finite numbers"
    inner = answer_data["innerRadius"]
    outer = answer_data["outerRadius"]
    if not (0 <= answer_data["x"] <= 1 and 0 <= answer_data["y"] <= 1):
        return "hotspot x and y must be between 0 and 1"
    if not 0.02 <= inner <= 0.5:
        return "hotspot innerRadius must be between 0.02 and 0.5"
    if not inner <= outer <= 1:
        return "hotspot outerRadius must be between innerRadius and 1"
    if not 0 <= answer_data["partialFraction"] <= 1:
        return "hotspot partialFraction must be between 0 and 1"
    return None


# Ordering rules (docs/plans/t7-ordering.md §4.1). The single checker for these rules:
# QuestionCreate uses it to reject bad input (create, and update via content_service's
# merge-and-revalidate), and game_service uses it to detect bad *stored* data (§4.6).
# Checks run in the §4.1 order, so the first failing one names the problem.
ORDERING_MIN_ITEMS = 3
ORDERING_MAX_ITEMS = 6
ORDERING_ITEM_MAX_LEN = 80


def _is_index(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def ordering_config_error(config: object) -> str | None:
    """Why an ordering config breaks §4.1, or None if it is valid."""
    if not isinstance(config, dict) or set(config) != {"items"}:
        return "ordering config must have exactly 'items'"
    items = config["items"]
    if (
        not isinstance(items, list)
        or not ORDERING_MIN_ITEMS <= len(items) <= ORDERING_MAX_ITEMS
        or not all(isinstance(item, str) for item in items)
    ):
        return "ordering items must be a list of 3 to 6 strings"
    for i, item in enumerate(items, start=1):
        if not 1 <= len(item) <= ORDERING_ITEM_MAX_LEN:
            return f"ordering item {i} must be 1 to 80 characters"
        if item != " ".join(item.split()):
            return (
                f"ordering item {i} must not have leading, trailing or repeated spaces"
            )
    if len({" ".join(item.lower().split()) for item in items}) != len(items):
        return "ordering items must be unique"
    return None


def ordering_answer_error(config: object, answer_data: object) -> str | None:
    """Why an ACCURACY ordering question's config or answer_data breaks §4.1, or None."""
    error = ordering_config_error(config)
    if error is not None:
        return error
    if not isinstance(answer_data, dict) or set(answer_data) != {
        "correctOrder",
        "partialCredit",
    }:
        return (
            "ACCURACY ordering answer_data must have exactly 'correctOrder' and "
            "'partialCredit'"
        )
    n = len(config["items"])
    order = answer_data["correctOrder"]
    if (
        not isinstance(order, list)
        or not all(_is_index(i) for i in order)
        or sorted(order) != list(range(n))
    ):
        return (
            f"ordering correctOrder must list each item index 0..{n - 1} exactly once"
        )
    if order == list(range(n)):
        return (
            "ordering items must be stored in a shuffled order, not the correct order"
        )
    if not isinstance(answer_data["partialCredit"], bool):
        return "ordering partialCredit must be true or false"
    return None


# T8 option images (docs/plans/t8-image-support.md D5, §5): only these types may carry
# config.optionImageIds.
OPTION_IMAGE_TYPES = ("multiple_choice", "multi_select")


def option_images_error(question_type: str, config: object) -> str | None:
    """Why config.optionImageIds (or an option's text) breaks T8 §5, or None if valid.
    Without optionImageIds the existing option rules are unchanged."""
    if not isinstance(config, dict) or "optionImageIds" not in config:
        return None
    if question_type not in OPTION_IMAGE_TYPES:
        return "optionImageIds is only allowed on multiple_choice and multi_select"
    ids, options = config["optionImageIds"], config.get("options")
    if (
        not isinstance(ids, list)
        or not isinstance(options, list)
        or len(ids) != len(options)
    ):
        return "optionImageIds must be a list the same length as options"
    for i, (image_id, text) in enumerate(zip(ids, options)):
        if image_id is not None and (
            isinstance(image_id, bool) or not isinstance(image_id, int) or image_id < 1
        ):
            return f"optionImageIds[{i}] must be a positive integer or null"
        if image_id is None and (not isinstance(text, str) or not text.strip()):
            return f"option {i + 1} needs text or an image"
    return None


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(
        ...,
        pattern="^(multiple_choice|true_false|fill_in_the_blank|multi_select|hotspot|ordering)$",
    )
    grading_type: str = Field(..., pattern="^(ACCURACY|COMPLETENESS)$")
    prompt: str = Field(..., min_length=1, max_length=2000)
    config: dict = Field(default_factory=dict)
    answer_data: dict = Field(default_factory=dict)
    time_limit_seconds: int = Field(30, ge=2, le=300)
    points_value: float = Field(1.0, ge=0, le=100000)
    order_index: int | None = Field(None, ge=0)
    # T8: image shown with the prompt; existence and course are checked in content_service.
    prompt_image_id: StrictInt | None = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_structure(self) -> QuestionCreate:
        error = option_images_error(self.type, self.config)
        if error is not None:
            raise ValueError(error)
        if self.type == "multiple_choice":
            opts = self.config.get("options")
            if not isinstance(opts, list) or len(opts) < 2:
                raise ValueError(
                    "multiple_choice config must have 'options' list with at least 2 items"
                )
            if self.grading_type == "ACCURACY":
                pts = self.answer_data.get("answer_points")
                if not isinstance(pts, list) or len(pts) != len(opts):
                    raise ValueError(
                        "ACCURACY multiple_choice answer_data must have 'answer_points' list matching options length"
                    )
                if any(not isinstance(p, (int, float)) or p < 0 for p in pts):
                    raise ValueError(
                        "answer_points values must be non-negative numbers"
                    )
        if self.type == "true_false" and self.grading_type == "ACCURACY":
            pts = self.answer_data.get("answer_points")
            if not isinstance(pts, dict) or set(pts.keys()) != {"true", "false"}:
                raise ValueError(
                    "ACCURACY true_false answer_data must have 'answer_points' with 'true' and 'false' keys"
                )
        if self.type == "fill_in_the_blank" and self.grading_type == "ACCURACY":
            answers = self.answer_data.get("acceptedAnswers")
            if not isinstance(answers, list) or len(answers) == 0:
                raise ValueError(
                    "ACCURACY fill_in_the_blank answer_data must have 'acceptedAnswers' list with at least one item"
                )
            if any(not isinstance(a, str) or not a.strip() for a in answers):
                raise ValueError("acceptedAnswers entries must be non-empty strings")
            pts = self.answer_data.get("answerPoints")
            if not isinstance(pts, list) or len(pts) != len(answers):
                raise ValueError(
                    "ACCURACY fill_in_the_blank answer_data must have 'answerPoints' list matching acceptedAnswers length"
                )
            if any(not isinstance(p, (int, float)) or p < 0 for p in pts):
                raise ValueError("answerPoints values must be non-negative numbers")
            edit_dist = self.answer_data.get("editDistance", 0)
            if not isinstance(edit_dist, int) or edit_dist < 0:
                raise ValueError("editDistance must be a non-negative integer")
        if self.type == "multi_select":
            opts = self.config.get("options")
            if not isinstance(opts, list) or len(opts) < 2:
                raise ValueError(
                    "multi_select config must have 'options' list with at least 2 items"
                )
            if self.grading_type == "ACCURACY":
                pts = self.answer_data.get("answer_points")
                if not isinstance(pts, list) or len(pts) != len(opts):
                    raise ValueError(
                        "ACCURACY multi_select answer_data must have 'answer_points' list matching options length"
                    )
                if any(not isinstance(p, (int, float)) for p in pts):
                    raise ValueError("answer_points values must be numbers")
        if self.type == "hotspot":
            error = hotspot_config_error(self.config)
            if error is None and self.grading_type == "ACCURACY":
                error = hotspot_answer_error(self.answer_data)
            if error is not None:
                raise ValueError(error)
        if self.type == "ordering":
            error = ordering_config_error(self.config)
            if error is None and self.grading_type == "ACCURACY":
                error = ordering_answer_error(self.config, self.answer_data)
            if error is not None:
                raise ValueError(error)
        return self


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str | None = Field(
        None,
        pattern="^(multiple_choice|true_false|fill_in_the_blank|multi_select|hotspot|ordering)$",
    )
    grading_type: str | None = Field(None, pattern="^(ACCURACY|COMPLETENESS)$")
    prompt: str | None = Field(None, min_length=1, max_length=2000)
    config: dict | None = None
    answer_data: dict | None = None
    time_limit_seconds: int | None = Field(None, ge=2, le=300)
    points_value: float | None = Field(None, ge=0, le=100000)
    order_index: int | None = Field(None, ge=0)
    # The one field where an explicit null is allowed on update: it removes the image.
    prompt_image_id: StrictInt | None = Field(None, gt=0)


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    game_id: int
    type: str
    grading_type: str
    prompt: str
    config: dict
    answer_data: dict
    time_limit_seconds: int
    points_value: float
    order_index: int
    prompt_image_id: int | None
    created_at: datetime


class QuestionReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[int] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Users (local accounts)
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=72)
    email: EmailStr | None = None

    @field_validator("username")
    @classmethod
    def lower_username(cls, v: str) -> str:
        return v.lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(
        None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    display_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8, max_length=72)
    role: str | None = Field(None, pattern="^(USER|ADMIN)$")

    @field_validator("username")
    @classmethod
    def lower_username(cls, v: str | None) -> str | None:
        return v.lower() if v is not None else None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str | None
    netid: str | None
    display_name: str | None
    email: str | None
    role: str
    created_at: datetime
    last_login: datetime | None


# ---------------------------------------------------------------------------
# Access management
# ---------------------------------------------------------------------------


class CourseAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: int
    role: str = Field(..., pattern="^(HOST|PLAYER)$")


class CourseMemberResponse(BaseModel):
    """A user with HOST or PLAYER in one course (admin course detail page)."""

    user_id: str
    username: str | None
    display_name: str | None
    netid: str | None
    role: str  # HOST | PLAYER


class GameAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: int


class UserWithAccessResponse(UserResponse):
    course_access: list[dict]
    game_access: list[int]


# ---------------------------------------------------------------------------
# Sessions (admin view)
# ---------------------------------------------------------------------------


class AdminSessionItem(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    session_id: str
    room_code: str
    status: str
    game_id: int
    game_title: str
    course_id: int
    course_name: str
    course_semester: str
    host_display_name: str | None
    created_at: datetime
    completed_at: datetime | None
    player_count: int
