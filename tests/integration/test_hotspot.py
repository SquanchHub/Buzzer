"""
T7 hotspot question type — stage A integration tests (docs/plans/t7-hotspot.md §10, §13.1 f).

Stage A covers §10 tests 1 and 6–10. Before T8 there is no image API, so questions use a
placeholder `imageId` and are created through `POST /api/admin/games/{g}/questions`, which does
not check that the image exists until T4 phase 3. Stage C moves tests 6–10 to the host route and
a real T8 image (§10). Test 18 is a unit test (`tests/unit/test_hotspot.py`).

Stage B (§13.2) adds the host-route tests at the end: the image-existence check (test 2, and
stage-B versions of tests 3–5 against the dev image `frontend/dev-images/1.png`, which the
backend sees through a dev-only mount), the v1-bundle hotspot rejection (test 13b) and the
sample-game import through the host route (test 14). Stage C switches them to real T8 images.

Socket tests advance to results with no pause after the last answer: `on_submit_answer`
commits before it emits `answer_received` (fix/commit-before-emit), so the results query
always sees every acknowledged answer.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from .conftest import _REPO_ROOT, create_guest_tokens, create_room
from .host_helpers import hapi  # noqa: F401 — fixture

# Aliased so pytest doesn't try to collect the Test-prefixed class from this module.
from .engine.socket_client import TestSocketClient as SocketClient

_TIMEOUT = 10.0

# Placeholder image: the admin create route doesn't check image existence before T4 phase 3.
CONFIG = {"imageId": 1, "aspectRatio": 2.0}
TARGET = {
    "x": 0.5,
    "y": 0.5,
    "innerRadius": 0.1,
    "outerRadius": 0.2,
    "partialFraction": 0.5,
}
TAP_ERROR = "hotspot answer must include x and y between 0 and 1"

# Pause after question_results before the next host_advance. NOT a race workaround for
# answers: host_advance emits question_results *before* it writes question_phase =
# "RESULTS" to Redis, so a second advance within ~10 ms still sees QUESTION, re-shows
# results and stalls the game (open finding "host_advance double-advance race",
# backend/app/websocket/README.md). Real hosts are protected by the results countdown.
_RESULTS_SETTLE_S = 0.3


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _question_body(**overrides) -> dict:
    body = {
        "type": "hotspot",
        "grading_type": "ACCURACY",
        "prompt": "Tap the target.",
        "config": dict(CONFIG),
        "answer_data": dict(TARGET),
        "time_limit_seconds": 60,
        "points_value": 1000,
    }
    body.update(overrides)
    return body


def _post_question(
    base_url: str, token: str, game_id: int, body: dict | str
) -> httpx.Response:
    """POST a question; a str body is sent verbatim (needed for a literal NaN)."""
    url = f"{base_url}/api/admin/games/{game_id}/questions"
    headers = {**_h(token), "Content-Type": "application/json"}
    content = body if isinstance(body, str) else json.dumps(body)
    return httpx.post(url, content=content, headers=headers, timeout=_TIMEOUT)


def _create(base_url: str, token: str, game_id: int, **overrides) -> int:
    r = _post_question(base_url, token, game_id, _question_body(**overrides))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _without(d: dict, key: str) -> dict:
    return {k: v for k, v in d.items() if k != key}


# ---------------------------------------------------------------------------
# §10 test 1 — create-time validation (§5.1)
# ---------------------------------------------------------------------------

_VIOLATIONS = {
    "missing imageId": {"config": _without(CONFIG, "imageId")},
    "bool imageId": {"config": {**CONFIG, "imageId": True}},
    "aspectRatio 0": {"config": {**CONFIG, "aspectRatio": 0}},
    "aspectRatio 6": {"config": {**CONFIG, "aspectRatio": 6}},
    "extra config key imageRef": {"config": {**CONFIG, "imageRef": "img1"}},
    "ACCURACY missing answer_data key": {
        "answer_data": _without(TARGET, "partialFraction")
    },
    "x 1.1": {"answer_data": {**TARGET, "x": 1.1}},
    "innerRadius 0.01": {"answer_data": {**TARGET, "innerRadius": 0.01}},
    "innerRadius 0.6": {
        "answer_data": {**TARGET, "innerRadius": 0.6, "outerRadius": 0.7}
    },
    "innerRadius > outerRadius": {"answer_data": {**TARGET, "innerRadius": 0.3}},
    "outerRadius 1.5": {"answer_data": {**TARGET, "outerRadius": 1.5}},
    "partialFraction -0.1": {"answer_data": {**TARGET, "partialFraction": -0.1}},
    "extra answer_data key": {"answer_data": {**TARGET, "z": 0}},
}


def test_create_valid_hotspot(game_setup, base_url, admin_token):
    """Baseline: the valid body is accepted and stored exactly, so each 422 below is
    caused by its one violation. (Stage C repeats this with a real image, §10 test 3.)"""
    r = _post_question(base_url, admin_token, game_setup["game_id"], _question_body())
    assert r.status_code == 201, r.text
    assert r.json()["config"] == CONFIG
    assert r.json()["answer_data"] == TARGET


@pytest.mark.parametrize("overrides", _VIOLATIONS.values(), ids=_VIOLATIONS.keys())
def test_create_rejects_each_violation(game_setup, base_url, admin_token, overrides):
    r = _post_question(
        base_url, admin_token, game_setup["game_id"], _question_body(**overrides)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "VALIDATION_ERROR"


def test_create_rejects_nan_aspect_ratio(game_setup, base_url, admin_token):
    """A literal NaN in the body is a 422, not a 500 (fix/422-handler-nan)."""
    raw = json.dumps(_question_body()).replace(
        '"aspectRatio": 2.0', '"aspectRatio": NaN'
    )
    assert "NaN" in raw
    r = _post_question(base_url, admin_token, game_setup["game_id"], raw)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "VALIDATION_ERROR"


def test_completeness_checks_config_but_not_answer_data(
    game_setup, base_url, admin_token
):
    game_id = game_setup["game_id"]
    ok = _question_body(grading_type="COMPLETENESS", answer_data={})
    assert _post_question(base_url, admin_token, game_id, ok).status_code == 201
    bad = _question_body(
        grading_type="COMPLETENESS", answer_data={}, config={"imageId": 1}
    )
    assert _post_question(base_url, admin_token, game_id, bad).status_code == 422


# ---------------------------------------------------------------------------
# Socket helpers
# ---------------------------------------------------------------------------


class HotspotGame:
    """A live room: host + N guest players over Socket.io, driven step by step."""

    def __init__(self, base_url: str, admin_token: str, setup: dict, n_players: int):
        self.base_url = base_url
        self.admin_token = admin_token
        self.setup = setup
        self.n_players = n_players
        self._after_results = False

    async def __aenter__(self) -> HotspotGame:
        room = create_room(
            self.base_url,
            self.admin_token,
            self.setup["course_id"],
            self.setup["game_id"],
        )
        tokens = create_guest_tokens(self.base_url, room, self.n_players)
        self.host = SocketClient(self.base_url, self.admin_token, "host")
        self.players = [
            SocketClient(self.base_url, t, f"p{i}") for i, t in enumerate(tokens)
        ]
        await asyncio.gather(*(c.connect() for c in [self.host, *self.players]))
        await self.host.emit("join_room", {"room_code": room, "role": "HOST"})
        await self.host.wait_for("sync_state")
        for p in self.players:
            await p.emit("join_room", {"room_code": room, "role": "PLAYER"})
            await p.wait_for("sync_state")
        return self

    async def __aexit__(self, *exc) -> None:
        await asyncio.gather(
            *(c.disconnect() for c in [self.host, *self.players]),
            return_exceptions=True,
        )

    async def _advance(self) -> None:
        if self._after_results:
            await asyncio.sleep(_RESULTS_SETTLE_S)  # see _RESULTS_SETTLE_S
        await self.host.emit("host_advance", {})

    async def next_question(self) -> tuple[dict, list[dict]]:
        """Advance to the next question; returns (host payload, player payloads)."""
        await self._advance()
        host_q = await self.host.wait_for("new_question")
        player_qs = [await p.wait_for("new_question") for p in self.players]
        self._after_results = False
        return host_q, player_qs

    async def tap(self, i: int, question_id: int, answer_data) -> dict:
        """Submit and wait for the server's answer_received for player i."""
        await self.players[i].emit(
            "submit_answer",
            {
                "question_id": question_id,
                "answer_data": answer_data,
                "answer_time_ms": 400,
            },
        )
        return await self.players[i].wait_for("answer_received")

    async def results(self) -> tuple[dict, list[dict]]:
        """Advance to results with no pause after the last answer."""
        await self._advance()
        host_r = await self.host.wait_for("question_results")
        player_rs = [await p.wait_for("question_results") for p in self.players]
        self._after_results = True
        return host_r, player_rs

    async def finish(self) -> None:
        """Advance from the last results to game_over, so the room ends COMPLETED."""
        await self._advance()
        await self.host.wait_for("game_over")
        for p in self.players:
            await p.wait_for("game_over")


