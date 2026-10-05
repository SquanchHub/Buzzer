"""
T4 phase 3 — the admin API on content_service, plus course membership for the admin app.

docs/plans/t4-ui-restructuring.md §6.5 and the phase-3 rows of §6.4. The /api/admin game and
question routes keep their URLs and their require_admin gate, but now run the same
content_service code as /api/host, so admins get D6–D8:

- game delete is 409 while live and clears the deleted sessions' Redis state (D6, D7);
- question create/update/delete/reorder are 409 while live (D7);
- a question update is re-validated as a whole; explicit nulls and order_index are 422 (D8,
  §6.2.5 a); an answered question can't be deleted (D6);
- import errors use the VALIDATION_ERROR body (§6.2.5 b).

Unlike a host, an admin may delete a game whose sessions other hosts ran (D6) and is never
auto-granted the games they create (D1).
"""

from __future__ import annotations

import json

from .host_helpers import MC_QUESTION, hapi, redis_exists, redis_keys  # noqa: F401


def _admin_game(hapi, course_id: int, questions: int = 1) -> int:  # noqa: F811
    gid = hapi.ok(
        "POST",
        "/admin/games",
        json={"title": f"Admin game {hapi.tag}", "course_id": course_id},
    )["id"]
    hapi.track_game(gid)
    for _ in range(questions):
        hapi.ok("POST", f"/admin/games/{gid}/questions", json=MC_QUESTION)
    return gid


def _questions(hapi, game_id: int) -> list[dict]:  # noqa: F811
    return hapi.ok("GET", f"/admin/games/{game_id}/questions")


def _admin_id(hapi) -> str:  # noqa: F811
    return next(u["id"] for u in hapi.ok("GET", "/admin/users") if u["role"] == "ADMIN")


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


def test_admin_game_delete_409_while_live_then_allowed(hapi):  # noqa: F811
    course = hapi.course()
    game = _admin_game(hapi, course)
    _, session = hapi.room(hapi.admin, course, game)

    r = hapi.req("DELETE", f"/admin/games/{game}")
    assert (
        r.status_code == 409 and r.json()["message"] == "This game has a live session"
    )
    assert hapi.req("GET", f"/admin/games/{game}").status_code == 200

    hapi.delete_session(session)  # the documented escape hatch (D6)
    assert hapi.req("DELETE", f"/admin/games/{game}").status_code == 204
    assert hapi.req("GET", f"/admin/games/{game}").status_code == 404


async def test_admin_game_delete_clears_redis(hapi):  # noqa: F811
    course = hapi.course()
    game = _admin_game(hapi, course)
    code, session = hapi.room(hapi.admin, course, game)
    await hapi.play(hapi.admin, code, answers=2)  # COMPLETED: no longer live

    before = redis_keys(f"session:{session}:*")
    assert redis_exists(f"room:{code}") == 1 and before, before

    assert hapi.req("DELETE", f"/admin/games/{game}").status_code == 204
    assert redis_exists(f"room:{code}") == 0
    assert redis_keys(f"session:{session}:*") == []
    assert hapi.req("GET", f"/game/sessions/{session}/export").status_code == 404


async def test_admin_deletes_game_with_other_hosts_sessions(hapi):  # noqa: F811
    """The host-only 'sessions you didn't host' 409 doesn't apply to admins (D6)."""
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    code, _ = hapi.room(host, course, game)
    await hapi.play(host, code)
    cohost_id, cohost = hapi.host_of(course)
    hapi.grant_game(cohost_id, game)
    r = hapi.req("DELETE", f"/host/games/{game}", cohost)
    assert r.status_code == 409  # a host can't delete another host's session history

    assert hapi.req("DELETE", f"/admin/games/{game}").status_code == 204
    assert hapi.req("GET", f"/admin/games/{game}").status_code == 404


