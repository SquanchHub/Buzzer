"""
Unit tests for the ordering validation rules in schemas/admin.py
(docs/plans/t7-ordering.md §4.1, §9.1 cases 1–2). Pure functions — no stack needed.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_ordering_schema.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.admin import (
    QuestionCreate,
    ordering_answer_error,
    ordering_config_error,
)

ITEMS = ["Anaphase", "Prophase", "Telophase", "Metaphase"]
ANSWER = {"correctOrder": [1, 3, 0, 2], "partialCredit": True}

LIST_MSG = "ordering items must be a list of 3 to 6 strings"


def _config(items) -> dict:
    return {"items": items}


# ---------------------------------------------------------------------------
# Case 1 — ordering_config_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [3, 6])
def test_valid_configs(n):
    assert ordering_config_error(_config([f"Item {i}" for i in range(n)])) is None


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ("items", "ordering config must have exactly 'items'"),
        ({}, "ordering config must have exactly 'items'"),
        (
            {"items": ITEMS, "extra": 1},
            "ordering config must have exactly 'items'",
        ),
        (_config("abc"), LIST_MSG),
        (_config(["a", "b"]), LIST_MSG),
        (_config([f"x{i}" for i in range(7)]), LIST_MSG),
        (_config(["a", "b", 3]), LIST_MSG),
        (_config(["a", "", "c"]), "ordering item 2 must be 1 to 80 characters"),
        (_config(["a", "b", "x" * 81]), "ordering item 3 must be 1 to 80 characters"),
        (
            _config([" Prophase", "b", "c"]),
            "ordering item 1 must not have leading, trailing or repeated spaces",
        ),
        (
            _config(["a", "Pro  phase", "c"]),
            "ordering item 2 must not have leading, trailing or repeated spaces",
        ),
        (
            _config(["a", "b", "a\nb"]),
            "ordering item 3 must not have leading, trailing or repeated spaces",
        ),
        (_config(["Mitosis", "b", "mitosis"]), "ordering items must be unique"),
    ],
    ids=[
        "not a dict",
        "missing items",
        "extra key",
        "items not a list",
        "2 items",
        "7 items",
        "non-string item",
        "empty item",
        "81 characters",
        "leading space",
        "double space",
        "newline",
        "case-insensitive duplicate",
    ],
)
def test_config_violations(config, message):
    assert ordering_config_error(config) == message


def test_80_characters_is_allowed():
    assert ordering_config_error(_config(["a", "b", "x" * 80])) is None


def test_check_order_length_before_whitespace_before_duplicates():
    # Item 1 breaks whitespace, item 2 is too long: the earlier index wins (§4.1 order).
    assert ordering_config_error(_config([" a", "x" * 81, "c"])) == (
        "ordering item 1 must not have leading, trailing or repeated spaces"
    )
    # A duplicate pair plus a bad item later: per-item checks run before duplicates.
    assert ordering_config_error(_config(["a", "a", " c"])) == (
        "ordering item 3 must not have leading, trailing or repeated spaces"
    )


# ---------------------------------------------------------------------------
# Case 2 — ordering_answer_error
# ---------------------------------------------------------------------------

KEYS_MSG = (
    "ACCURACY ordering answer_data must have exactly 'correctOrder' and 'partialCredit'"
)
PERM_MSG = "ordering correctOrder must list each item index 0..3 exactly once"
IDENTITY_MSG = (
    "ordering items must be stored in a shuffled order, not the correct order"
)
PARTIAL_MSG = "ordering partialCredit must be true or false"


def test_valid_answer():
    assert ordering_answer_error(_config(ITEMS), ANSWER) is None
    assert (
        ordering_answer_error(_config(ITEMS), {**ANSWER, "partialCredit": False})
        is None
    )


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (None, KEYS_MSG),
        ({"correctOrder": [1, 3, 0, 2]}, KEYS_MSG),
        ({**ANSWER, "extra": 1}, KEYS_MSG),
        ({**ANSWER, "correctOrder": [1, 3, 0]}, PERM_MSG),
        ({**ANSWER, "correctOrder": [1, 3, 0, 0]}, PERM_MSG),
        ({**ANSWER, "correctOrder": [1, 3, 0, 4]}, PERM_MSG),
        ({**ANSWER, "correctOrder": [1, 3, True, 2]}, PERM_MSG),
        ({**ANSWER, "correctOrder": "1302"}, PERM_MSG),
        ({**ANSWER, "correctOrder": [0, 1, 2, 3]}, IDENTITY_MSG),
        ({**ANSWER, "partialCredit": 1}, PARTIAL_MSG),
        ({**ANSWER, "partialCredit": "yes"}, PARTIAL_MSG),
    ],
    ids=[
        "not a dict",
        "missing partialCredit",
        "extra key",
        "wrong length",
        "duplicate index",
        "out of range",
        "bool index",
        "string",
        "identity",
        "partialCredit 1",
        "partialCredit string",
    ],
)
def test_answer_violations(answer, message):
    assert ordering_answer_error(_config(ITEMS), answer) == message


def test_invalid_config_is_reported_first():
    assert ordering_answer_error(_config(["a", "b"]), ANSWER) == LIST_MSG


# ---------------------------------------------------------------------------
# QuestionCreate wiring (§6.1)
# ---------------------------------------------------------------------------


def _body(**overrides) -> dict:
    body = {
        "type": "ordering",
        "grading_type": "ACCURACY",
        "prompt": "Put the phases of mitosis in order, first to last.",
        "config": _config(ITEMS),
        "answer_data": dict(ANSWER),
        "points_value": 1000,
    }
    body.update(overrides)
    return body


def test_question_create_accepts_valid_ordering():
    q = QuestionCreate(**_body())
    assert q.config == _config(ITEMS)


def test_question_create_raises_with_the_checker_message():
    with pytest.raises(ValidationError, match="not the correct order"):
        QuestionCreate(**_body(answer_data={**ANSWER, "correctOrder": [0, 1, 2, 3]}))


def test_completeness_checks_config_but_not_answer_data():
    QuestionCreate(**_body(grading_type="COMPLETENESS", answer_data={}))
    QuestionCreate(**_body(grading_type="COMPLETENESS", answer_data={"junk": 1}))
    with pytest.raises(ValidationError, match="3 to 6 strings"):
        QuestionCreate(**_body(grading_type="COMPLETENESS", config=_config(["a", "b"])))
