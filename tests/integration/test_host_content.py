# ruff: noqa: F811 — `hapi` is a pytest fixture imported from host_helpers; test
# parameters named after it are how pytest injects it, not redefinitions.
"""
T4 phase 2 — host content management (docs/plans/t4-ui-restructuring.md §6.4 phase-2 rows):

- Host CRUD on an own-course game (game + questions + export/import), through /api/host.
- Auto-grant on host create and host import (D1): the new game is the creator's to run.
- Host create/import with an unknown course_id → 403, not 404 (assert_host_can_use_course
  runs before content_service's 404; a non-admin is not HOST of a nonexistent course).
- Path-based course endpoints (/host/courses/{id}/…) → 404 for a nonexistent course, for a
  host and for an admin.
"""

from __future__ import annotations

import json

import pytest

from .conftest import _REPO_ROOT
from .host_helpers import MC_QUESTION, hapi  # noqa: F401

_SAMPLE = _REPO_ROOT / "sample_games" / "cs_first_day.json"


def test_host_crud_on_own_course_game(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)

    # Create, read, update the game.
    r = hapi.req(
        "POST", "/host/games", host, json={"title": "Quiz", "course_id": course}
    )
    assert r.status_code == 201, r.text
    game = hapi.track_game(r.json()["id"])
    assert r.json()["course_id"] == course
    r = hapi.req(
        "PUT", f"/host/games/{game}", host, json={"title": "Quiz 2", "max_players": 40}
    )
    assert (
        r.status_code == 200
        and r.json()["title"] == "Quiz 2"
        and r.json()["max_players"] == 40
    )
    assert hapi.req("GET", f"/host/games/{game}", host).json()["title"] == "Quiz 2"
    # Hosts can't move a game between courses (D5): course_id isn't in HostGameUpdate.
    r = hapi.req("PUT", f"/host/games/{game}", host, json={"course_id": hapi.course()})
    assert r.status_code == 422 and r.json()["error"] == "VALIDATION_ERROR"

    # Questions: create (appended), update, reorder, delete.
    q1 = hapi.req("POST", f"/host/games/{game}/questions", host, json=MC_QUESTION)
    q2 = hapi.req(
        "POST",
        f"/host/games/{game}/questions",
        host,
        json={**MC_QUESTION, "prompt": "<b>Two</b><script>x</script>"},
    )
    assert (q1.status_code, q2.status_code) == (201, 201)
    q1, q2 = q1.json(), q2.json()
    assert (q1["order_index"], q2["order_index"]) == (0, 1)
    assert q2["prompt"] == "<b>Two</b>x"  # sanitized
    r = hapi.req(
        "PUT",
        f"/host/games/{game}/questions/{q1['id']}",
        host,
        json={"prompt": "Edited"},
    )
    assert r.status_code == 200 and r.json()["prompt"] == "Edited"
    r = hapi.req(
        "POST",
        f"/host/games/{game}/questions/reorder",
        host,
        json={"order": [q2["id"], q1["id"]]},
    )
    assert r.status_code == 204
    listed = hapi.req("GET", f"/host/games/{game}/questions", host).json()
    assert [q["id"] for q in listed] == [q2["id"], q1["id"]]
    assert (
        hapi.req("DELETE", f"/host/games/{game}/questions/{q2['id']}", host).status_code
        == 204
    )
    assert [
        q["id"] for q in hapi.req("GET", f"/host/games/{game}/questions", host).json()
    ] == [q1["id"]]

    # Export (attachment, never course_id) and import the bundle back into the course.
    r = hapi.req("GET", f"/host/games/{game}/export", host)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    bundle = r.json()
    assert "course_id" not in json.dumps(bundle)
    r = hapi.req(
        "POST",
        "/host/games/import",
        host,
        files={"file": ("q.json", r.content)},
        data={"course_id": str(course)},
    )
    assert r.status_code == 201, r.text
    copy = hapi.track_game(r.json()["game_id"])
    assert [
        q["prompt"]
        for q in hapi.req("GET", f"/host/games/{copy}/questions", host).json()
    ] == ["Edited"]

    # The course list shows both, with session counts; delete the original.
    items = {
        g["id"]: g
        for g in hapi.req("GET", f"/host/courses/{course}/games", host).json()
    }
    assert set(items) == {game, copy} and items[game]["session_count"] == 0
    assert hapi.req("DELETE", f"/host/games/{game}", host).status_code == 204
    assert hapi.req("GET", f"/host/games/{game}", host).status_code == 404


