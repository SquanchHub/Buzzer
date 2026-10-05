"""
Read-your-writes: a write is committed before its response is sent.

`database.get_db` commits after `yield`. With FastAPI's default dependency scope
("request") that cleanup runs *after* the response has been sent, so a client on
a keep-alive connection that reads right after a write can see the old data
(T4 design §6.2.5 k measured up to 162/200 stale reads). These tests replay that
probe: many write-then-read rounds on one connection, zero stale reads allowed.

The handlers used here rely on get_db's commit alone (no commit of their own),
which is exactly the pattern the bug affected.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

_ROUNDS = 100


def _tag() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def client(docker_stack, base_url: str, admin_token: str):
    # One client = one keep-alive connection, so the next request can arrive
    # before the previous handler's cleanup has finished.
    with httpx.Client(
        base_url=f"{base_url}/api",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10.0,
    ) as c:
        yield c


@pytest.fixture()
def course_id(client: httpx.Client) -> int:
    r = client.post("/admin/courses", json={"name": f"Timing {_tag()}", "semester": "T"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def game_id(client: httpx.Client, course_id: int):
    r = client.post("/admin/games", json={"title": "timing", "course_id": course_id})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    yield gid
    client.delete(f"/admin/games/{gid}")


def test_update_is_visible_to_the_next_request(client: httpx.Client, game_id: int):
    stale = 0
    for i in range(_ROUNDS):
        r = client.put(f"/admin/games/{game_id}", json={"title": f"t{i}"})
        assert r.status_code == 200, r.text
        if client.get(f"/admin/games/{game_id}").json()["title"] != f"t{i}":
            stale += 1
    assert stale == 0, f"{stale}/{_ROUNDS} reads missed the preceding update"


def test_course_grant_is_visible_to_the_next_grant(
    client: httpx.Client, course_id: int, game_id: int
):
    """The game grant (409 without course HOST) reads what the course grant wrote."""
    refused = 0
    rounds = _ROUNDS // 5  # each round creates and deletes a user
    for _ in range(rounds):
        r = client.post(
            "/admin/users",
            json={"username": f"tm_{_tag()}", "display_name": "t", "password": "timing-pw1"},
        )
        assert r.status_code == 201, r.text
        user_id = r.json()["id"]
        r = client.post(
            f"/admin/users/{user_id}/course-access",
            json={"course_id": course_id, "role": "HOST"},
        )
        assert r.status_code == 204, r.text
        if client.post(
            f"/admin/users/{user_id}/game-access", json={"game_id": game_id}
        ).status_code == 409:
            refused += 1
        client.delete(f"/admin/users/{user_id}")
    assert refused == 0, f"{refused}/{rounds} game grants missed the course grant"


def test_delete_is_visible_to_the_next_request(client: httpx.Client, course_id: int):
    stale = 0
    for _ in range(_ROUNDS // 2):
        r = client.post("/admin/games", json={"title": "gone", "course_id": course_id})
        gid = r.json()["id"]
        r = client.delete(f"/admin/games/{gid}")
        assert r.status_code == 204, r.text
        if client.get(f"/admin/games/{gid}").status_code != 404:
            stale += 1
    assert stale == 0, f"{stale}/{_ROUNDS // 2} reads still saw a deleted game"
