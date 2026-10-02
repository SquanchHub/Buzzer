"""
Shared helpers for the T4 phase-2 host tests (docs/plans/t4-ui-restructuring.md §6.4,
§6.2.5 g). Import the `hapi` fixture into a test module:

    from .host_helpers import hapi  # noqa: F401

`hapi` creates users, courses, games and sessions through the real API and removes what it
can on teardown (sessions — which also clears their Redis state —, games, users). Courses
have no delete endpoint and stay behind as inert rows, as in the other integration tests.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid

import httpx
import pytest

from .conftest import _REPO_ROOT

# Aliased so pytest doesn't try to collect the Test-prefixed class from test modules.
from .engine.socket_client import TestSocketClient as SocketClient

_TIMEOUT = 10.0
# Pause after question_results before the next host_advance: host_advance emits results
# before it writes question_phase = "RESULTS", so an immediate second advance can be
# processed as another QUESTION -> RESULTS (open finding, backend/app/websocket/README.md).
_RESULTS_SETTLE_S = 0.3

MC_QUESTION = {
    "type": "multiple_choice",
    "grading_type": "ACCURACY",
    "prompt": "Pick A",
    "config": {"options": ["A", "B"]},
    "answer_data": {"answer_points": [1000, 0]},
    "time_limit_seconds": 60,
    "points_value": 1000,
}


def redis_exists(*keys: str) -> int:
    """How many of `keys` exist in the stack's Redis (it isn't exposed to the host)."""
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "redis", "redis-cli", "EXISTS", *keys],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout.strip())


class HostApi:
    def __init__(self, base_url: str, admin_token: str):
        self.base = base_url
        self.admin = admin_token
        self.tag = uuid.uuid4().hex[:6]
        self._users: list[str] = []
        self._games: list[int] = []
        self._sessions: list[str] = []

    # ── HTTP ────────────────────────────────────────────────────────────────
    def req(
        self, method: str, path: str, token: str | None = None, **kw
    ) -> httpx.Response:
        """`path` is relative to /api. Defaults to the admin token."""
        headers = {"Authorization": f"Bearer {token or self.admin}"}
        return httpx.request(
            method, f"{self.base}/api{path}", headers=headers, timeout=_TIMEOUT, **kw
        )

    def ok(self, method: str, path: str, token: str | None = None, **kw):
        r = self.req(method, path, token, **kw)
        assert r.is_success, f"{method} {path} -> {r.status_code}: {r.text}"
        return (
            r.json() if r.content and "json" in r.headers.get("content-type", "") else r
        )

    # ── world building (admin API) ──────────────────────────────────────────
    def course(self) -> int:
        return self.ok(
            "POST",
            "/admin/courses",
            json={
                "name": f"Host test {self.tag} {uuid.uuid4().hex[:4]}",
                "semester": "Test",
            },
        )["id"]

    def user(self) -> tuple[str, str]:
        """A USER account → (user_id, access token)."""
        name, pw = f"ht{uuid.uuid4().hex[:10]}", f"pw-{uuid.uuid4().hex}"
        uid = self.ok(
            "POST",
            "/admin/users",
            json={"username": name, "display_name": name, "password": pw},
        )["id"]
        self._users.append(uid)
        token = self.ok(
            "POST", "/auth/login", token="", json={"username": name, "password": pw}
        )["access_token"]
        return uid, token

    def host_of(self, course_id: int) -> tuple[str, str]:
        """A USER with HOST on `course_id`."""
        uid, token = self.user()
        self.grant_course(uid, course_id)
        return uid, token

    def grant_course(self, user_id: str, course_id: int, role: str = "HOST") -> None:
        self.ok(
            "POST",
            f"/admin/users/{user_id}/course-access",
            json={"course_id": course_id, "role": role},
        )

    def grant_game(self, user_id: str, game_id: int) -> None:
        self.ok(
            "POST", f"/admin/users/{user_id}/game-access", json={"game_id": game_id}
        )

    def delete_user(self, user_id: str) -> None:
        self.ok("DELETE", f"/admin/users/{user_id}")
        self._users.remove(user_id)

    def guest(self, room_code: str) -> str:
        return self.ok(
            "POST",
            "/auth/guest",
            token="",
            json={
                "display_name": "Guest",
                "email": f"g{uuid.uuid4().hex[:10]}@example.com",
                "room_code": room_code,
            },
        )["access_token"]

    # ── host API ────────────────────────────────────────────────────────────
    def host_game(self, token: str, course_id: int, questions: int = 1) -> int:
        """Create a game through POST /host/games (auto-granted to a non-admin) with
        `questions` multiple-choice questions."""
        gid = self.ok(
            "POST",
            "/host/games",
            token,
            json={"title": f"Host game {self.tag}", "course_id": course_id},
        )["id"]
        self._games.append(gid)
        for _ in range(questions):
            self.ok("POST", f"/host/games/{gid}/questions", token, json=MC_QUESTION)
        return gid

    def track_game(self, game_id: int) -> int:
        self._games.append(game_id)
        return game_id

    def room(self, token: str, course_id: int, game_id: int) -> tuple[str, str]:
        """Open a room (a LOBBY session, live while its Redis key exists) → (code, session_id)."""
        r = self.ok(
            "POST",
            "/game/rooms",
            token,
            json={"course_id": course_id, "game_id": game_id},
        )
        self._sessions.append(r["session_id"])
        return r["room_code"], r["session_id"]

    def delete_session(self, session_id: str, token: str | None = None) -> None:
        self.ok("DELETE", f"/game/sessions/{session_id}", token)
        self._sessions.remove(session_id)

    async def play(self, host_token: str, room_code: str, answers: int = 1) -> None:
        """Run a room's game to game_over: `answers` guests each answer every question
        with option 0 (correct)."""
        host = SocketClient(self.base, host_token, "host")
        players = [
            SocketClient(self.base, self.guest(room_code), f"p{i}")
            for i in range(answers)
        ]
        try:
            await asyncio.gather(*(c.connect() for c in [host, *players]))
            await host.emit("join_room", {"room_code": room_code, "role": "HOST"})
            await host.wait_for("sync_state")
            for p in players:
                await p.emit("join_room", {"room_code": room_code, "role": "PLAYER"})
                await p.wait_for("sync_state")
            await host.emit("host_advance", {})
            while True:
                event = await _first(host, "new_question", "game_over")
                if event[0] == "game_over":
                    break
                qid = event[1]["questionId"]
                for p in players:
                    await p.wait_for("new_question")
                    await p.emit(
                        "submit_answer",
                        {
                            "question_id": qid,
                            "answer_data": {"selectedIndex": 0},
                            "answer_time_ms": 300,
                        },
                    )
                    await p.wait_for("answer_received")
                await host.emit("host_advance", {})
                await host.wait_for("question_results")
                await asyncio.sleep(_RESULTS_SETTLE_S)
                await host.emit("host_advance", {})
        finally:
            await asyncio.gather(
                *(c.disconnect() for c in [host, *players]), return_exceptions=True
            )

    # ── teardown ────────────────────────────────────────────────────────────
    def cleanup(self) -> None:
        for sid in self._sessions:
            self.req("DELETE", f"/game/sessions/{sid}")  # also clears Redis
        for gid in self._games:
            self.req("DELETE", f"/admin/games/{gid}")
        for uid in self._users:
            self.req("DELETE", f"/admin/users/{uid}")


async def _first(client: SocketClient, *events: str) -> tuple[str, dict]:
    """Wait for whichever of `events` arrives first."""
    tasks = {asyncio.ensure_future(client.wait_for(e, _TIMEOUT)): e for e in events}
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    task = done.pop()
    return tasks[task], task.result()


@pytest.fixture()
def hapi(docker_stack, base_url: str, admin_token: str):
    api = HostApi(base_url, admin_token)
    yield api
    api.cleanup()
