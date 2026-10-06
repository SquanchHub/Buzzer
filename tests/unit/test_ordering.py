"""
Unit tests for the ordering helpers in game_service (docs/plans/t7-ordering.md §4.3–4.6,
§9.1 cases 3–7). Pure functions — no database, Redis or Docker stack needed.

Run with:
    cd tests/unit && PYTHONPATH=../../backend pytest test_ordering.py -v
"""

from __future__ import annotations

from itertools import combinations, permutations
from types import SimpleNamespace

import pytest
from structlog.testing import capture_logs

from app.services.game_service import (
    OrderingKey,
    calculate_score,
    ordering_dist_key,
    ordering_item_count,
    ordering_key,
    ordering_mean_positions,
    ordering_outcome,
    ordering_result,
    ordering_reveal,
    ordering_submission,
)

# Display order A..F is the identity; the tests below use correct orders over letters.
LETTERS = "ABCDEF"


def _brute_lis(seq: list[int]) -> int:
    """Longest strictly increasing subsequence by brute force (independent of the DP)."""
    for size in range(len(seq), 0, -1):
        for idx in combinations(range(len(seq)), size):
            vals = [seq[i] for i in idx]
            if all(a < b for a, b in zip(vals, vals[1:])):
                return size
    return 0


def _key(correct: str, display: str, partial: bool = True) -> OrderingKey:
    """A key where `display` is what players see and `correct` the right order."""
    return OrderingKey(
        correct_order=tuple(display.index(ch) for ch in correct),
        partial_credit=partial,
    )


def _sub(submitted: str, display: str) -> tuple[int, ...]:
    return tuple(display.index(ch) for ch in submitted)


def _question(items: list[str], answer_data, grading="ACCURACY", points=1000.0):
    return SimpleNamespace(
        id=7,
        type="ordering",
        grading_type=grading,
        config={"items": items},
        answer_data=answer_data,
        points_value=points,
    )


# ---------------------------------------------------------------------------
# Case 3 — ordering_key never raises; logs once on bad data
# ---------------------------------------------------------------------------

CONFIG4 = {"items": ["Anaphase", "Prophase", "Telophase", "Metaphase"]}
ANSWER4 = {"correctOrder": [1, 3, 0, 2], "partialCredit": True}


def test_ordering_key_parses_valid_data():
    assert ordering_key(1, CONFIG4, ANSWER4) == OrderingKey((1, 3, 0, 2), True)


@pytest.mark.parametrize(
    ("config", "answer_data"),
    [
        (CONFIG4, None),
        (CONFIG4, []),
        (CONFIG4, "x"),
        (CONFIG4, {"correctOrder": "0123"}),
        (CONFIG4, {"correctOrder": [0, 1, 2, 3], "partialCredit": True}),
        (CONFIG4, {"correctOrder": [1, 3, 0], "partialCredit": True}),
        (CONFIG4, {"correctOrder": [1, 3, 0, 2]}),
        (None, ANSWER4),
    ],
    ids=[
        "None",
        "list",
        "string",
        "string order",
        "identity",
        "wrong length",
        "no partialCredit",
        "config None",
    ],
)
def test_ordering_key_returns_none_and_logs(config, answer_data):
    with capture_logs() as logs:
        assert ordering_key(42, config, answer_data) is None
    assert [e["event"] for e in logs] == ["ordering_key_invalid"]
    assert logs[0]["question_id"] == 42


def test_ordering_item_count():
    assert ordering_item_count(1, CONFIG4) == 4
    with capture_logs() as logs:
        assert ordering_item_count(5, {"items": ["a", "b"]}) is None
    assert [e["event"] for e in logs] == ["ordering_config_invalid"]


# ---------------------------------------------------------------------------
# Case 4 — ordering_result: run length and the §4.3 tie-break
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [3, 4, 5])
def test_in_order_matches_brute_force_for_every_permutation(n):
    # Use a non-identity correct order so display index != rank.
    correct = tuple(reversed(range(n)))
    key = OrderingKey(correct, True)
    rank = {d: k for k, d in enumerate(correct)}
    for order in permutations(range(n)):
        res = ordering_result(key, order)
        assert res.in_order == _brute_lis([rank[d] for d in order])
        assert res.total == n
        assert len(res.out_of_place) == n - res.in_order
        assert set(res.out_of_place) <= set(order)
        # The items kept "in order" really are increasing in correct position.
        kept = [rank[d] for d in order if d not in res.out_of_place]
        assert len(kept) == res.in_order
        assert all(a < b for a, b in zip(kept, kept[1:]))
        assert res.exact == (order == correct)


# (correct, submitted, L, out-of-place items in submission order) — §4.3 and §4.5.
_TIE_BREAKS = [
    ("ABCD", "ABCD", 4, ""),
    ("ABCD", "DABC", 3, "D"),
    ("ABCD", "BACD", 3, "A"),
    ("ABCD", "BADC", 2, "AC"),
    ("ABCD", "DCBA", 1, "CBA"),
    ("ABC", "BAC", 2, "A"),
    ("ABCDE", "BCDEA", 4, "A"),
]


