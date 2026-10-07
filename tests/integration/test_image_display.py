"""
T8 image display (docs/plans/t8-image-support.md §7, Arjun's tests 16–17).

Test 16: the live `new_question` payload carries the question's images — `promptImageId`
(null when the question has none) and, inside `config`, `optionImageIds` — to both the host
and the players (§5 "Live game payload", D8).
"""

from __future__ import annotations

import asyncio
import base64
import uuid

from .engine.socket_client import TestSocketClient as SocketClient
from .host_helpers import hapi  # noqa: F401 — fixture
from .image_helpers import png

# Pause after question_results before the next host_advance (host_advance double-advance
# race, backend/app/websocket/README.md open finding).
_RESULTS_SETTLE_S = 0.3


def _mc(prompt: str, **extra) -> dict:
    body = {
        "type": "multiple_choice",
        "grading_type": "ACCURACY",
        "prompt": prompt,
        "config": {"options": ["A", "B"]},
        "answer_data": {"answer_points": [1000, 0]},
        "time_limit_seconds": 60,
        "points_value": 1000,
    }
    body.update(extra)
    return body


async def test_new_question_carries_prompt_and_option_images(hapi):  # noqa: F811
    """Test 16."""
    course = hapi.course()
    _, token = hapi.host_of(course)
    prompt_img = hapi.image(course, png((40, 20), (200, 30, 30)), token)
    option_img = hapi.image(course, png((40, 20), (30, 200, 30)), token)
    game = hapi.host_game(token, course, questions=0)
    with_images = _mc(
        "Which picture?",
        prompt_image_id=prompt_img,
        config={"options": ["A", ""], "optionImageIds": [None, option_img]},
    )
    for body in (with_images, _mc("No pictures")):
        hapi.ok("POST", f"/host/games/{game}/questions", token, json=body)
    code, _ = hapi.room(token, course, game)

    host = SocketClient(hapi.base, token, "host")
    player = SocketClient(hapi.base, hapi.guest(code), "guest")
    try:
        await asyncio.gather(host.connect(), player.connect())
        await host.emit("join_room", {"room_code": code, "role": "HOST"})
        await host.wait_for("sync_state")
        await player.emit("join_room", {"room_code": code, "role": "PLAYER"})
        await player.wait_for("sync_state")

        await host.emit("host_advance", {})
        for q in (
            await host.wait_for("new_question"),
            await player.wait_for("new_question"),
        ):
            assert q["promptImageId"] == prompt_img
            assert q["config"]["optionImageIds"] == [None, option_img]
            assert q["config"]["options"] == ["A", ""]

        await host.emit("host_advance", {})
        await host.wait_for("question_results")
        await asyncio.sleep(_RESULTS_SETTLE_S)
        await host.emit("host_advance", {})
        for q in (
            await host.wait_for("new_question"),
            await player.wait_for("new_question"),
        ):
            assert q["promptImageId"] is None
            assert "optionImageIds" not in q["config"]
    finally:
        await asyncio.gather(
            host.disconnect(), player.disconnect(), return_exceptions=True
        )


async def test_host_game_over_summary_carries_prompt_images(hapi):  # noqa: F811
    """The host's game-over cards show each question's prompt image (D8), so the host
    question summary carries promptImageId (null when the question has none)."""
    course = hapi.course()
    _, token = hapi.host_of(course)
    prompt_img = hapi.image(course, png((40, 20), (20, 20, 200)), token)
    game = hapi.host_game(token, course, questions=0)
    for body in (_mc("With a picture", prompt_image_id=prompt_img), _mc("Without")):
        hapi.ok("POST", f"/host/games/{game}/questions", token, json=body)
    code, _ = hapi.room(token, course, game)

    host = SocketClient(hapi.base, token, "host")
    player = SocketClient(hapi.base, hapi.guest(code), "guest")
    try:
        await asyncio.gather(host.connect(), player.connect())
        await host.emit("join_room", {"room_code": code, "role": "HOST"})
        await host.wait_for("sync_state")
        await player.emit("join_room", {"room_code": code, "role": "PLAYER"})
        await player.wait_for("sync_state")
        for _ in range(2):
            await host.emit("host_advance", {})
            await host.wait_for("new_question")
            await host.emit("host_advance", {})
            await host.wait_for("question_results")
            await asyncio.sleep(_RESULTS_SETTLE_S)
        await host.emit("host_advance", {})
        summary = (await host.wait_for("game_over"))["questionSummary"]
    finally:
        await asyncio.gather(
            host.disconnect(), player.disconnect(), return_exceptions=True
        )
    assert [q["promptImageId"] for q in summary] == [prompt_img, None]