async def _nothing(client: SocketClient, event: str, wait: float = 0.5) -> bool:
    """True if `event` does not arrive within `wait` seconds."""
    try:
        await client.wait_for(event, wait)
    except (asyncio.TimeoutError, TimeoutError):
        return True
    return False


# ---------------------------------------------------------------------------
# §10 tests 6–10 — live game over Socket.io
# ---------------------------------------------------------------------------


async def test_scoring_bands_with_aspect_correction(game_setup, base_url, admin_token):
    """§10 test 6. On a 2:1 image the outer tap is 0.35 away per axis (a miss for
    outerRadius 0.2) but 0.175 away in longer-side units — inside the outer ring (H3).
    All taps are >= 0.005 from both ring boundaries (§7.10)."""
    qid = _create(base_url, admin_token, game_setup["game_id"])
    async with HotspotGame(base_url, admin_token, game_setup, 3) as g:
        await g.next_question()
        inner = await g.tap(0, qid, {"x": 0.5, "y": 0.5})  # d = 0
        outer = await g.tap(1, qid, {"x": 0.5, "y": 0.85})  # d = 0.35 / 2 = 0.175
        miss = await g.tap(
            2, qid, {"x": 0.9, "y": 0.1}
        )  # d = sqrt(0.4² + 0.2²) ≈ 0.447
        assert (inner["pointsAwarded"], inner["isCorrect"]) == (1000.0, True)
        assert (outer["pointsAwarded"], outer["isCorrect"]) == (500.0, False)
        assert (miss["pointsAwarded"], miss["isCorrect"]) == (0, False)
        await g.results()
        await g.finish()


