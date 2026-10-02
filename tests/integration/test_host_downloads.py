# ruff: noqa: F811 — `hapi` is a pytest fixture imported from host_helpers; test
# parameters named after it are how pytest injects it, not redefinitions.
"""
T4 phase 2 — session downloads (docs/plans/t4-ui-restructuring.md D9, §6.2.4, §6.4):

Downloads (HTML report and CSV): 403 for a non-host, 409 before COMPLETED, 200 with the
correct CSV columns / HTML for the host. Also GET /game/my-sessions, which lists them.
"""

from __future__ import annotations

import csv
import io

import pytest

from .host_helpers import hapi  # noqa: F401

DOWNLOADS = [
    ("report", "/game/sessions/{}/report", "text/html"),
    ("export", "/game/sessions/{}/export", "text/csv"),
]


@pytest.mark.parametrize(
    ("name", "path", "ctype"), DOWNLOADS, ids=[d[0] for d in DOWNLOADS]
)
async def test_session_downloads(hapi, name, path, ctype):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course, questions=2)
    code, session = hapi.room(host, course, game)
    url = path.format(session)

    # Not finished yet: 409 for the host (and admin); a non-host is refused first.
    assert hapi.req("GET", url, host).status_code == 409
    assert hapi.req("GET", url).status_code == 409
    _, outsider = hapi.user()
    assert hapi.req("GET", url, outsider).status_code == 403

    await hapi.play(host, code, answers=2)

    r = hapi.req("GET", url, host)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(ctype)
    assert "attachment" in r.headers["content-disposition"]
    if name == "export":
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == ["Player", "Q1", "Q2", "Total"]
        assert len(rows) == 3  # one row per player
        assert all(float(row[-1]) == 2000 for row in rows[1:])  # both correct on both
    else:
        assert "<html" in r.text.lower() and "Host game" in r.text
        assert "Guest" not in r.text  # PII-free: no player names

    # Only the session's host or an admin: another HOST of the same course is refused.
    _, cohost = hapi.host_of(course)
    for token in (outsider, cohost):
        r = hapi.req("GET", url, token)
        assert (
            r.status_code == 403
            and r.json()["message"] == "Only the session host can access this session"
        )
    assert hapi.req("GET", url).status_code == 200  # admin
    assert hapi.req("GET", path.format("no-such-session"), host).status_code == 404


async def test_my_sessions_lists_completed_hosted_sessions(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    game = hapi.host_game(host, course)
    code, done = hapi.room(host, course, game)
    await hapi.play(host, code, answers=3)
    _, open_session = hapi.room(host, course, game)  # still LOBBY

    mine = hapi.req("GET", "/game/my-sessions", host).json()
    assert [m["session_id"] for m in mine] == [done]
    item = mine[0]
    assert item["room_code"] == code and item["player_count"] == 3
    assert (
        item["game_title"].startswith("Host game") and item["course_semester"] == "Test"
    )
    assert item["completed_at"] is not None
    assert open_session not in [m["session_id"] for m in mine]
    _, other = hapi.host_of(course)
    assert hapi.req("GET", "/game/my-sessions", other).json() == []
