"""
T8 image display (docs/plans/t8-image-support.md §7, Arjun's tests 16–17).

Test 16: the live `new_question` payload carries the question's images — `promptImageId`
(null when the question has none) and, inside `config`, `optionImageIds` — to both the host
and the players (§5 "Live game payload", D8).
"""

from __future__ import annotations

import asyncio

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