async def test_completeness_any_tap_scores_full(game_setup, base_url, admin_token):
    """§10 test 7."""
    qid = _create(
        base_url,
        admin_token,
        game_setup["game_id"],
        grading_type="COMPLETENESS",
        answer_data={},
    )
    async with HotspotGame(base_url, admin_token, game_setup, 2) as g:
        await g.next_question()
        a = await g.tap(0, qid, {"x": 0.0, "y": 1.0})
        assert (a["pointsAwarded"], a["isCorrect"]) == (1000.0, True)
        host_r, player_rs = await g.results()
        assert host_r["answerReveal"] == {"type": "completeness"}
        assert host_r["answerDistribution"] == {}
        assert host_r["taps"] == [{"x": 0.0, "y": 1.0, "band": None}]
        assert [p["yourBand"] for p in player_rs] == [
            None,
            None,
        ]  # answered, unanswered
        await g.finish()


@pytest.mark.parametrize(
    "bad_tap",
    [
        {"y": 0.5},
        {"x": True, "y": 0.5},
        {"x": 0.5, "y": 1.5},
        {"x": "0.5", "y": 0.5},
        [0.5, 0.5],
    ],
    ids=["x missing", "x true", "y 1.5", "x string", "not an object"],
)
async def test_malformed_tap_is_rejected_and_not_recorded(
    game_setup, base_url, admin_token, bad_tap
):
    """§10 test 8: socket `error`, nothing recorded, and a valid tap still works after."""
    qid = _create(base_url, admin_token, game_setup["game_id"])
    async with HotspotGame(base_url, admin_token, game_setup, 1) as g:
        await g.next_question()
        await g.players[0].emit(
            "submit_answer",
            {"question_id": qid, "answer_data": bad_tap, "answer_time_ms": 100},
        )
        err = await g.players[0].wait_for("error")
        assert err["message"] == TAP_ERROR
        assert await _nothing(g.players[0], "answer_received")
        ok = await g.tap(0, qid, {"x": 0.5, "y": 0.5, "extra": "dropped"})
        assert ok["pointsAwarded"] == 1000.0
        host_r, _ = await g.results()
        # Exactly one row was recorded (the valid tap), stored without the extra key.
        assert host_r["totalAnswered"] == 1
        assert host_r["taps"] == [{"x": 0.5, "y": 0.5, "band": "inner"}]
        await g.finish()


