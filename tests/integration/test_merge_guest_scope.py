"""
Guest merges: the host path is session-scoped, the admin path is a global identity merge.

POST /game/sessions/{id}/merge-guest used to re-attribute ALL of a guest's answers — including
rows from other hosts' sessions — after checking only that the caller hosted THIS session.
A guest is one account per email, reused on every join, so the same guest commonly has
answers in several hosts' sessions. These tests pin the fixed behaviour (backend/app/routers/
README.md gotchas) and the deliberately global admin merge.
"""

from __future__ import annotations

import asyncio
import csv
import io
import uuid

import httpx
import pytest

# Aliased so pytest doesn't try to collect the Test-prefixed class from this module.
from .engine.socket_client import TestSocketClient as SocketClient

_T = 10.0
_RESULTS_SETTLE_S = (
    0.3  # host_advance double-advance race (websocket README open finding)
)
MC = {
    "type": "multiple_choice",
    "grading_type": "ACCURACY",
    "prompt": "Pick A",
    "config": {"options": ["A", "B"]},
    "answer_data": {"answer_points": [1000, 0]},
    "time_limit_seconds": 60,
    "points_value": 1000,
}


class World:
    """Users, courses, games and sessions made through the real API; cleaned up after."""

    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url
        self.admin = admin_token
        self.tag = uuid.uuid4().hex[:6]
        self.course = self.ok(
            "POST",
            "/admin/courses",
            json={"name": f"Merge {self.tag}", "semester": "Test"},
        )["id"]
        self._games: list[int] = []
        self._users: list[str] = []

    def req(self, method, path, token=None, **kw) -> httpx.Response:
        return httpx.request(
            method,
            f"{self.base}/api{path}",
            headers={"Authorization": f"Bearer {token or self.admin}"},
            timeout=_T,
            **kw,
        )

    def ok(self, method, path, token=None, **kw):
        r = self.req(method, path, token, **kw)
        assert r.is_success, f"{method} {path} -> {r.status_code}: {r.text}"
        return r.json() if r.content else {}

    def host(self) -> str:
        """A USER who HOSTs the course and owns a one-question game in it → token."""
        name, pw = f"mh{uuid.uuid4().hex[:10]}", f"pw-{uuid.uuid4().hex}"
        uid = self.ok(
            "POST",
            "/admin/users",
            json={"username": name, "display_name": name, "password": pw},
        )["id"]
        self._users.append(uid)
        self.ok(
            "POST",
            f"/admin/users/{uid}/course-access",
            json={"course_id": self.course, "role": "HOST"},
        )
        game = self.ok(
            "POST",
            "/admin/games",
            json={"title": f"Merge game {self.tag}", "course_id": self.course},
        )["id"]
        self._games.append(game)
        self.ok("POST", f"/admin/games/{game}/questions", json=MC)
        self.ok("POST", f"/admin/users/{uid}/game-access", json={"game_id": game})
        token = self.ok("POST", "/auth/login", json={"username": name, "password": pw})[
            "access_token"
        ]
        self.games_of = getattr(self, "games_of", {})
        self.games_of[token] = game
        return token

    def room(self, host_token: str) -> tuple[str, str]:
        r = self.ok(
            "POST",
            "/game/rooms",
            host_token,
            json={"course_id": self.course, "game_id": self.games_of[host_token]},
        )
        return r["room_code"], r["session_id"]

    def guest(self, room_code: str, email: str, name: str = "Guest Student") -> str:
        """Join as a guest; the same email always maps to the same guest account."""
        return self.ok(
            "POST",
            "/auth/guest",
            json={"display_name": name, "email": email, "room_code": room_code},
        )["access_token"]

    def guest_id(self, email: str) -> str | None:
        ids = [
            g["id"]
            for g in self.ok("GET", "/admin/users/guests")
            if g["email"] == email
        ]
        return ids[0] if ids else None

    def netid_user(self) -> tuple[str, str]:
        """A real account created through the dev netid login → (netid, token)."""
        netid = f"m{uuid.uuid4().hex[:8]}"
        # Dev netid login returns a temp token (as SSO does); exchange it like the apps do.
        temp = self.ok("POST", "/auth/login", json={"netid": netid})["temp_token"]
        token = self.ok("POST", "/auth/exchange-temp", temp)["access_token"]
        # A non-guest may only join rooms of courses they belong to (authorise_player).
        uid = next(
            u["id"] for u in self.ok("GET", "/admin/users") if u["netid"] == netid
        )
        self._users.append(uid)
        self.ok(
            "POST",
            f"/admin/users/{uid}/course-access",
            json={"course_id": self.course, "role": "PLAYER"},
        )
        return netid, token

    def players(self, session_id: str, host_token: str) -> list[str]:
        """Player column of the session's score CSV (guest display name or the netid)."""
        r = self.req("GET", f"/game/sessions/{session_id}/export", host_token)
        assert r.status_code == 200, r.text
        return sorted(row[0] for row in list(csv.reader(io.StringIO(r.text)))[1:])

    def merge(
        self, host_token: str, session_id: str, guest_id: str, netid: str
    ) -> httpx.Response:
        return self.req(
            "POST",
            f"/game/sessions/{session_id}/merge-guest",
            host_token,
            json={"guest_user_id": guest_id, "target_netid": netid},
        )

    async def play(
        self, host_token: str, room_code: str, player_tokens: list[str]
    ) -> None:
        """Run the one-question game to game_over; every player answers."""
        host = SocketClient(self.base, host_token, "host")
        ps = [SocketClient(self.base, t, f"p{i}") for i, t in enumerate(player_tokens)]
        try:
            await asyncio.gather(*(c.connect() for c in [host, *ps]))
            await host.emit("join_room", {"room_code": room_code, "role": "HOST"})
            await host.wait_for("sync_state")
            for p in ps:
                await p.emit("join_room", {"room_code": room_code, "role": "PLAYER"})
                await p.wait_for("sync_state")
            await host.emit("host_advance", {})
            await host.wait_for("new_question")
            for p in ps:
                q = await p.wait_for("new_question")
                await p.emit(
                    "submit_answer",
                    {
                        "question_id": q["questionId"],
                        "answer_data": {"selectedIndex": 0},
                        "answer_time_ms": 300,
                    },
                )
                await p.wait_for("answer_received")
            await host.emit("host_advance", {})
            await host.wait_for("question_results")
            await asyncio.sleep(_RESULTS_SETTLE_S)
            await host.emit("host_advance", {})
            await host.wait_for("game_over")
        finally:
            await asyncio.gather(
                *(c.disconnect() for c in [host, *ps]), return_exceptions=True
            )

    async def completed_session(self, host_token: str, player_tokens_for) -> str:
        """Open a room, let `player_tokens_for(room_code)` join, play to the end → session id."""
        code, session = self.room(host_token)
        await self.play(host_token, code, player_tokens_for(code))
        return session

    def cleanup(self) -> None:
        for g in self._games:  # also removes the games' sessions and scores
            self.req("DELETE", f"/admin/games/{g}")
        for u in self._users:
            self.req("DELETE", f"/admin/users/{u}")


