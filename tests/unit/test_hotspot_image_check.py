"""
Unit tests for the stage-B image-existence stand-in in content_service
(docs/plans/t7-hotspot.md §7.3, §13.2 G1). REMOVE IN T7 STAGE C with `_image_exists`.

The check must key off APP_ENV, never off the dev-images folder being present: outside
development no image exists even when the folder (and the file) is there.

Run with:
    cd tests/unit && pytest test_hotspot_image_check.py -v
"""

from __future__ import annotations

import pytest

from app.common.exceptions import RequestBodyInvalidError
from app.schemas.admin import QuestionCreate
from app.services import content_service


@pytest.fixture()
def dev_images(tmp_path, monkeypatch):
    (tmp_path / "1.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(content_service, "_DEV_IMAGES_DIR", tmp_path)
    return tmp_path


def _env(monkeypatch, app_env: str) -> None:
    monkeypatch.setattr(content_service.settings, "APP_ENV", app_env)


def test_development_present_file_exists(dev_images, monkeypatch):
    _env(monkeypatch, "development")
    assert content_service._image_exists(1) is True


def test_development_missing_file_does_not_exist(dev_images, monkeypatch):
    _env(monkeypatch, "development")
    assert content_service._image_exists(2) is False


@pytest.mark.parametrize("app_env", ["production", "staging", ""])
def test_other_environments_have_no_images_even_with_the_file(
    dev_images, monkeypatch, app_env
):
    _env(monkeypatch, app_env)
    assert content_service._image_exists(1) is False


def _hotspot(image_id: int) -> QuestionCreate:
    return QuestionCreate(
        type="hotspot",
        grading_type="ACCURACY",
        prompt="Tap it",
        config={"imageId": image_id, "aspectRatio": 2.0},
        answer_data={
            "x": 0.5,
            "y": 0.5,
            "innerRadius": 0.1,
            "outerRadius": 0.2,
            "partialFraction": 0.5,
        },
        time_limit_seconds=30,
        points_value=1000,
    )


def test_check_raises_field_error_for_unknown_image(dev_images, monkeypatch):
    _env(monkeypatch, "development")
    content_service._check_hotspot_image(_hotspot(1))  # exists: no error
    with pytest.raises(RequestBodyInvalidError) as exc:
        content_service._check_hotspot_image(_hotspot(7))
    assert exc.value.errors == [
        {
            "type": "value_error",
            "loc": ("body", "config", "imageId"),
            "msg": "Image 7 does not exist",
            "input": 7,
        }
    ]


def test_check_ignores_other_question_types(monkeypatch):
    _env(monkeypatch, "production")  # would reject any hotspot image
    mc = QuestionCreate(
        type="multiple_choice",
        grading_type="ACCURACY",
        prompt="Pick",
        config={"options": ["A", "B"]},
        answer_data={"answer_points": [1, 0]},
        time_limit_seconds=30,
        points_value=1,
    )
    content_service._check_hotspot_image(mc)