async def test_results_payloads(game_setup, base_url, admin_token):
    """§10 test 9: host gets taps + band counts; each player gets the reveal and their
    own yourBand, never taps. The second question has points_value 0, where points can't
    tell the bands apart but yourBand still can (H12)."""
    game_id = game_setup["game_id"]
    q1 = _create(base_url, admin_token, game_id)
    q2 = _create(base_url, admin_token, game_id, points_value=0)
    reveal = {
        "type": "hotspot",
        "x": 0.5,
        "y": 0.5,
        "innerRadius": 0.1,
        "outerRadius": 0.2,
    }
    taps = [{"x": 0.5, "y": 0.5}, {"x": 0.5, "y": 0.85}, {"x": 0.9, "y": 0.1}]
    async with HotspotGame(base_url, admin_token, game_setup, 3) as g:
        await g.next_question()
        for i, t in enumerate(taps):
            await g.tap(i, q1, t)
        host_r, player_rs = await g.results()
        assert host_r["answerReveal"] == reveal
        assert host_r["answerDistribution"] == {"inner": 1, "outer": 1, "miss": 1}
        assert host_r["taps"] == [
            {**taps[0], "band": "inner"},
            {**taps[1], "band": "outer"},
            {**taps[2], "band": "miss"},
        ]
        assert "yourBand" not in host_r
        assert [p["yourBand"] for p in player_rs] == ["inner", "outer", "miss"]
        assert all(p["answerReveal"] == reveal for p in player_rs)
        assert not any("taps" in p for p in player_rs)

        await g.next_question()
        await g.tap(0, q2, taps[1])  # outer, worth 0 points
        _, player_rs = await g.results()
        assert player_rs[0]["yourPoints"] == 0
        assert [p["yourBand"] for p in player_rs] == ["outer", None, None]
        await g.finish()


async def test_new_question_payload_has_no_target(game_setup, base_url, admin_token):
    """§10 test 10: clients get config (image + aspect ratio) but never the target."""
    _create(base_url, admin_token, game_setup["game_id"])
    async with HotspotGame(base_url, admin_token, game_setup, 1) as g:
        host_q, player_qs = await g.next_question()
        for payload in (host_q, *player_qs):
            assert payload["type"] == "hotspot"
            assert payload["config"] == CONFIG
            flat = json.dumps(payload)
            for secret in (
                "innerRadius",
                "outerRadius",
                "partialFraction",
                "answer_data",
            ):
                assert secret not in flat
            assert "x" not in payload and "y" not in payload
        await g.results()
        await g.finish()


# ---------------------------------------------------------------------------
# Stage B — host routes (§7.3, §6.3.3, §13.2). DEV_IMAGE exists in frontend/dev-images;
# UNKNOWN_IMAGE doesn't. Stage C: real T8 images instead.
# ---------------------------------------------------------------------------

DEV_IMAGE = 1
UNKNOWN_IMAGE = 999_999


def _host_game(hapi) -> tuple[str, int, int]:  # noqa: F811
    """A host with an empty game of their own → (token, course_id, game_id)."""
    course = hapi.course()
    _, token = hapi.host_of(course)
    return token, course, hapi.host_game(token, course, questions=0)


def _host_body(image_id: int = DEV_IMAGE, **overrides) -> dict:
    return _question_body(config={**CONFIG, "imageId": image_id}, **overrides)


def _image_error(r: httpx.Response, image_id: int) -> None:
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert body["detail"] == [
        {
            "type": "value_error",
            "loc": ["body", "config", "imageId"],
            "msg": f"Image {image_id} does not exist",
            "input": image_id,
        }
    ]


def test_host_create_unknown_image_is_422(hapi):  # noqa: F811
    """§10 test 2."""
    token, _, game = _host_game(hapi)
    r = hapi.req(
        "POST", f"/host/games/{game}/questions", token, json=_host_body(UNKNOWN_IMAGE)
    )
    _image_error(r, UNKNOWN_IMAGE)
    assert hapi.req("GET", f"/host/games/{game}/questions", token).json() == []


def test_host_create_with_dev_image(hapi):  # noqa: F811
    """Stage-B version of §10 test 3."""
    token, _, game = _host_game(hapi)
    r = hapi.req("POST", f"/host/games/{game}/questions", token, json=_host_body())
    assert r.status_code == 201, r.text
    [listed] = hapi.req("GET", f"/host/games/{game}/questions", token).json()
    assert listed["config"] == {**CONFIG, "imageId": DEV_IMAGE}
    assert listed["answer_data"] == TARGET


def test_structural_error_is_reported_before_image_lookup(hapi):  # noqa: F811
    token, _, game = _host_game(hapi)
    body = _host_body(UNKNOWN_IMAGE)
    body["config"]["aspectRatio"] = 6
    r = hapi.req("POST", f"/host/games/{game}/questions", token, json=body)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert all(e["loc"][-1] != "imageId" for e in detail), detail
    assert any("aspectRatio" in e["msg"] for e in detail), detail


