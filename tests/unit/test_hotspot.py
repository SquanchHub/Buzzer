"""
Unit tests for the hotspot helpers in game_service (docs/plans/t7-hotspot.md §5.2, §5.4,
§10 test 18). Pure functions — no database, Redis or Docker stack needed.

Boundary taps use binary-exact values (eighths, sixteenths) so "both boundaries are
inclusive" is tested exactly, with no float rounding.

Run with:
    cd tests/unit && pytest test_hotspot.py -v
"""

from __future__ import annotations

import math

import pytest
from structlog.testing import capture_logs

from app.services.game_service import (
    HotspotTarget,
    hotspot_band,
    hotspot_reveal,
    hotspot_target,
)

CONFIG = {"imageId": 1, "aspectRatio": 2.0}
ANSWER = {
    "x": 0.5,
    "y": 0.25,
    "innerRadius": 0.02,
    "outerRadius": 0.05,
    "partialFraction": 0.5,
}


def target(aspect: float, inner: float, outer: float) -> HotspotTarget:
    """A target at the image centre. Built directly, so radii aren't bound by §5.1."""
    return HotspotTarget(
        x=0.5,
        y=0.5,
        inner_radius=inner,
        outer_radius=outer,
        partial_fraction=0.5,
        aspect_ratio=aspect,
    )


# ---------------------------------------------------------------------------
# hotspot_target
# ---------------------------------------------------------------------------


def test_target_valid_returns_floats():
    t = hotspot_target(7, CONFIG, {**ANSWER, "x": 1, "y": 0})  # ints are allowed
    assert t == HotspotTarget(
        x=1.0,
        y=0.0,
        inner_radius=0.02,
        outer_radius=0.05,
        partial_fraction=0.5,
        aspect_ratio=2.0,
    )
    assert isinstance(t.x, float) and isinstance(t.aspect_ratio, float)


def test_target_ignores_image_id():
    # A bad imageId is the clients' "Image unavailable" path, not a scoring failure.
    assert hotspot_target(7, {"aspectRatio": 2.0}, ANSWER) is not None
    assert (
        hotspot_target(7, {"imageId": "nope", "aspectRatio": 2.0}, ANSWER) is not None
    )


@pytest.mark.parametrize(
    ("config", "answer_data"),
    [
        (CONFIG, None),
        (CONFIG, []),
        (CONFIG, "x=0.5"),
        (CONFIG, {}),
        (CONFIG, {k: v for k, v in ANSWER.items() if k != "innerRadius"}),
        (CONFIG, {**ANSWER, "innerRadius": "0.02"}),
        (CONFIG, {**ANSWER, "x": True}),
        (CONFIG, {**ANSWER, "x": math.nan}),
        (CONFIG, {**ANSWER, "innerRadius": 0.06, "outerRadius": 0.05}),
        (CONFIG, {**ANSWER, "extra": 1}),
        ({"imageId": 1, "aspectRatio": 0}, ANSWER),
        ({"imageId": 1, "aspectRatio": math.inf}, ANSWER),
        ({"imageId": 1, "aspectRatio": "2"}, ANSWER),
        ({"imageId": 1}, ANSWER),
        (None, ANSWER),
        ([1, 2.0], ANSWER),
    ],
)
def test_target_invalid_returns_none_and_logs(config, answer_data):
    with capture_logs() as logs:
        assert hotspot_target(42, config, answer_data) is None
    assert logs == [
        {
            "event": "hotspot_target_invalid",
            "question_id": 42,
            "log_level": "warning",
        }
    ]


def test_target_valid_does_not_log():
    with capture_logs() as logs:
        hotspot_target(42, CONFIG, ANSWER)
    assert logs == []


# ---------------------------------------------------------------------------
# hotspot_band — boundaries inclusive, aspect-corrected distance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("px", "py", "band"),
    [
        (0.5, 0.5, "inner"),  # dead centre
        (0.75, 0.5, "inner"),  # d = 0.25, exactly on the inner ring
        (0.5, 0.25, "inner"),
        (0.875, 0.5, "outer"),  # d = 0.375, exactly on the outer ring
        (0.5, 0.125, "outer"),
        (0.9, 0.5, "miss"),
        (0.0, 0.0, "miss"),
    ],
)
def test_band_square(px, py, band):
    assert hotspot_band(target(1.0, 0.25, 0.375), px, py) == band


def test_band_diagonal_uses_euclidean_distance():
    # dx = 3/16, dy = 4/16 → d = 5/16 exactly (a 3-4-5 triangle).
    assert hotspot_band(target(1.0, 0.3125, 0.5), 0.6875, 0.75) == "inner"
    assert hotspot_band(target(1.0, 0.25, 0.3125), 0.6875, 0.75) == "outer"
    assert hotspot_band(target(1.0, 0.25, 0.3), 0.6875, 0.75) == "miss"


@pytest.mark.parametrize(
    ("px", "py", "band"),
    [
        # Landscape 2:1 — width is the longer side, so a y-offset counts half.
        (0.625, 0.5, "inner"),  # dx = 0.125, on the inner ring
        (0.5, 0.75, "inner"),  # dy = 0.25 / 2 = 0.125, on the inner ring
        (0.75, 0.5, "outer"),  # dx = 0.25, on the outer ring
        (0.5, 1.0, "outer"),  # dy = 0.5 / 2 = 0.25, on the outer ring
        (0.76, 0.5, "miss"),
    ],
)
def test_band_landscape(px, py, band):
    assert hotspot_band(target(2.0, 0.125, 0.25), px, py) == band


@pytest.mark.parametrize(
    ("px", "py", "band"),
    [
        # Portrait 1:2 — height is the longer side, so an x-offset counts half.
        (0.75, 0.5, "inner"),  # dx = 0.25 * 0.5 = 0.125, on the inner ring
        (0.5, 0.625, "inner"),  # dy = 0.125, on the inner ring
        (1.0, 0.5, "outer"),  # dx = 0.5 * 0.5 = 0.25, on the outer ring
        (0.5, 0.75, "outer"),  # dy = 0.25, on the outer ring
        (0.5, 0.76, "miss"),
    ],
)
def test_band_portrait(px, py, band):
    assert hotspot_band(target(0.5, 0.125, 0.25), px, py) == band


def test_band_aspect_correction_differs_from_per_axis():
    # §10 test 6's idea at unit level: on a 2:1 image this tap is 0.2 away per-axis
    # (a miss for outer 0.15) but 0.1 away in longer-side units (inside the outer ring).
    t = target(2.0, 0.05, 0.15)
    assert hotspot_band(t, 0.5, 0.7) == "outer"


def test_band_equal_radii_has_no_outer_band():
    t = target(1.0, 0.25, 0.25)
    assert hotspot_band(t, 0.75, 0.5) == "inner"
    assert hotspot_band(t, 0.76, 0.5) == "miss"


# ---------------------------------------------------------------------------
# hotspot_reveal
# ---------------------------------------------------------------------------


def test_reveal_shape_omits_partial_fraction():
    t = hotspot_target(1, CONFIG, ANSWER)
    assert hotspot_reveal(t) == {
        "type": "hotspot",
        "x": 0.5,
        "y": 0.25,
        "innerRadius": 0.02,
        "outerRadius": 0.05,
    }


def test_reveal_invalid_target_has_no_target_fields():
    assert hotspot_reveal(None) == {"type": "hotspot"}
