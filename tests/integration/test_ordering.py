"""
T7 ordering question type — integration tests (docs/plans/t7-ordering.md §9.2).

Every authoring test runs through both the admin and the host question routes, because T7
warns that create and update paths are not necessarily symmetric (O8).

Socket tests advance to results with no pause after the last answer: `on_submit_answer`
commits before it emits `answer_received`, so the results query sees every acknowledged
answer (see test_hotspot.py).
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from .conftest import create_guest_tokens, create_room
from .host_helpers import MC_QUESTION, hapi, mysql  # noqa: F401 — fixture
from .image_helpers import png

# Aliased so pytest doesn't try to collect the Test-prefixed class from this module.
from .engine.socket_client import TestSocketClient as SocketClient

ITEMS = ["Anaphase", "Prophase", "Telophase", "Metaphase"]
# Correct order: Prophase, Metaphase, Anaphase, Telophase.
ANSWER = {"correctOrder": [1, 3, 0, 2], "partialCredit": True}

ROUTES = ["admin", "host"]


def _body(**overrides) -> dict:
    body = {
        "type": "ordering",
        "grading_type": "ACCURACY",
        "prompt": "Put the phases of mitosis in order, first to last.",
        "config": {"items": list(ITEMS)},
        "answer_data": dict(ANSWER),
        "time_limit_seconds": 60,
        "points_value": 1000,
    }
    body.update(overrides)
    return body


class Author:
    """One game reachable through one question route (admin or host)."""

    def __init__(self, hapi, route: str):  # noqa: F811
        self.hapi = hapi
        course = hapi.course()
        _, host_token = hapi.host_of(course)
        self.game = hapi.host_game(host_token, course, questions=0)
        self.course = course
        self.host_token = host_token
        self.route = route
        # The admin routes need an admin token; the host routes use the game's host.
        self.token = hapi.admin if route == "admin" else host_token

    def _path(self, suffix: str = "") -> str:
        return f"/{self.route}/games/{self.game}/questions{suffix}"

    def create(self, body: dict):
        return self.hapi.req("POST", self._path(), self.token, json=body)

    def update(self, qid: int, patch: dict):
        return self.hapi.req("PUT", self._path(f"/{qid}"), self.token, json=patch)

    def questions(self) -> list[dict]:
        return self.hapi.ok("GET", self._path(), self.token)


def _assert_422(r, message: str) -> None:
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"] == "VALIDATION_ERROR"
    # Pydantic prefixes model-validator messages with "Value error, " (§4.1).
    assert any(message in e["msg"] for e in body["detail"]), body["detail"]


# ---------------------------------------------------------------------------
# §9.2 test 1 — create rejects each violation, on both routes
# ---------------------------------------------------------------------------

_CREATE_VIOLATIONS = {
    "2 items": (
        {"config": {"items": ["a", "b"]}},
        "ordering items must be a list of 3 to 6 strings",
    ),
    "extra config key": (
        {"config": {"items": ITEMS, "labels": ["first", "last"]}},
        "ordering config must have exactly 'items'",
    ),
    "duplicate items": (
        {"config": {"items": ["Prophase", "prophase", "Anaphase"]}},
        "ordering items must be unique",
    ),
    "item with double space": (
        {"config": {"items": ["Pro  phase", "Anaphase", "Telophase"]}},
        "ordering item 1 must not have leading, trailing or repeated spaces",
    ),
    "81 characters": (
        {"config": {"items": ["a", "b", "x" * 81]}},
        "ordering item 3 must be 1 to 80 characters",
    ),
    "missing partialCredit": (
        {"answer_data": {"correctOrder": [1, 3, 0, 2]}},
        "must have exactly 'correctOrder' and 'partialCredit'",
    ),
    "not a permutation": (
        {"answer_data": {**ANSWER, "correctOrder": [1, 3, 0, 0]}},
        "ordering correctOrder must list each item index 0..3 exactly once",
    ),
    "identity": (
        {"answer_data": {**ANSWER, "correctOrder": [0, 1, 2, 3]}},
        "ordering items must be stored in a shuffled order, not the correct order",
    ),
    "partialCredit 1": (
        {"answer_data": {**ANSWER, "partialCredit": 1}},
        "ordering partialCredit must be true or false",
    ),
    "optionImageIds": (
        {"config": {"items": ITEMS, "optionImageIds": [None] * 4}},
        "optionImageIds is only allowed on multiple_choice and multi_select",
    ),
}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    ("overrides", "message"),
    _CREATE_VIOLATIONS.values(),
    ids=_CREATE_VIOLATIONS.keys(),
)
def test_create_rejects_each_violation(hapi, route, overrides, message):  # noqa: F811
    a = Author(hapi, route)
    _assert_422(a.create(_body(**overrides)), message)
    assert a.questions() == []


# ---------------------------------------------------------------------------
# §9.2 test 2 — valid creates are stored exactly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_create_valid_questions(hapi, route):  # noqa: F811
    a = Author(hapi, route)
    bodies = [
        _body(),
        _body(answer_data={**ANSWER, "partialCredit": False}),
        _body(
            grading_type="COMPLETENESS",
            prompt="Rank these pizza toppings, favourite first.",
            config={"items": ["Pepperoni", "Mushrooms", "Pineapple"]},
            answer_data={},
        ),
    ]
    for body in bodies:
        r = a.create(body)
        assert r.status_code == 201, r.text
    stored = a.questions()
    assert [(q["type"], q["config"], q["answer_data"]) for q in stored] == [
        ("ordering", b["config"], b["answer_data"]) for b in bodies
    ]


@pytest.mark.parametrize("route", ROUTES)
def test_completeness_still_checks_config(hapi, route):  # noqa: F811
    a = Author(hapi, route)
    r = a.create(
        _body(grading_type="COMPLETENESS", config={"items": ["a", "b"]}, answer_data={})
    )
    _assert_422(r, "ordering items must be a list of 3 to 6 strings")


# ---------------------------------------------------------------------------
# §9.2 test 3 — update re-validates the merged question (symmetry, O8)
# ---------------------------------------------------------------------------

_UPDATE_VIOLATIONS = {
    "7 items": (
        {"config": {"items": [f"Step {i}" for i in range(7)]}},
        "ordering items must be a list of 3 to 6 strings",
    ),
    "identity correctOrder": (
        {"answer_data": {**ANSWER, "correctOrder": [0, 1, 2, 3]}},
        "not the correct order",
    ),
    # Cross-field: valid 5-item config on its own, but the stored correctOrder has 4.
    "5 items with a 4-entry correctOrder": (
        {"config": {"items": ITEMS + ["Cytokinesis"]}},
        "ordering correctOrder must list each item index 0..4 exactly once",
    ),
    # The merge is per field: an answer_data patch replaces it whole (§9.2 test 3).
    "partialCredit string": (
        {"answer_data": {**ANSWER, "partialCredit": "yes"}},
        "ordering partialCredit must be true or false",
    ),
}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    ("patch", "message"),
    _UPDATE_VIOLATIONS.values(),
    ids=_UPDATE_VIOLATIONS.keys(),
)
def test_update_revalidates(hapi, route, patch, message):  # noqa: F811
    a = Author(hapi, route)
    r = a.create(_body())
    assert r.status_code == 201, r.text
    q = r.json()
    _assert_422(a.update(q["id"], patch), message)
    [stored] = a.questions()
    assert stored == q


@pytest.mark.parametrize("route", ROUTES)
def test_valid_update_is_stored(hapi, route):  # noqa: F811
    a = Author(hapi, route)
    q = a.create(_body()).json()
    patch = {
        "config": {"items": ["Telophase", "Anaphase", "Prophase", "Metaphase"]},
        "answer_data": {"correctOrder": [2, 3, 1, 0], "partialCredit": False},
    }
    r = a.update(q["id"], patch)
    assert r.status_code == 200, r.text
    [stored] = a.questions()
    assert stored["config"] == patch["config"]
    assert stored["answer_data"] == patch["answer_data"]


# ---------------------------------------------------------------------------
# §9.2 test 4 — type changes are validated against the kept fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES)
def test_type_change_to_ordering_keeps_mc_config_and_fails(hapi, route):  # noqa: F811
    a = Author(hapi, route)
    mc = a.create(MC_QUESTION).json()
    _assert_422(
        a.update(mc["id"], {"type": "ordering"}),
        "ordering config must have exactly 'items'",
    )
    assert a.questions() == [mc]


@pytest.mark.parametrize("route", ROUTES)
def test_type_change_from_ordering_keeps_items_and_fails(hapi, route):  # noqa: F811
    a = Author(hapi, route)
    q = a.create(_body()).json()
    r = a.update(q["id"], {"type": "multiple_choice"})
    assert r.status_code == 422, r.text
    assert a.questions() == [q]


# ---------------------------------------------------------------------------
# Live game over Socket.io (§9.2 tests 5–11)
# ---------------------------------------------------------------------------

_TIMEOUT = 10.0
# See test_hotspot.py: host_advance emits results before it records the RESULTS phase.
_RESULTS_SETTLE_S = 0.3

ORDER_ERROR = "ordering answer must list every item exactly once"
# Display: Anaphase(0) Prophase(1) Telophase(2) Metaphase(3); correct: P M A T.
EXACT = [1, 3, 0, 2]
ONE_MOVED = [2, 1, 3, 0]  # T P M A: Telophase moved to the front
TWO_SWAPS = [3, 1, 2, 0]  # M P T A
REVERSED = [2, 0, 3, 1]  # T A M P


class OrderingGame:
    """A live room: host + N guest players over Socket.io, driven step by step."""

    def __init__(self, base_url: str, admin_token: str, setup: dict, n_players: int):
        self.base_url = base_url
        self.admin_token = admin_token
        self.setup = setup
        self.n_players = n_players
        self._after_results = False

    async def __aenter__(self) -> OrderingGame:
        room = create_room(
            self.base_url,
            self.admin_token,
            self.setup["course_id"],
            self.setup["game_id"],
        )
        self.room = room
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
            await asyncio.sleep(_RESULTS_SETTLE_S)
        await self.host.emit("host_advance", {})

    async def next_question(self) -> tuple[dict, list[dict]]:
        await self._advance()
        host_q = await self.host.wait_for("new_question")
        player_qs = [await p.wait_for("new_question") for p in self.players]
        self._after_results = False
        return host_q, player_qs

    async def submit(self, i: int, question_id: int, answer_data) -> dict:
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
        await self._advance()
        host_r = await self.host.wait_for("question_results")
        player_rs = [await p.wait_for("question_results") for p in self.players]
        self._after_results = True
        return host_r, player_rs

    async def finish(self) -> tuple[dict, list[dict]]:
        await self._advance()
        host_over = await self.host.wait_for("game_over")
        player_overs = [await p.wait_for("game_over") for p in self.players]
        return host_over, player_overs


async def _nothing(client: SocketClient, event: str, wait: float = 0.5) -> bool:
    try:
        await client.wait_for(event, wait)
    except (asyncio.TimeoutError, TimeoutError):
        return True
    return False


def _create(base_url: str, token: str, game_id: int, **overrides) -> int:
    r = httpx.post(
        f"{base_url}/api/admin/games/{game_id}/questions",
        json=_body(**overrides),
        headers={"Authorization": f"Bearer {token}"},
        timeout=_TIMEOUT,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _keys(obj) -> set[str]:
    """Every dict key anywhere inside `obj`."""
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


async def test_new_question_payload_has_no_answer_key(
    game_setup, base_url, admin_token
):
    """§9.2 test 5."""
    _create(base_url, admin_token, game_setup["game_id"])
    async with OrderingGame(base_url, admin_token, game_setup, 1) as g:
        host_q, player_qs = await g.next_question()
        for payload in (host_q, *player_qs):
            assert payload["type"] == "ordering"
            assert payload["config"] == {"items": ITEMS}
            assert not _keys(payload) & {"correctOrder", "partialCredit", "answer_data"}
        await g.results()
        await g.finish()


@pytest.mark.parametrize(
    ("partial", "expected"),
    [(True, [1000.0, 666.67, 333.33, 0]), (False, [1000.0, 0, 0, 0])],
    ids=["partial credit", "exact only"],
)
async def test_scoring_over_sockets(
    game_setup, base_url, admin_token, partial, expected
):
    """§9.2 test 6."""
    qid = _create(
        base_url,
        admin_token,
        game_setup["game_id"],
        answer_data={**ANSWER, "partialCredit": partial},
    )
    async with OrderingGame(base_url, admin_token, game_setup, 4) as g:
        await g.next_question()
        acks = [
            await g.submit(i, qid, {"order": order})
            for i, order in enumerate([EXACT, ONE_MOVED, TWO_SWAPS, REVERSED])
        ]
        assert [a["pointsAwarded"] for a in acks] == pytest.approx(expected)
        assert [a["isCorrect"] for a in acks] == [True, False, False, False]
        await g.results()
        host_over, _ = await g.finish()
        [summary] = host_over["questionSummary"]
        assert summary["correctCount"] == 1


async def test_completeness_any_order_scores_full(game_setup, base_url, admin_token):
    """§9.2 test 7."""
    qid = _create(
        base_url,
        admin_token,
        game_setup["game_id"],
        grading_type="COMPLETENESS",
        config={"items": ["Pepperoni", "Mushrooms", "Pineapple"]},
        answer_data={},
    )
    async with OrderingGame(base_url, admin_token, game_setup, 2) as g:
        await g.next_question()
        a = await g.submit(0, qid, {"order": [2, 0, 1]})
        b = await g.submit(1, qid, {"order": [2, 1, 0]})
        assert (a["pointsAwarded"], a["isCorrect"]) == (1000.0, True)
        assert b["pointsAwarded"] == 1000.0
        host_r, player_rs = await g.results()
        assert host_r["answerReveal"] == {"type": "completeness"}
        assert host_r["answerDistribution"] == {}
        # Pepperoni: 2nd and 3rd; Mushrooms: 3rd and 2nd; Pineapple: 1st twice.
        assert host_r["meanPositions"] == [2.5, 2.5, 1.0]
        assert [p["yourOrdering"] for p in player_rs] == [None, None]
        await g.finish()


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"order": "1302"},
        {"order": [1, 3, 0]},
        {"order": [1, 3, 0, 0]},
        {"order": [1, 3, 0, 4]},
        {"order": [True, 3, 0, 2]},
        {"order": ["1", "3", "0", "2"]},
    ],
    ids=["missing", "not a list", "short", "duplicate", "index n", "bool", "strings"],
)
async def test_malformed_submission_is_rejected(game_setup, base_url, admin_token, bad):
    """§9.2 test 8: socket `error`, nothing recorded, and a valid order still works."""
    qid = _create(base_url, admin_token, game_setup["game_id"])
    async with OrderingGame(base_url, admin_token, game_setup, 1) as g:
        await g.next_question()
        await g.players[0].emit(
            "submit_answer",
            {"question_id": qid, "answer_data": bad, "answer_time_ms": 100},
        )
        err = await g.players[0].wait_for("error")
        assert err["message"] == ORDER_ERROR
        assert await _nothing(g.players[0], "answer_received")
        ok = await g.submit(0, qid, {"order": EXACT, "extra": "dropped"})
        assert ok["pointsAwarded"] == 1000.0
        host_r, _ = await g.results()
        assert host_r["totalAnswered"] == 1
        await g.finish()


async def test_results_payloads(game_setup, base_url, admin_token):
    """§9.2 test 9: host gets the reveal, distribution and room order; each player gets
    the reveal and their own yourOrdering, never meanPositions."""
    qid = _create(base_url, admin_token, game_setup["game_id"])
    async with OrderingGame(base_url, admin_token, game_setup, 4) as g:
        await g.next_question()
        for i, order in enumerate([EXACT, ONE_MOVED, ONE_MOVED]):
            await g.submit(i, qid, {"order": order})  # player 3 does not answer
        host_r, player_rs = await g.results()
        reveal = {"type": "ordering", "correctOrder": EXACT}
        assert host_r["answerReveal"] == reveal
        assert host_r["answerDistribution"] == {"0": 1, "1": 2}
        # Display item d's 1-based position in EXACT, ONE_MOVED, ONE_MOVED:
        # A: 3,4,4  P: 1,2,2  T: 4,1,1  M: 2,3,3
        assert host_r["meanPositions"] == [3.67, 1.67, 2.0, 2.67]
        assert "yourOrdering" not in host_r
        assert all(p["answerReveal"] == reveal for p in player_rs)
        assert [p["yourOrdering"] for p in player_rs] == [
            {"inOrder": 4, "total": 4, "outOfPlace": []},
            {"inOrder": 3, "total": 4, "outOfPlace": [2]},  # Telophase
            {"inOrder": 3, "total": 4, "outOfPlace": [2]},
            None,
        ]
        assert not any("meanPositions" in p for p in player_rs)
        await g.finish()


async def test_game_over_summaries(game_setup, base_url, admin_token):
    """§9.2 test 10."""
    qid = _create(base_url, admin_token, game_setup["game_id"])
    async with OrderingGame(base_url, admin_token, game_setup, 2) as g:
        await g.next_question()
        await g.submit(0, qid, {"order": EXACT})
        await g.submit(1, qid, {"order": REVERSED})
        await g.results()
        host_over, player_overs = await g.finish()
        [h] = host_over["questionSummary"]
        assert h["answerReveal"] == {"type": "ordering", "correctOrder": EXACT}
        assert h["answerDistribution"] == {"0": 1, "3": 1}
        assert h["meanPositions"] == [2.5, 2.5, 2.5, 2.5]  # exact + reversed
        [p0] = player_overs[0]["questionSummary"]
        assert p0["playerAnswer"] == {"order": EXACT}
        assert p0["answerReveal"] == {"type": "ordering", "correctOrder": EXACT}


@pytest.mark.parametrize(
    "bad_sql",
    [
        "JSON_SET(answer_data, '$.correctOrder', JSON_ARRAY(0, 1, 2, 3))",
        "JSON_SET(answer_data, '$.correctOrder', JSON_ARRAY(1, 0, 2))",
        "JSON_REMOVE(answer_data, '$.partialCredit')",
    ],
    ids=["identity", "wrong length", "partialCredit missing"],
)
async def test_bad_stored_key_scores_zero_without_crashing(
    game_setup, base_url, admin_token, bad_sql
):
    """§9.2 test 11: bad data planted after create (both write paths validate)."""
    qid = _create(base_url, admin_token, game_setup["game_id"])
    mysql(f"UPDATE questions SET answer_data = {bad_sql} WHERE id = {int(qid)}")
    async with OrderingGame(base_url, admin_token, game_setup, 1) as g:
        await g.next_question()
        a = await g.submit(0, qid, {"order": EXACT})
        assert (a["pointsAwarded"], a["isCorrect"]) == (0, False)
        host_r, [p] = await g.results()
        assert host_r["answerReveal"] == {"type": "ordering"}
        assert p["answerReveal"] == {"type": "ordering"}
        assert p["yourOrdering"] is None
        assert host_r["meanPositions"] == [3.0, 1.0, 4.0, 2.0]
        host_over, _ = await g.finish()
        assert host_over["questionSummary"][0]["answerReveal"] == {"type": "ordering"}


# ---------------------------------------------------------------------------
# §9.2 tests 12–14 — export / import (§5: no code change needed)
# ---------------------------------------------------------------------------


def _import(hapi, route: str, course: int, bundle: dict, token: str):  # noqa: F811
    return hapi.req(
        "POST",
        f"/{route}/games/import",
        token,
        files={"file": ("g.json", json.dumps(bundle).encode(), "application/json")},
        data={"course_id": str(course)},
    )


def _stored(q: dict) -> tuple:
    return (q["type"], q["grading_type"], q["config"], q["answer_data"])


def test_export_import_version_1_round_trip(hapi):  # noqa: F811
    """§9.2 test 12: an ordering-only game exports as version 1 and re-imports the
    question unchanged (the stored shuffle and key survive byte for byte)."""
    a = Author(hapi, "host")
    for body in (
        _body(),
        _body(
            grading_type="COMPLETENESS",
            config={"items": ["Pepperoni", "Mushrooms", "Pineapple"]},
            answer_data={},
        ),
    ):
        assert a.create(body).status_code == 201
    originals = a.questions()
    bundle = hapi.ok("GET", f"/host/games/{a.game}/export", a.host_token)
    assert bundle["version"] == 1
    assert [q["config"] for q in bundle["questions"]] == [
        q["config"] for q in originals
    ]
    assert [q["answer_data"] for q in bundle["questions"]] == [
        q["answer_data"] for q in originals
    ]

    target = hapi.course()
    _, token = hapi.host_of(target)
    r = _import(hapi, "host", target, bundle, token)
    assert r.status_code == 201, r.text
    copy = hapi.track_game(r.json()["game_id"])
    imported = hapi.ok("GET", f"/host/games/{copy}/questions", token)
    assert [_stored(q) for q in imported] == [_stored(q) for q in originals]


@pytest.mark.parametrize("route", ROUTES)
def test_export_import_version_2_with_prompt_image(hapi, route):  # noqa: F811
    """§9.2 test 13: a T8 prompt image on an ordering question makes the bundle
    version 2; the round trip gives a new image id and leaves the ordering data alone."""
    a = Author(hapi, "host")
    image = hapi.image(a.course, png((30, 20)), a.host_token)
    q = a.create(_body(prompt_image_id=image)).json()
    token = hapi.admin if route == "admin" else a.host_token
    bundle = hapi.ok("GET", f"/{route}/games/{a.game}/export", token)
    assert bundle["version"] == 2
    [exported] = bundle["questions"]
    assert exported["prompt_image_ref"] == bundle["images"][0]["ref"]
    assert exported["config"] == q["config"]

    target = hapi.course()
    _, target_host = hapi.host_of(target)
    r = _import(
        hapi, route, target, bundle, hapi.admin if route == "admin" else target_host
    )
    assert r.status_code == 201, r.text
    copy = hapi.track_game(r.json()["game_id"])
    [imported] = hapi.ok("GET", f"/admin/games/{copy}/questions")
    hapi._images.append(imported["prompt_image_id"])
    assert imported["prompt_image_id"] not in (None, image)
    assert _stored(imported) == _stored(q)


def test_import_rejects_unshuffled_ordering_question(hapi):  # noqa: F811
    """§9.2 test 14: a real export with its correctOrder edited to the identity."""
    a = Author(hapi, "host")
    assert a.create(_body()).status_code == 201
    bundle = hapi.ok("GET", f"/host/games/{a.game}/export", a.host_token)
    bundle["questions"][0]["answer_data"]["correctOrder"] = [0, 1, 2, 3]
    course = hapi.course()
    _, token = hapi.host_of(course)
    r = _import(hapi, "host", course, bundle, token)
    assert r.status_code == 422, r.text
    assert "Question 1 invalid" in r.text
    assert "shuffled order" in r.text
    assert hapi.ok("GET", f"/host/courses/{course}/games", token) == []
