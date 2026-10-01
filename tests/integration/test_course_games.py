"""
T4 phase 1 — games belong to one course.

Behaviour under test (docs/plans/t4-ui-restructuring.md §6.1, §6.4 phase 1):

- Every game is created/imported into a course; `course_id` is returned.
- A non-admin host can use a game only with BOTH a `user_game_access` grant
  AND the HOST role on the game's course (D1). Revoking course HOST therefore
  revokes game access with no other cleanup.
- `create_room` requires the room's course to equal the game's course, and
  refuses unassigned games — for admins too (D4).
- An admin can only grant game access to a user who hosts the game's course.
- An admin can move a game to another course, except while it has a live
  session (MySQL LOBBY/IN_PROGRESS *and* a `room:{code}` key in Redis, D7).

Unassigned (course_id NULL) games can no longer be created through the API;
they exist only as legacy rows left by migration 004. Tests that need one write
it straight to MySQL (`legacy_game`).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import uuid
from typing import Iterator

import httpx
import pytest

from .conftest import _REPO_ROOT

_SAMPLE_GAMES = sorted((_REPO_ROOT / "sample_games").glob("*.json"))
_TIMEOUT = 10.0


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = _REPO_ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _compose(*args: str, stdin: str | None = None) -> str:
    """Run a command in a stack container (MySQL/Redis are not reachable otherwise)."""
    r = subprocess.run(
        ["docker", "compose", "exec", "-T", *args],
        cwd=_REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout


def _mysql(sql: str) -> str:
    password = _env().get("MYSQL_PASSWORD", "")
    return _compose(
        "mysql", "mysql", "-N", "-uapp_user", f"-p{password}", "buzzer", stdin=sql
    )


def _redis(*args: str) -> str:
    return _compose("redis", "redis-cli", *args).strip()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class Api:
    """Thin admin-token HTTP client for the live stack."""

    def __init__(self, base_url: str, admin_token: str):
        self.base = f"{base_url}/api"
        self.admin = admin_token
        self._games: list[int] = []
        self._users: list[str] = []
        self._sessions: list[tuple[str, str]] = []  # (session_id, token)

    # --- raw verbs -------------------------------------------------------
    def req(self, method: str, path: str, token: str | None = None, **kw):
        return httpx.request(
            method,
            f"{self.base}{path}",
            headers=_h(token or self.admin),
            timeout=_TIMEOUT,
            **kw,
        )

    # --- builders (all tracked for teardown) ----------------------------
    def course(self) -> int:
        r = self.req(
            "POST", "/admin/courses", json={"name": f"T4 {_tag()}", "semester": "T"}
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def game(self, course_id: int, token: str | None = None) -> dict:
        r = self.req(
            "POST",
            "/admin/games",
            token,
            json={"title": f"T4 game {_tag()}", "course_id": course_id},
        )
        assert r.status_code == 201, r.text
        self._games.append(r.json()["id"])
        return r.json()

    def question(self, game_id: int) -> None:
        r = self.req(
            "POST",
            f"/admin/games/{game_id}/questions",
            json={
                "type": "true_false",
                "grading_type": "COMPLETENESS",
                "prompt": "Ready?",
                "points_value": 10,
            },
        )
        assert r.status_code == 201, r.text

    def user(self) -> tuple[str, str]:
        """Create a local USER and return (user_id, access_token)."""
        tag = _tag()
        password = f"pw-{tag}-long"
        r = self.req(
            "POST",
            "/admin/users",
            json={
                "username": f"t4_{tag}",
                "display_name": f"T4 {tag}",
                "password": password,
            },
        )
        assert r.status_code == 201, r.text
        user_id = r.json()["id"]
        self._users.append(user_id)
        r = httpx.post(
            f"{self.base}/auth/login",
            json={"username": f"t4_{tag}", "password": password},
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200, r.text
        return user_id, r.json()["access_token"]

    def grant_course(self, user_id: str, course_id: int, role: str = "HOST"):
        return self.req(
            "POST",
            f"/admin/users/{user_id}/course-access",
            json={"course_id": course_id, "role": role},
        )

    def grant_game(self, user_id: str, game_id: int):
        return self.req(
            "POST", f"/admin/users/{user_id}/game-access", json={"game_id": game_id}
        )

    def room(self, course_id: int, game_id: int, token: str | None = None):
        r = self.req(
            "POST",
            "/game/rooms",
            token,
            json={"course_id": course_id, "game_id": game_id},
        )
        if r.status_code == 201:
            self._sessions.append((r.json()["session_id"], token or self.admin))
        return r

    def delete_session(self, session_id: str) -> None:
        r = self.req("DELETE", f"/game/sessions/{session_id}")
        assert r.status_code == 204, r.text
        self._sessions = [s for s in self._sessions if s[0] != session_id]

    def import_bundle(self, raw: bytes, course_id: int | None, name="game.json"):
        data = {} if course_id is None else {"course_id": str(course_id)}
        r = self.req(
            "POST",
            "/admin/games/import",
            files={"file": (name, raw, "application/json")},
            data=data,
        )
        if r.status_code == 201:
            self._games.append(r.json()["game_id"])
        return r

    def track_game(self, game_id: int) -> None:
        self._games.append(game_id)

    def cleanup(self) -> None:
        # Sessions first, through the endpoint that also clears Redis.
        for session_id, _ in self._sessions:
            self.req("DELETE", f"/game/sessions/{session_id}")
        for game_id in self._games:
            self.req("DELETE", f"/admin/games/{game_id}")
        for user_id in self._users:
            self.req("DELETE", f"/admin/users/{user_id}")


@pytest.fixture()
def api(docker_stack, base_url: str, admin_token: str) -> Iterator[Api]:
    a = Api(base_url, admin_token)
    yield a
    a.cleanup()


@pytest.fixture()
def legacy_game(api: Api) -> int:
    """An unassigned game, as migration 004 leaves behind (not creatable via API)."""
    title = f"T4 legacy {_tag()}"
    out = _mysql(
        f"INSERT INTO games (title, description, max_players) "
        f"VALUES ('{title}', '', 10); SELECT LAST_INSERT_ID();"
    )
    game_id = int(out.split()[-1])
    api.track_game(game_id)
    api.question(game_id)
    return game_id


def _error(r: httpx.Response) -> str:
    return r.json().get("error", "")


# ---------------------------------------------------------------------------
# Game creation carries a course (§6.1.3, §6.1.6)
# ---------------------------------------------------------------------------


def test_create_game_records_course(api: Api):
    course_id = api.course()
    game = api.game(course_id)
    assert game["course_id"] == course_id

    r = api.req("GET", f"/admin/games/{game['id']}")
    assert r.status_code == 200
    assert r.json()["course_id"] == course_id


def test_create_game_without_course_is_rejected(api: Api):
    r = api.req("POST", "/admin/games", json={"title": f"T4 {_tag()}"})
    assert r.status_code == 422
    assert _error(r) == "VALIDATION_ERROR"
    assert any(e["loc"][-1] == "course_id" for e in r.json()["detail"])


@pytest.mark.parametrize("bad", [0, -3])
def test_create_game_with_non_positive_course_is_rejected(api: Api, bad: int):
    r = api.req("POST", "/admin/games", json={"title": "x", "course_id": bad})
    assert r.status_code == 422


def test_create_game_with_unknown_course_is_404(api: Api):
    r = api.req(
        "POST", "/admin/games", json={"title": f"T4 {_tag()}", "course_id": 99999999}
    )
    assert r.status_code == 404
    assert _error(r) == "NOT_FOUND"


def test_admin_game_list_includes_course_id(api: Api, legacy_game: int):
    course_id = api.course()
    game = api.game(course_id)
    listed = {g["id"]: g for g in api.req("GET", "/admin/games").json()}
    assert listed[game["id"]]["course_id"] == course_id
    assert listed[legacy_game]["course_id"] is None


# ---------------------------------------------------------------------------
# Import (D10: bundles never carry course_id; course supplied alongside)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _SAMPLE_GAMES, ids=[p.stem for p in _SAMPLE_GAMES])
def test_import_unmodified_sample_game_into_course(api: Api, path: pathlib.Path):
    course_id = api.course()
    raw = path.read_bytes()
    r = api.import_bundle(raw, course_id, name=path.name)
    assert r.status_code == 201, r.text

    game = api.req("GET", f"/admin/games/{r.json()['game_id']}").json()
    assert game["course_id"] == course_id
    assert game["title"] == json.loads(raw)["game"]["title"]
    questions = api.req("GET", f"/admin/games/{game['id']}/questions").json()
    assert len(questions) == len(json.loads(raw)["questions"])


def test_import_without_course_is_rejected(api: Api):
    r = api.import_bundle(_SAMPLE_GAMES[0].read_bytes(), None)
    assert r.status_code == 422
    assert any(e["loc"][-1] == "course_id" for e in r.json()["detail"])


def test_import_into_unknown_course_is_404(api: Api):
    r = api.import_bundle(_SAMPLE_GAMES[0].read_bytes(), 99999999)
    assert r.status_code == 404


def test_import_bundle_carrying_course_id_is_rejected(api: Api):
    """The bundle's game block is validated with GameMeta, which has no course_id."""
    course_id = api.course()
    bundle = json.loads(_SAMPLE_GAMES[0].read_bytes())
    bundle["game"]["course_id"] = course_id
    r = api.import_bundle(json.dumps(bundle).encode(), course_id)
    assert r.status_code == 422