def test_admin_create_and_import_do_not_auto_grant(hapi):  # noqa: F811
    course = hapi.course()
    game = _admin_game(hapi, course, questions=0)
    bundle = hapi.ok("GET", f"/admin/games/{game}/export")
    r = hapi.req(
        "POST",
        "/admin/games/import",
        files={"file": ("g.json", json.dumps(bundle), "application/json")},
        data={"course_id": str(course)},
    )
    assert r.status_code == 201, r.text
    imported = hapi.track_game(r.json()["game_id"])

    granted = hapi.ok("GET", f"/admin/users/{_admin_id(hapi)}")["game_access"]
    assert game not in granted and imported not in granted


def test_admin_import_errors_use_validation_error_body(hapi):  # noqa: F811
    course = hapi.course()
    cases = [
        (b"{not json", "Invalid JSON"),
        (json.dumps({"format": "nope"}).encode(), "Unrecognised file format"),
        (
            json.dumps({"format": "buzzer/game", "version": 99}).encode(),
            "Unsupported version 99",
        ),
        (
            json.dumps(
                {
                    "format": "buzzer/game",
                    "version": 1,
                    "game": {"title": "x"},
                    "questions": [{"type": "multiple_choice"}],
                }
            ).encode(),
            "Question 1 invalid",
        ),
    ]
    for raw, message in cases:
        r = hapi.req(
            "POST",
            "/admin/games/import",
            files={"file": ("g.json", raw, "application/json")},
            data={"course_id": str(course)},
        )
        assert r.status_code == 422, (message, r.text)
        body = r.json()
        assert body["error"] == "VALIDATION_ERROR", body
        assert body["detail"][0]["loc"] == ["body", "file"]
        assert message in body["detail"][0]["msg"], body


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def test_admin_question_update_revalidation_422(hapi):  # noqa: F811
    game = _admin_game(hapi, hapi.course())
    q = _questions(hapi, game)[0]
    url = f"/admin/games/{game}/questions/{q['id']}"

    # Each field is fine alone; the merged question has one option (D8).
    r = hapi.req("PUT", url, json={"config": {"options": ["only one"]}})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert "at least 2 items" in body["detail"][0]["msg"]
    # Option count no longer matches answer_points.
    r = hapi.req("PUT", url, json={"config": {"options": ["A", "B", "C"]}})
    assert r.status_code == 422

    stored = _questions(hapi, game)[0]
    assert stored["config"] == q["config"]

    # A consistent patch still works and is sanitized.
    r = hapi.req(
        "PUT",
        url,
        json={
            "prompt": "<script>x</script><b>Pick C</b>",
            "config": {"options": ["A", "B", "C"]},
            "answer_data": {"answer_points": [0, 0, 1000]},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["prompt"] == "x<b>Pick C</b>"


def test_admin_question_update_null_and_order_index_422(hapi):  # noqa: F811
    game = _admin_game(hapi, hapi.course(), questions=2)
    q = _questions(hapi, game)[0]
    url = f"/admin/games/{game}/questions/{q['id']}"

    r = hapi.req("PUT", url, json={"prompt": None})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "prompt"]

    r = hapi.req("PUT", url, json={"order_index": 1})
    assert r.status_code == 422
    assert "reorder" in r.json()["detail"][0]["msg"]
    assert [x["id"] for x in _questions(hapi, game)][0] == q["id"]


def test_admin_question_create_appends_ignoring_order_index(hapi):  # noqa: F811
    game = _admin_game(hapi, hapi.course(), questions=2)
    r = hapi.req(
        "POST", f"/admin/games/{game}/questions", json={**MC_QUESTION, "order_index": 0}
    )
    assert r.status_code == 201, r.text
    assert r.json()["order_index"] == 2
    assert [x["order_index"] for x in _questions(hapi, game)] == [0, 1, 2]


def test_admin_question_mutations_409_while_live_then_allowed(hapi):  # noqa: F811
    course = hapi.course()
    game = _admin_game(hapi, course, questions=2)
    first, second = (x["id"] for x in _questions(hapi, game))
    _, session = hapi.room(hapi.admin, course, game)
    base = f"/admin/games/{game}/questions"

    for method, path, kw in [
        ("POST", base, {"json": MC_QUESTION}),
        ("PUT", f"{base}/{first}", {"json": {"prompt": "edited"}}),
        ("DELETE", f"{base}/{second}", {}),
        ("POST", f"{base}/reorder", {"json": {"order": [second, first]}}),
    ]:
        r = hapi.req(method, path, **kw)
        assert r.status_code == 409, (method, path, r.text)
        assert r.json()["message"] == "This game has a live session"
    assert [x["id"] for x in _questions(hapi, game)] == [first, second]

    hapi.delete_session(session)
    assert hapi.req(
        "POST", f"{base}/reorder", json={"order": [second, first]}
    ).is_success
    assert hapi.req("PUT", f"{base}/{first}", json={"prompt": "edited"}).is_success
    assert [x["id"] for x in _questions(hapi, game)] == [second, first]


async def test_admin_answered_question_delete_409(hapi):  # noqa: F811
    course = hapi.course()
    game = _admin_game(hapi, course)
    answered = _questions(hapi, game)[0]["id"]
    code, _ = hapi.room(hapi.admin, course, game)
    await hapi.play(hapi.admin, code)
    spare = hapi.ok("POST", f"/admin/games/{game}/questions", json=MC_QUESTION)["id"]

    r = hapi.req("DELETE", f"/admin/games/{game}/questions/{answered}")
    assert r.status_code == 409  # was a 500 before content_service
    assert r.json()["message"] == "Question has recorded answers"

    assert (
        hapi.req("DELETE", f"/admin/games/{game}/questions/{spare}").status_code == 204
    )
    assert [x["id"] for x in _questions(hapi, game)] == [answered]


def test_admin_question_routes_404_for_unknown_ids(hapi):  # noqa: F811
    game = _admin_game(hapi, hapi.course())
    other = _admin_game(hapi, hapi.course())
    foreign = _questions(hapi, other)[0]["id"]
    assert hapi.req("GET", "/admin/games/99999999/questions").status_code == 404
    assert (
        hapi.req(
            "PUT", f"/admin/games/{game}/questions/{foreign}", json={"prompt": "x"}
        ).status_code
        == 404
    )
    assert (
        hapi.req("DELETE", f"/admin/games/{game}/questions/{foreign}").status_code
        == 404
    )
    assert hapi.req("DELETE", "/admin/games/99999999").status_code == 404


# ---------------------------------------------------------------------------
# Course membership (GET /admin/courses/{id}/access)
# ---------------------------------------------------------------------------


def test_course_access_lists_members_with_roles(hapi):  # noqa: F811
    course, other = hapi.course(), hapi.course()
    host_id, _ = hapi.host_of(course)
    player_id, _ = hapi.user()
    hapi.grant_course(player_id, course, role="PLAYER")
    outsider_id, _ = hapi.user()
    hapi.grant_course(outsider_id, other)

    r = hapi.req("GET", f"/admin/courses/{course}/access")
    assert r.status_code == 200, r.text
    members = {m["user_id"]: m for m in r.json()}
    assert set(members) == {host_id, player_id}
    assert members[host_id]["role"] == "HOST"
    assert members[player_id]["role"] == "PLAYER"
    assert {"user_id", "username", "display_name", "netid", "role"} <= set(
        members[host_id]
    )
    # HOSTs first.
    assert [m["role"] for m in r.json()] == ["HOST", "PLAYER"]

    # A role change and a revoke show up straight away.
    hapi.grant_course(player_id, course, role="HOST")
    hapi.ok("DELETE", f"/admin/users/{host_id}/course-access/{course}")
    r = hapi.req("GET", f"/admin/courses/{course}/access")
    assert [(m["user_id"], m["role"]) for m in r.json()] == [(player_id, "HOST")]


def test_course_access_empty_404_and_403(hapi):  # noqa: F811
    course = hapi.course()
    assert hapi.ok("GET", f"/admin/courses/{course}/access") == []
    assert hapi.req("GET", "/admin/courses/99999999/access").status_code == 404
    _, host = hapi.host_of(course)
    assert hapi.req("GET", f"/admin/courses/{course}/access", host).status_code == 403
