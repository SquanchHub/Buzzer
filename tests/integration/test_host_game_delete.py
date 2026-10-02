# ruff: noqa: F811 — `hapi` is a pytest fixture imported from host_helpers; test
# parameters named after it are how pytest injects it, not redefinitions.
"""
T4 phase 2 — game deletion on the host path (docs/plans/t4-ui-restructuring.md D6, §6.4):

- Host game delete 409 with another host's session, and with a NULL-host session.
- Game delete 409 while a session is live (admins too).
- Game delete clears room:{code} and session:{id}:* in Redis — exercised through the host
  delete path, which runs the shared content_service.delete_game.
"""

from __future__ import annotations

from .host_helpers import hapi, redis_exists, redis_keys  # noqa: F401

NOT_YOURS = "This game has sessions you didn't host"


async def _cohost_session(hapi, course, game):
    """A co-host of the course, granted the game, completes a session of it."""
    cohost_id, cohost = hapi.host_of(course)
    hapi.grant_game(cohost_id, game)
    code, session = hapi.room(cohost, course, game)
    await hapi.play(cohost, code)
    return cohost_id, session


async def test_host_delete_409_with_another_hosts_session(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    code, _ = hapi.room(host, course, game)
    await hapi.play(host, code)  # the host's own session is fine…
    await _cohost_session(hapi, course, game)  # …someone else's is not

    r = hapi.req("DELETE", f"/host/games/{game}", host)
    assert r.status_code == 409 and r.json()["message"] == NOT_YOURS, r.text
    assert hapi.req("GET", f"/host/games/{game}", host).status_code == 200
    # An admin may delete it.
    assert hapi.req("DELETE", f"/host/games/{game}").status_code == 204


async def test_host_delete_409_with_a_null_host_session(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    cohost_id, session = await _cohost_session(hapi, course, game)
    hapi.delete_user(
        cohost_id
    )  # the session keeps its scores' game but loses its host (NULL)

    r = hapi.req("DELETE", f"/host/games/{game}", host)
    assert r.status_code == 409 and r.json()["message"] == NOT_YOURS, r.text
    assert hapi.req("GET", f"/host/games/{game}", host).status_code == 200


def test_game_delete_409_while_live(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    _, session = hapi.room(host, course, game)

    for token in (host, None):  # host, then admin (on the shared content_service path)
        r = hapi.req("DELETE", f"/host/games/{game}", token)
        assert (
            r.status_code == 409
            and r.json()["message"] == "This game has a live session"
        )

    hapi.delete_session(session, host)
    assert hapi.req("DELETE", f"/host/games/{game}", host).status_code == 204


async def test_host_game_delete_clears_redis(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    code, session = hapi.room(host, course, game)
    await hapi.play(host, code, answers=2)

    before = redis_keys(f"session:{session}:*")
    assert redis_exists(f"room:{code}") == 1 and before, before  # state exists to clear

    assert hapi.req("DELETE", f"/host/games/{game}", host).status_code == 204
    assert redis_exists(f"room:{code}") == 0
    assert redis_keys(f"session:{session}:*") == []
    # MySQL side too: the game and its session are gone.
    assert hapi.req("GET", f"/host/games/{game}", host).status_code == 404
    assert hapi.req("GET", f"/game/sessions/{session}/export", host).status_code == 404