def test_auto_grant_on_host_create_and_import(hapi):
    course = hapi.course()
    host_id, host = hapi.host_of(course)
    created = hapi.req(
        "POST", "/host/games", host, json={"title": "Mine", "course_id": course}
    )
    imported = hapi.req(
        "POST",
        "/host/games/import",
        host,
        files={"file": ("g.json", _SAMPLE.read_bytes())},
        data={"course_id": str(course)},
    )
    assert (created.status_code, imported.status_code) == (201, 201), (
        created.text,
        imported.text,
    )
    ids = {
        hapi.track_game(created.json()["id"]),
        hapi.track_game(imported.json()["game_id"]),
    }

    # Granted: listed in my-games and the course list, and runnable (a room opens).
    assert ids <= {g["id"] for g in hapi.req("GET", "/game/my-games", host).json()}
    assert ids <= {
        g["id"] for g in hapi.req("GET", f"/host/courses/{course}/games", host).json()
    }
    detail = hapi.ok("GET", f"/admin/users/{host_id}")
    assert ids <= set(detail["game_access"])
    for gid in ids:
        hapi.room(host, course, gid)

    # Another HOST of the same course doesn't get the creator's games (D1: grant needed).
    _, cohost = hapi.host_of(course)
    assert not ids & {
        g["id"] for g in hapi.req("GET", f"/host/courses/{course}/games", cohost).json()
    }
    assert (
        hapi.req("GET", f"/host/games/{created.json()['id']}", cohost).status_code
        == 403
    )


def test_admin_create_gets_no_grant(hapi):
    course = hapi.course()
    r = hapi.req("POST", "/host/games", json={"title": "Admin's", "course_id": course})
    assert r.status_code == 201
    gid = hapi.track_game(r.json()["id"])
    _, host = hapi.host_of(course)
    assert gid not in {
        g["id"] for g in hapi.req("GET", f"/host/courses/{course}/games", host).json()
    }


def test_unknown_course_on_create_and_import_is_403_for_a_host(hapi):
    _, host = hapi.host_of(hapi.course())
    r = hapi.req(
        "POST", "/host/games", host, json={"title": "x", "course_id": 999999999}
    )
    assert r.status_code == 403, r.text
    r = hapi.req(
        "POST",
        "/host/games/import",
        host,
        files={"file": ("g.json", _SAMPLE.read_bytes())},
        data={"course_id": "999999999"},
    )
    assert r.status_code == 403, r.text
    # An admin passes the course check and gets content_service's 404.
    assert (
        hapi.req(
            "POST", "/host/games", json={"title": "x", "course_id": 999999999}
        ).status_code
        == 404
    )


def test_host_of_another_course_is_403(hapi):
    course, other = hapi.course(), hapi.course()
    _, host = hapi.host_of(course)
    assert (
        hapi.req(
            "POST", "/host/games", host, json={"title": "x", "course_id": other}
        ).status_code
        == 403
    )
    assert hapi.req("GET", f"/host/courses/{other}/games", host).status_code == 403
    _, other_host = hapi.host_of(other)
    game = hapi.host_game(other_host, other)
    assert hapi.req("GET", f"/host/games/{game}", host).status_code == 403
    assert (
        hapi.req(
            "POST", f"/host/games/{game}/questions", host, json=MC_QUESTION
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/host/courses/{c}/roster", None),
        ("POST", "/host/courses/{c}/roster/import", {"rows": []}),
        ("PATCH", "/host/courses/{c}/roster/1", {"is_active": False}),
        ("GET", "/host/courses/{c}/games", None),
    ],
    ids=["roster", "roster import", "roster patch", "games"],
)
def test_path_course_endpoints_404_for_nonexistent_course(hapi, method, path, body):
    _, host = hapi.host_of(hapi.course())
    url = path.format(c=999999999)
    kw = {"json": body} if body is not None else {}
    assert hapi.req(method, url, host, **kw).status_code == 404  # host
    assert hapi.req(method, url, **kw).status_code == 404  # admin