async def test_report_embeds_images_and_labels_image_only_options(hapi):  # noqa: F811
    """t8-image-support.md test 17 and t7-hotspot.md §10 test 15, together: the HTML
    report of a played session embeds every image as a data: URI (hotspot image, prompt
    image, option images), draws the hotspot rings in an <svg>, labels the image-only
    option "(image)", and names no player."""
    course = hapi.course()
    _, token = hapi.host_of(course)
    map_img = hapi.image(course, png((800, 400), (40, 120, 60)), token)
    prompt_img = hapi.image(course, png((40, 20), (200, 30, 30)), token)
    lion_img = hapi.image(course, png((40, 20), (210, 150, 20)), token)
    zebra_img = hapi.image(course, png((40, 20), (20, 20, 20)), token)
    game = hapi.host_game(token, course, questions=0)
    hotspot = {
        "type": "hotspot",
        "grading_type": "ACCURACY",
        "prompt": "Tap the target",
        "config": {"imageId": map_img, "aspectRatio": 2.0},
        "answer_data": {
            "x": 0.5,
            "y": 0.5,
            "innerRadius": 0.1,
            "outerRadius": 0.2,
            "partialFraction": 0.5,
        },
        "time_limit_seconds": 60,
        "points_value": 1000,
    }
    picture = _mc(
        "Which animal?",
        prompt_image_id=prompt_img,
        config={"options": ["Lion", ""], "optionImageIds": [lion_img, zebra_img]},
    )
    for body in (hotspot, picture):
        hapi.ok("POST", f"/host/games/{game}/questions", token, json=body)
    code, session = hapi.room(token, course, game)

    secret_name = f"Zed{uuid.uuid4().hex[:6]}"
    guest = hapi.ok(
        "POST",
        "/auth/guest",
        token="",
        json={
            "display_name": secret_name,
            "email": f"r{uuid.uuid4().hex[:8]}@example.com",
            "room_code": code,
        },
    )["access_token"]
    host = SocketClient(hapi.base, token, "host")
    player = SocketClient(hapi.base, guest, "guest")
    try:
        await asyncio.gather(host.connect(), player.connect())
        await host.emit("join_room", {"room_code": code, "role": "HOST"})
        await host.wait_for("sync_state")
        await player.emit("join_room", {"room_code": code, "role": "PLAYER"})
        await player.wait_for("sync_state")
        for answer in ({"x": 0.5, "y": 0.5}, {"selectedIndex": 1}):
            await host.emit("host_advance", {})
            q = await player.wait_for("new_question")
            await player.emit(
                "submit_answer",
                {
                    "question_id": q["questionId"],
                    "answer_data": answer,
                    "answer_time_ms": 300,
                },
            )
            await player.wait_for("answer_received")
            await host.emit("host_advance", {})
            await host.wait_for("question_results")
            await asyncio.sleep(_RESULTS_SETTLE_S)
        await host.emit("host_advance", {})
        await host.wait_for("game_over")
    finally:
        await asyncio.gather(
            host.disconnect(), player.disconnect(), return_exceptions=True
        )

    r = hapi.req("GET", f"/game/sessions/{session}/report", token)
    assert r.status_code == 200, r.text
    report = r.text
    for image_id in (map_img, prompt_img, lion_img, zebra_img):
        stored = hapi.req("GET", f"/images/{image_id}", token)
        uri = f"data:image/png;base64,{base64.b64encode(stored.content).decode()}"
        embedded = uri in report  # (not inline: pytest would print the whole report)
        assert embedded, f"image {image_id} is not embedded"
    assert "Image unavailable" not in report
    assert "<svg" in report and 'class="ring-inner"' in report
    assert 'class="ring-outer"' in report
    # The image-only option B: its bar label ends "(image)" (after its thumbnail).
    assert "(image)</span>" in report
    assert secret_name not in report