def test_export_never_writes_course_id(api: Api):
    course_id = api.course()
    game = api.game(course_id)
    api.question(game["id"])
    r = api.req("GET", f"/admin/games/{game['id']}/export")
    assert r.status_code == 200
    bundle = r.json()
    assert "course_id" not in bundle["game"]
    # And the export round-trips into another course.
    other = api.course()
    r = api.import_bundle(json.dumps(bundle).encode(), other)
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# Effective host access = game grant AND HOST on the game's course (D1)
# ---------------------------------------------------------------------------


def _my_game_ids(api: Api, token: str) -> dict[int, dict]:
    r = api.req("GET", "/game/my-games", token)
    assert r.status_code == 200, r.text
    return {g["id"]: g for g in r.json()}


def test_host_with_both_grants_can_run_game(api: Api):
    course_id = api.course()
    game = api.game(course_id)
    api.question(game["id"])
    user_id, token = api.user()
    assert api.grant_course(user_id, course_id).status_code == 204
    assert api.grant_game(user_id, game["id"]).status_code == 204

    mine = _my_game_ids(api, token)
    assert mine[game["id"]]["course_id"] == course_id

    r = api.room(course_id, game["id"], token)
    assert r.status_code == 201, r.text


def test_host_denied_on_game_whose_course_they_do_not_host(api: Api):
    """A grant on game G (course A) is useless to a host who only hosts course B."""
    course_a, course_b = api.course(), api.course()
    game = api.game(course_a)
    api.question(game["id"])
    user_id, token = api.user()
    # Legitimately granted while they hosted A ...
    api.grant_course(user_id, course_a)
    assert api.grant_game(user_id, game["id"]).status_code == 204
    # ... then moved to host B only (the grant row survives).
    api.grant_course(user_id, course_a, role="PLAYER")
    api.grant_course(user_id, course_b)

    assert game["id"] not in _my_game_ids(api, token)
    for course_id in (course_a, course_b):
        r = api.room(course_id, game["id"], token)
        assert r.status_code == 403, r.text