_UPDATE_VIOLATIONS = {
    "aspectRatio 6": {"config": {**CONFIG, "imageId": DEV_IMAGE, "aspectRatio": 6}},
    "innerRadius > outerRadius": {"answer_data": {**TARGET, "innerRadius": 0.3}},
    "extra answer_data key": {"answer_data": {**TARGET, "z": 0}},
}


@pytest.mark.parametrize(
    "patch", _UPDATE_VIOLATIONS.values(), ids=_UPDATE_VIOLATIONS.keys()
)
def test_host_update_revalidates_hotspot(hapi, patch):  # noqa: F811
    """Stage-B version of §10 test 4: the merged question is validated (T4 D8)."""
    token, _, game = _host_game(hapi)
    q = hapi.ok("POST", f"/host/games/{game}/questions", token, json=_host_body())
    r = hapi.req("PUT", f"/host/games/{game}/questions/{q['id']}", token, json=patch)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "VALIDATION_ERROR"
    [stored] = hapi.req("GET", f"/host/games/{game}/questions", token).json()
    assert stored == q


def test_host_update_to_unknown_image_is_422(hapi):  # noqa: F811
    """Stage-B version of §10 test 5."""
    token, _, game = _host_game(hapi)
    q = hapi.ok("POST", f"/host/games/{game}/questions", token, json=_host_body())
    r = hapi.req(
        "PUT",
        f"/host/games/{game}/questions/{q['id']}",
        token,
        json={"config": {**CONFIG, "imageId": UNKNOWN_IMAGE}},
    )
    _image_error(r, UNKNOWN_IMAGE)
    [stored] = hapi.req("GET", f"/host/games/{game}/questions", token).json()
    assert stored == q


def test_host_update_checks_image_even_when_patch_omits_it(hapi):  # noqa: F811
    """§13.2 G7: a question with a dangling imageId (possible through the admin route
    until T4 phase 3) can't be edited through the host route until the image is fixed."""
    token, _, game = _host_game(hapi)
    q = hapi.ok(
        "POST", f"/admin/games/{game}/questions", json=_host_body(UNKNOWN_IMAGE)
    )
    url = f"/host/games/{game}/questions/{q['id']}"
    _image_error(hapi.req("PUT", url, token, json={"prompt": "Edited"}), UNKNOWN_IMAGE)
    r = hapi.req("PUT", url, token, json={"config": {**CONFIG, "imageId": DEV_IMAGE}})
    assert r.status_code == 200, r.text


def test_v1_bundle_with_hotspot_question_is_rejected(hapi):  # noqa: F811
    """§10 test 13b (§6.3.3): the second question is hotspot; nothing is created."""
    token, course, _ = _host_game(hapi)
    before = hapi.req("GET", f"/host/courses/{course}/games", token).json()
    mc = {
        "type": "multiple_choice",
        "grading_type": "ACCURACY",
        "prompt": "Pick A",
        "config": {"options": ["A", "B"]},
        "answer_data": {"answer_points": [1, 0]},
        "time_limit_seconds": 30,
        "points_value": 1,
    }
    bundle = {
        "format": "buzzer/game",
        "version": 1,
        "game": {"title": "v1 with hotspot"},
        "questions": [mc, _host_body()],
    }
    r = hapi.req(
        "POST",
        "/host/games/import",
        token,
        files={"file": ("g.json", json.dumps(bundle).encode())},
        data={"course_id": str(course)},
    )
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["msg"] == (
        "Question 2: hotspot questions require a version 2 bundle"
    )
    assert hapi.req("GET", f"/host/courses/{course}/games", token).json() == before


_SAMPLE_GAMES = sorted((_REPO_ROOT / "sample_games").glob("*.json"))


@pytest.mark.parametrize("path", _SAMPLE_GAMES, ids=[p.name for p in _SAMPLE_GAMES])
def test_sample_game_imports_through_host_route(hapi, path):  # noqa: F811
    """§10 test 14 (§13.1 g): every unmodified v1 sample game imports via /api/host."""
    course = hapi.course()
    _, token = hapi.host_of(course)
    r = hapi.req(
        "POST",
        "/host/games/import",
        token,
        files={"file": (path.name, path.read_bytes())},
        data={"course_id": str(course)},
    )
    assert r.status_code == 201, r.text
    hapi.track_game(r.json()["game_id"])
