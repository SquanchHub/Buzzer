"""
T7 ordering question type — integration tests (docs/plans/t7-ordering.md §9.2).

Every authoring test runs through both the admin and the host question routes, because T7
warns that create and update paths are not necessarily symmetric (O8).

Socket tests advance to results with no pause after the last answer: `on_submit_answer`
commits before it emits `answer_received`, so the results query sees every acknowledged
answer (see test_hotspot.py).
"""

from __future__ import annotations

import pytest

from .host_helpers import MC_QUESTION, hapi  # noqa: F401 — fixture

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