@pytest.fixture()
def world(docker_stack, base_url, admin_token):
    w = World(base_url, admin_token)
    yield w
    w.cleanup()


async def test_host_merge_moves_only_this_sessions_answers(world):
    host_a, host_b = world.host(), world.host()
    email = f"student{world.tag}@example.com"
    sa = await world.completed_session(host_a, lambda code: [world.guest(code, email)])
    sb = await world.completed_session(host_b, lambda code: [world.guest(code, email)])
    gid = world.guest_id(email)
    netid, _ = world.netid_user()

    r = world.merge(host_a, sa, gid, netid)
    assert r.status_code == 204, r.text
    assert world.players(sa, host_a) == [netid]
    # The regression: host A must not touch host B's session.
    assert world.players(sb, host_b) == ["Guest Student"]
    assert world.guest_id(email) == gid  # kept: still has answers in B's session

    # B's host merges their own session; now nothing references the guest, so it goes.
    r = world.merge(host_b, sb, gid, netid)
    assert r.status_code == 204, r.text
    assert world.players(sb, host_b) == [netid]
    assert world.guest_id(email) is None


async def test_host_cannot_merge_through_another_hosts_session(world):
    host_a, host_b = world.host(), world.host()
    email = f"student{world.tag}@example.com"
    sb = await world.completed_session(host_b, lambda code: [world.guest(code, email)])
    netid, _ = world.netid_user()
    r = world.merge(host_a, sb, world.guest_id(email), netid)
    assert r.status_code == 403
    assert world.players(sb, host_b) == ["Guest Student"]