def test_revoking_course_host_revokes_game_access(api: Api):
    course_id = api.course()
    game = api.game(course_id)
    api.question(game["id"])
    user_id, token = api.user()
    api.grant_course(user_id, course_id)
    api.grant_game(user_id, game["id"])
    assert game["id"] in _my_game_ids(api, token)

    r = api.req("DELETE", f"/admin/users/{user_id}/course-access/{course_id}")
    assert r.status_code == 204

    assert game["id"] not in _my_game_ids(api, token)
    r = api.room(course_id, game["id"], token)
    assert r.status_code == 403
    # The user's game grant itself is untouched — only its effect is gone.
    detail = api.req("GET", f"/admin/users/{user_id}").json()
    assert game["id"] in detail["game_access"]


def test_game_access_denial_does_not_reveal_which_grant_is_missing(api: Api):
    """Course HOST but no game grant → same 403 message as the reverse case."""
    course_id = api.course()
    game = api.game(course_id)
    api.question(game["id"])

    host_no_grant_id, host_no_grant = api.user()
    api.grant_course(host_no_grant_id, course_id)
    r1 = api.room(course_id, game["id"], host_no_grant)

    grant_no_host_id, grant_no_host = api.user()
    api.grant_course(grant_no_host_id, course_id)
    api.grant_game(grant_no_host_id, game["id"])
    other = api.course()
    api.grant_course(grant_no_host_id, other)
    api.req("DELETE", f"/admin/users/{grant_no_host_id}/course-access/{course_id}")
    r2 = api.room(other, game["id"], grant_no_host)

    assert r1.status_code == r2.status_code == 403
    assert r1.json()["message"] == r2.json()["message"]


