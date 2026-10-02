# ruff: noqa: F811 — `hapi` is a pytest fixture imported from host_helpers; test
# parameters named after it are how pytest injects it, not redefinitions.
"""
T4 phase 2 — question rules on the host path (docs/plans/t4-ui-restructuring.md §6.4):

- Question mutation 409 while the game is live (D7), allowed after the room is deleted.
- Answered-question delete 409 (D6).
- Update re-validation 422 with the VALIDATION_ERROR body; explicit null field 422 (D8);
  order_index in an update 422 (§6.2.5 a).
"""

from __future__ import annotations

from .host_helpers import MC_QUESTION, hapi  # noqa: F401

LIVE = "This game has a live session"


def _mutations(hapi, token, game, qid):
    """Every question mutation, as (name, response)."""
    return [
        (
            "create",
            hapi.req("POST", f"/host/games/{game}/questions", token, json=MC_QUESTION),
        ),
        (
            "update",
            hapi.req(
                "PUT",
                f"/host/games/{game}/questions/{qid}",
                token,
                json={"prompt": "x"},
            ),
        ),
        (
            "reorder",
            hapi.req(
                "POST",
                f"/host/games/{game}/questions/reorder",
                token,
                json={"order": [qid]},
            ),
        ),
        ("delete", hapi.req("DELETE", f"/host/games/{game}/questions/{qid}", token)),
    ]


def test_question_mutations_409_while_live_then_allowed(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    qid = hapi.req("GET", f"/host/games/{game}/questions", host).json()[0]["id"]

    _, session = hapi.room(host, course, game)  # LOBBY + Redis room key = live
    for name, r in _mutations(hapi, host, game, qid):
        assert r.status_code == 409, f"{name}: {r.status_code} {r.text}"
        assert r.json()["message"] == LIVE, name
    # Admins are held to D7 too.
    r = hapi.req("POST", f"/host/games/{game}/questions", json=MC_QUESTION)
    assert r.status_code == 409

    hapi.delete_session(session, host)  # clears MySQL row and Redis room
    results = dict(_mutations(hapi, host, game, qid))
    assert {k: r.status_code for k, r in results.items()} == {
        "create": 201,
        "update": 200,
        "reorder": 409,  # two questions now, so a one-id order is rejected — not live
        "delete": 204,
    }
    assert results["reorder"].json()["message"] != LIVE


async def test_answered_question_delete_is_409(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    answered = hapi.req("GET", f"/host/games/{game}/questions", host).json()[0]["id"]
    code, _ = hapi.room(host, course, game)
    await hapi.play(host, code, answers=1)  # COMPLETED: no longer live

    r = hapi.req("DELETE", f"/host/games/{game}/questions/{answered}", host)
    assert (
        r.status_code == 409 and r.json()["message"] == "Question has recorded answers"
    )
    # A question nobody answered can still go.
    fresh = hapi.req(
        "POST", f"/host/games/{game}/questions", host, json=MC_QUESTION
    ).json()["id"]
    assert (
        hapi.req("DELETE", f"/host/games/{game}/questions/{fresh}", host).status_code
        == 204
    )
    assert [
        q["id"] for q in hapi.req("GET", f"/host/games/{game}/questions", host).json()
    ] == [answered]


def test_update_revalidation_422_body(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    q = hapi.req("GET", f"/host/games/{game}/questions", host).json()[0]
    url = f"/host/games/{game}/questions/{q['id']}"

    # The merged question has one option: invalid as a whole (D8), not field by field.
    r = hapi.req("PUT", url, host, json={"config": {"options": ["only one"]}})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert isinstance(body["detail"], list) and body["detail"]
    err = body["detail"][0]
    assert err["loc"] == ["body"] and "at least 2 items" in err["msg"]
    assert {"loc", "msg", "type"} <= set(err)

    # A type change without matching answer_data is caught by the merge too.
    assert hapi.req("PUT", url, host, json={"type": "true_false"}).status_code == 422

    # Nothing was written.
    stored = [
        x
        for x in hapi.req("GET", f"/host/games/{game}/questions", host).json()
        if x["id"] == q["id"]
    ][0]
    assert (stored["type"], stored["config"]) == (q["type"], q["config"])


def test_update_explicit_null_and_order_index_422(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    q = hapi.req("GET", f"/host/games/{game}/questions", host).json()[0]
    url = f"/host/games/{game}/questions/{q['id']}"

    r = hapi.req("PUT", url, host, json={"prompt": None, "answer_data": None})
    assert r.status_code == 422 and r.json()["error"] == "VALIDATION_ERROR"
    assert [e["loc"] for e in r.json()["detail"]] == [
        ["body", "prompt"],
        ["body", "answer_data"],
    ]

    r = hapi.req("PUT", url, host, json={"order_index": 0})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "order_index"]
    assert "reorder" in r.json()["detail"][0]["msg"]

    stored = hapi.req("GET", f"/host/games/{game}/questions", host).json()[0]
    assert (stored["prompt"], stored["answer_data"]) == (q["prompt"], q["answer_data"])