@pytest.mark.parametrize(("correct", "submitted", "length", "out"), _TIE_BREAKS)
def test_tie_break_examples(correct, submitted, length, out):
    display = "".join(sorted(correct, reverse=True))  # any fixed display order works
    res = ordering_result(_key(correct, display), _sub(submitted, display))
    assert res.in_order == length
    assert "".join(display[d] for d in res.out_of_place) == out


# ---------------------------------------------------------------------------
# Case 5 — calculate_score (§4.5 table)
# ---------------------------------------------------------------------------

# (correct, submitted, partial-credit points, is_correct)
_SCORES = [
    ("ABCD", "ABCD", 1000, True),
    ("ABCD", "DABC", 666.67, False),
    ("ABCD", "BACD", 666.67, False),
    ("ABCD", "BADC", 333.33, False),
    ("ABCD", "DCBA", 0, False),
    ("ABC", "BAC", 500, False),
    ("ABCDE", "BCDEA", 750, False),
    ("ABCDEF", "ABDEFC", 800, False),
]


@pytest.mark.parametrize(("correct", "submitted", "points", "exact"), _SCORES)
@pytest.mark.parametrize("partial", [True, False])
def test_calculate_score_table(correct, submitted, points, exact, partial):
    display = correct[1:] + correct[0]  # a rotation: never the identity
    items = list(display)
    key = _key(correct, display, partial)
    q = _question(
        items,
        {"correctOrder": list(key.correct_order), "partialCredit": partial},
    )
    res = calculate_score(q, {"order": list(_sub(submitted, display))})
    expected = points if (partial or exact) else 0
    assert res.points_awarded == pytest.approx(expected)
    assert res.is_correct == exact


def test_completeness_scores_any_order_full():
    q = _question(list("ABCD"), {}, grading="COMPLETENESS")
    res = calculate_score(q, {"order": [3, 2, 1, 0]})
    assert (res.points_awarded, res.is_correct) == (1000.0, True)


def test_empty_answer_scores_zero():
    q = _question(CONFIG4["items"], ANSWER4)
    res = calculate_score(q, {})
    assert (res.points_awarded, res.is_correct) == (0, False)


def test_invalid_key_scores_a_miss():
    q = _question(
        CONFIG4["items"], {"correctOrder": [0, 1, 2, 3], "partialCredit": True}
    )
    with capture_logs():
        res = calculate_score(q, {"order": [0, 1, 2, 3]})
    assert (res.points_awarded, res.is_correct) == (0, False)


def test_invalid_submission_scores_a_miss():
    q = _question(CONFIG4["items"], ANSWER4)
    res = calculate_score(q, {"order": [1, 3, 0]})
    assert (res.points_awarded, res.is_correct) == (0, False)


def test_zero_points_exact_is_still_correct():
    q = _question(CONFIG4["items"], ANSWER4, points=0)
    res = calculate_score(q, {"order": [1, 3, 0, 2]})
    assert (res.points_awarded, res.is_correct) == (0, True)


# ---------------------------------------------------------------------------
# Case 6 — ordering_submission
# ---------------------------------------------------------------------------


def test_submission_accepts_a_permutation():
    assert ordering_submission({"order": [2, 0, 1], "extra": 1}, 3) == (2, 0, 1)


@pytest.mark.parametrize(
    "answer_data",
    [
        None,
        [0, 1, 2],
        {},
        {"order": "012"},
        {"order": [0, 1]},
        {"order": [0, 1, 1]},
        {"order": [0, 1, 3]},
        {"order": [True, 0, 2]},
        {"order": ["0", "1", "2"]},
        {"order": [0.0, 1, 2]},
    ],
    ids=[
        "None",
        "bare list",
        "no order",
        "string",
        "short",
        "duplicate",
        "out of range",
        "bool",
        "strings",
        "float",
    ],
)
def test_submission_rejects(answer_data):
    assert ordering_submission(answer_data, 3) is None


# ---------------------------------------------------------------------------
# Case 7 — reveal, outcome, distribution key, mean positions
# ---------------------------------------------------------------------------


def test_reveal_outcome_and_dist_key():
    key = OrderingKey((1, 3, 0, 2), True)
    assert ordering_reveal(key) == {"type": "ordering", "correctOrder": [1, 3, 0, 2]}
    assert ordering_reveal(None) == {"type": "ordering"}
    # M P A T: r = [1, 0, 2, 3]; the §4.3 tie-break keeps M A T, so Prophase (1) is out.
    res = ordering_result(key, (3, 1, 0, 2))
    assert ordering_outcome(res) == {"inOrder": 3, "total": 4, "outOfPlace": [1]}
    assert ordering_outcome(None) is None
    assert ordering_dist_key(res) == "1"
    assert ordering_dist_key(ordering_result(key, key.correct_order)) == "0"


def test_mean_positions():
    orders = [(0, 1, 2), (2, 1, 0)]
    assert ordering_mean_positions(3, orders) == [2.0, 2.0, 2.0]
    assert ordering_mean_positions(3, [(1, 0, 2), (1, 2, 0), (0, 1, 2)]) == [
        2.0,
        1.33,
        2.67,
    ]
    assert ordering_mean_positions(3, []) == [None, None, None]
