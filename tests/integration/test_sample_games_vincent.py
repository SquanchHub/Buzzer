"""
T6 — Vincent's sample games (docs/plans/t6-sample-games-vincent.md §5).

1. Each file meets the T6 requirements on its own: every question type including the team's
   new T7 types, both grading modes, a version 2 bundle whose hotspot images resolve.
2. Each imports cleanly through the host and admin routes.
3. Each plays correctly after import: every hotspot tapped at its target and every ACCURACY
   ordering question answered in its correct order scores full points, so keys, shuffles and
   image coordinates survived the round trip.
"""

from __future__ import annotations

import json

import pytest

from .conftest import _REPO_ROOT
from .host_helpers import hapi  # noqa: F401 — fixture
from .test_ordering import OrderingGame

_DIR = _REPO_ROOT / "sample_games"
GAMES = {
    "reading_the_data_stats.json": "classroom",
    "food_fight_party.json": "party",
}
ALL_TYPES = {
    "multiple_choice",
    "true_false",
    "fill_in_the_blank",
    "multi_select",
    "hotspot",
    "ordering",
}


def _bundle(name: str) -> dict:
    return json.loads((_DIR / name).read_text())


@pytest.mark.parametrize("name", GAMES)
def test_file_meets_t6_requirements(name):
    b = _bundle(name)
    assert b["format"] == "buzzer/game"
    assert b["version"] == 2  # hotspot images need version 2 (T8 D7)
    qs = b["questions"]
    assert {q["type"] for q in qs} >= ALL_TYPES
    assert {q["grading_type"] for q in qs} == {"ACCURACY", "COMPLETENESS"}
    refs = {img["ref"] for img in b["images"]}
    for q in qs:
        if q["type"] == "hotspot":
            assert q["config"]["imageRef"] in refs
    assert "imageId" not in json.dumps(b)  # never an instance-specific id
    # Distinct from every other sample game (T6: new, distinctly named files).
    others = [p for p in _DIR.glob("*.json") if p.name != name]
    titles = {json.loads(p.read_text())["game"]["title"] for p in others}
    assert b["game"]["title"] not in titles


def test_one_classroom_and_one_party_game():
    assert sorted(GAMES.values()) == ["classroom", "party"]


def _import(hapi, route: str, name: str):  # noqa: F811
    course = hapi.course()
    token = hapi.admin
    if route == "host":
        _, token = hapi.host_of(course)
    r = hapi.req(
        "POST",
        f"/{route}/games/import",
        token,
        files={"file": (name, (_DIR / name).read_bytes(), "application/json")},
        data={"course_id": str(course)},
    )
    assert r.status_code == 201, r.text
    game = hapi.track_game(r.json()["game_id"])
    questions = hapi.ok("GET", f"/admin/games/{game}/questions")
    for q in questions:
        if q["type"] == "hotspot":
            image = q["config"]["imageId"]
            if image not in hapi._images:
                hapi._images.append(image)  # deleted on teardown, after the game
    return course, game, questions


@pytest.mark.parametrize("route", ["host", "admin"])
@pytest.mark.parametrize("name", GAMES)
def test_file_imports_cleanly(hapi, route, name):  # noqa: F811
    course, _, questions = _import(hapi, route, name)
    b = _bundle(name)
    assert len(questions) == len(b["questions"])
    assert [q["type"] for q in questions] == [q["type"] for q in b["questions"]]
    images = {i["id"] for i in hapi.ok("GET", f"/images?course_id={course}")["items"]}
    for q in questions:
        if q["type"] == "hotspot":
            assert q["config"]["imageId"] in images


@pytest.mark.parametrize("name", GAMES)
async def test_new_type_questions_score_full_points(hapi, name):  # noqa: F811
    course, game, questions = _import(hapi, "admin", name)
    setup = {"course_id": course, "game_id": game}
    checked = 0
    async with OrderingGame(hapi.base, hapi.admin, setup, 1) as g:
        for q in questions:
            await g.next_question()
            a = q["answer_data"]
            answer = None
            if q["grading_type"] == "ACCURACY" and q["type"] == "hotspot":
                answer = {"x": a["x"], "y": a["y"]}
            elif q["grading_type"] == "ACCURACY" and q["type"] == "ordering":
                answer = {"order": a["correctOrder"]}
            if answer is not None:
                ack = await g.submit(0, q["id"], answer)
                assert (ack["pointsAwarded"], ack["isCorrect"]) == (
                    q["points_value"],
                    True,
                ), q["prompt"]
                checked += 1
            await g.results()
        await g.finish()
    assert checked >= 3  # both hotspots and at least one ACCURACY ordering question