async def test_merge_refused_until_the_session_has_finished(world):
    host = world.host()
    email = f"student{world.tag}@example.com"
    done = await world.completed_session(host, lambda code: [world.guest(code, email)])
    _, lobby = world.room(host)  # same guest exists, but this session is still LOBBY
    netid, _ = world.netid_user()
    r = world.merge(host, lobby, world.guest_id(email), netid)
    assert (
        r.status_code == 409
        and r.json()["message"]
        == "Guests can only be merged once the session has finished"
    )
    world.ok("DELETE", f"/game/sessions/{lobby}")
    assert world.players(done, host) == ["Guest Student"]


async def test_merge_refused_when_target_already_answered_in_session(world):
    host = world.host()
    email = f"student{world.tag}@example.com"
    netid, real_token = world.netid_user()
    # The student played this session twice: once as a guest, once signed in.
    session = await world.completed_session(
        host, lambda code: [world.guest(code, email), real_token]
    )
    r = world.merge(host, session, world.guest_id(email), netid)
    assert (
        r.status_code == 409
        and "already has answers in this session" in r.json()["message"]
    )
    assert world.players(session, host) == sorted(
        ["Guest Student", netid]
    )  # nothing moved


async def test_merge_404_when_guest_has_no_answers_in_session(world):
    host_a, host_b = world.host(), world.host()
    email = f"student{world.tag}@example.com"
    sa = await world.completed_session(
        host_a,
        lambda code: [
            world.guest(code, f"other{world.tag}@example.com", "Someone Else")
        ],
    )
    await world.completed_session(host_b, lambda code: [world.guest(code, email)])
    gid = world.guest_id(email)
    netid, _ = world.netid_user()
    # Host A names a guest who never played A's session: nothing to move, and the guest
    # (who has answers in B's session) must not be deleted through A's session.
    r = world.merge(host_a, sa, gid, netid)
    assert r.status_code == 404
    assert world.guest_id(email) == gid


async def test_target_netid_is_normalised(world):
    host = world.host()
    email = f"student{world.tag}@example.com"
    session = await world.completed_session(
        host, lambda code: [world.guest(code, email)]
    )
    netid, _ = world.netid_user()
    r = world.merge(host, session, world.guest_id(email), f"  {netid.upper()}  ")
    assert r.status_code == 204, r.text
    assert world.players(session, host) == [netid]


async def test_admin_merge_stays_global(world):
    """Pinned on purpose: an admin merge is an identity merge across every session."""
    host_a, host_b = world.host(), world.host()
    email = f"student{world.tag}@example.com"
    sa = await world.completed_session(host_a, lambda code: [world.guest(code, email)])
    sb = await world.completed_session(host_b, lambda code: [world.guest(code, email)])
    netid, _ = world.netid_user()
    r = world.req(
        "POST",
        "/admin/users/merge-guest",
        json={"guest_user_id": world.guest_id(email), "target_netid": netid},
    )
    assert r.status_code == 204, r.text
    await asyncio.sleep(0.3)  # admin.merge_guest commits via get_db, after the response
    assert world.players(sa, host_a) == [netid]
    assert world.players(sb, host_b) == [netid]
    assert world.guest_id(email) is None
