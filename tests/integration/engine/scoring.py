"""
Scoring logic that mirrors backend calculate_score() exactly.

Kept intentionally independent of the backend source — if the two ever diverge,
the test will catch the discrepancy.  Update this file when a new question type
or grading method is added to the backend.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class QuestionSpec:
    """Declarative description of one question — mirrors the DB Question model."""
    type: str           # 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'hotspot'
    grading_type: str   # 'ACCURACY' | 'COMPLETENESS'
    prompt: str
    config: dict        # e.g. {"options": ["A", "B", "C"]}
    answer_data: dict   # e.g. {"answer_points": [0, 1000, 0]}
    points_value: int = 1000
    time_limit_seconds: int = 30


@dataclass
class PlayerScript:
    """
    One player's responses for every question in a scenario.
    Each entry corresponds positionally to GameScenario.questions.
      None  →  player does not answer (late join, skip)
      dict  →  answer_data payload submitted via submit_answer
    """
    responses: list[dict | None]


@dataclass
class GameScenario:
    """Complete, self-describing game that can be executed and verified."""
    name: str
    questions: list[QuestionSpec]
    player_scripts: list[PlayerScript]
    # Optional human-readable description shown in pytest output
    description: str = ""

    # Derived fields (populated by __post_init__)
    _expected_scores: list[float] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        self._expected_scores = [
            compute_player_score(self, i) for i in range(len(self.player_scripts))
        ]

    @property
    def expected_scores(self) -> list[float]:
        return self._expected_scores

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# FITB helpers — mirror backend normalization and Levenshtein logic exactly
# ---------------------------------------------------------------------------

def _normalize_fitb(text: str) -> str:
    """Mirrors backend: lowercase + collapse all whitespace."""
    return " ".join(text.lower().split())


def _levenshtein(a: str, b: str) -> int:
    """Classic DP Levenshtein distance — mirrors rapidfuzz.distance.Levenshtein."""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[j] = prev[j - 1]
            else:
                dp[j] = 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n]


# ---------------------------------------------------------------------------
# Scoring functions — must stay in sync with backend calculate_score()
# ---------------------------------------------------------------------------

def compute_question_score(q: QuestionSpec, response: dict | None) -> float:
    """
    Return the points awarded for one player's response to one question.
    Mirrors backend game_service.calculate_score() logic exactly.
    """
    if response is None:
        return 0  # no answer → 0 points regardless of grading type

    if q.grading_type == "COMPLETENESS":
        return q.points_value  # any answer → full points

    # ACCURACY grading
    if q.type == "multiple_choice":
        selected = response.get("selectedIndex")
        if selected is None:
            return 0
        pts_list: list[int] = q.answer_data.get("answer_points", [])
        if not (0 <= selected < len(pts_list)):
            return 0
        return pts_list[selected]

    if q.type == "true_false":
        selected = response.get("selectedValue")
        if selected is None:
            return 0
        pts_map: dict = q.answer_data.get("answer_points", {})
        key = "true" if selected else "false"
        return pts_map.get(key, 0)

    if q.type == "fill_in_the_blank":
        text = _normalize_fitb(response.get("text") or "")
        if not text:
            return 0
        accepted = [_normalize_fitb(a) for a in q.answer_data.get("acceptedAnswers", [])]
        max_dist = int(q.answer_data.get("editDistance", 0))
        if any(_levenshtein(text, a) <= max_dist for a in accepted):
            return q.points_value
        return 0

    if q.type == "hotspot":
        return _hotspot_score(q, response)

    # Unknown question type — extend here when new types are added
    return 0


def _hotspot_score(q: QuestionSpec, response: dict) -> float:
    """
    Mirror of docs/plans/t7-hotspot.md §5.2–5.3, written from the spec rather than
    imported from the backend. Distance is in units of the image's longer side;
    both band boundaries are inclusive. Scenario taps must sit at least 0.005 from
    every boundary (§7.10) so float rounding cannot flip an expected band.
    """
    px, py = response.get("x"), response.get("y")
    for v in (px, py):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            return 0
    t, aspect = q.answer_data, q.config["aspectRatio"]
    if aspect >= 1:  # landscape or square
        dx, dy = px - t["x"], (py - t["y"]) / aspect
    else:  # portrait
        dx, dy = (px - t["x"]) * aspect, py - t["y"]
    d = math.sqrt(dx * dx + dy * dy)
    if d <= t["innerRadius"]:
        return q.points_value
    if d <= t["outerRadius"]:
        return q.points_value * t["partialFraction"]
    return 0


def compute_player_score(scenario: GameScenario, player_idx: int) -> float:
    """Sum of compute_question_score across all questions for one player."""
    script = scenario.player_scripts[player_idx]
    return sum(
        compute_question_score(q, r)
        for q, r in zip(scenario.questions, script.responses)
    )


def compute_expected_summary(scenario: GameScenario, player_idx: int) -> list[dict]:
    """
    Build the per-question summary we expect to see in the game_over payload.
    Mirrors the structure returned by backend get_player_question_summary().
    """
    script = scenario.player_scripts[player_idx]
    summary = []
    for q, response in zip(scenario.questions, script.responses):
        points = compute_question_score(q, response)
        reveal = _build_reveal(q)
        summary.append({
            "pointsAwarded": points,
            "playerAnswer": response,
            "answerReveal": reveal,
            "gradingType": q.grading_type,
            "type": q.type,
        })
    return summary


def _build_reveal(q: QuestionSpec) -> dict:
    """Build the answerReveal dict the backend will produce for a question."""
    if q.grading_type == "COMPLETENESS":
        return {"type": "completeness"}
    if q.type == "multiple_choice":
        pts = q.answer_data.get("answer_points", [])
        correct = [i for i, p in enumerate(pts) if p >= q.points_value]
        return {"type": "multiple_choice", "correctIndices": correct}
    if q.type == "true_false":
        pts_map = q.answer_data.get("answer_points", {})
        correct_true = pts_map.get("true", 0) >= q.points_value
        return {"type": "true_false", "correctValue": correct_true}
    if q.type == "fill_in_the_blank":
        return {
            "type": "fill_in_the_blank",
            "acceptedAnswers": q.answer_data.get("acceptedAnswers", []),
            "editDistance": q.answer_data.get("editDistance", 0),
        }
    if q.type == "hotspot":
        a = q.answer_data
        return {
            "type": "hotspot",
            "x": a["x"],
            "y": a["y"],
            "innerRadius": a["innerRadius"],
            "outerRadius": a["outerRadius"],
        }
    return {}