def test_host_never_sees_unassigned_game_even_with_grant(api: Api, legacy_game: int):
    course_id = api.course()
    user_id, token = api.user()
    api.grant_course(user_id, course_id)
    # Grant row written directly: the admin API refuses it (tested below).
    _mysql(
        f"INSERT INTO user_game_access (user_id, game_id) "
        f"VALUES ('{user_id}', {legacy_game});"
    )
    assert legacy_game not in _my_game_ids(api, token)
    assert api.room(course_id, legacy_game, token).status_code == 403


def test_admin_my_games_lists_all_games_with_course(api: Api, legacy_game: int):
    course_id = api.course()
    game = api.game(course_id)
    mine = _my_game_ids(api, api.admin)
    assert mine[game["id"]]["course_id"] == course_id
    assert mine[legacy_game]["course_id"] is None


def test_create_room_for_unknown_game_is_404_for_admin(api: Api):
    course_id = api.course()
    r = api.room(course_id, 99999999)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Room course must equal the game's course — admins included (D4)
# ---------------------------------------------------------------------------


def test_create_room_in_other_course_is_409_for_admin(api: Api):
    course_a, course_b = api.course(), api.course()
    game = api.game(course_a)
    api.question(game["id"])
    r = api.room(course_b, game["id"])
    assert r.status_code == 409
    assert "different course" in r.json()["message"]


def test_create_room_in_other_hosted_course_is_409_for_host(api: Api):
    """Host of both courses with a grant: access passes, the invariant still fails."""
    course_a, course_b = api.course(), api.course()
    game = api.game(course_a)
    api.question(game["id"])
    user_id, token = api.user()
    api.grant_course(user_id, course_a)
    api.grant_course(user_id, course_b)
    api.grant_game(user_id, game["id"])
    r = api.room(course_b, game["id"], token)
    assert r.status_code == 409
    assert "different course" in r.json()["message"]


def test_create_room_for_unassigned_game_is_409_for_admin(api: Api, legacy_game: int):
    course_id = api.course()
    r = api.room(course_id, legacy_game)
    assert r.status_code == 409
    assert "not assigned to a course" in r.json()["message"]


def test_room_records_the_games_course(api: Api):
    course_id = api.course()
    game = api.game(course_id)
    api.question(game["id"])
    r = api.room(course_id, game["id"])
    assert r.status_code == 201
    info = api.req("GET", f"/game/rooms/{r.json()['room_code']}").json()
    assert info["course_id"] == course_id


# ---------------------------------------------------------------------------
# Admin game grant requires HOST on the game's course (§6.1.6)
# ---------------------------------------------------------------------------


def test_grant_game_access_without_course_host_is_409(api: Api):
    course_id = api.course()
    game = api.game(course_id)
    user_id, _ = api.user()

    r = api.grant_game(user_id, game["id"])
    assert r.status_code == 409
    assert "HOST access to this game's course" in r.json()["message"]

    # PLAYER on the course is not enough either.
    api.grant_course(user_id, course_id, role="PLAYER")
    assert api.grant_game(user_id, game["id"]).status_code == 409

    # HOST on a different course is not enough either.
    api.grant_course(user_id, api.course())
    assert api.grant_game(user_id, game["id"]).status_code == 409

    api.grant_course(user_id, course_id)
    assert api.grant_game(user_id, game["id"]).status_code == 204
    # Granting twice stays idempotent.
    assert api.grant_game(user_id, game["id"]).status_code == 204


def test_grant_unassigned_game_is_409(api: Api, legacy_game: int):
    course_id = api.course()
    user_id, _ = api.user()
    api.grant_course(user_id, course_id)
    assert api.grant_game(user_id, legacy_game).status_code == 409


def test_grant_game_access_to_admin_needs_no_course(api: Api):
    course_id = api.course()
    game = api.game(course_id)
    admin = next(u for u in api.req("GET", "/admin/users").json() if u["role"] == "ADMIN")
    r = api.grant_game(admin["id"], game["id"])
    assert r.status_code == 204
    api.req("DELETE", f"/admin/users/{admin['id']}/game-access/{game['id']}")
