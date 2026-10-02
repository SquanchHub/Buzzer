# ruff: noqa: F811 — `hapi` is a pytest fixture imported from host_helpers; test
# parameters named after it are how pytest injects it, not redefinitions.
"""
T4 phase 2 — host roster management (docs/plans/t4-ui-restructuring.md §6.2.3, §6.4):

- Host roster import deactivates missing netids; a non-HOST gets 403.
- Host roster PATCH with a roster_id from another course → 404.
"""

from __future__ import annotations

import uuid

from .host_helpers import hapi  # noqa: F401


def _rows(n: int) -> list[dict]:
    tag = uuid.uuid4().hex[:6]
    return [
        {
            "netid": f"r{tag}{i}",
            "full_name": f"Student {i}",
            "email": f"r{tag}{i}@example.com",
        }
        for i in range(n)
    ]


def _roster(hapi, token, course) -> dict[str, dict]:
    r = hapi.req("GET", f"/host/courses/{course}/roster", token)
    assert r.status_code == 200, r.text
    return {e["netid"]: e for e in r.json()}


def test_roster_import_deactivates_missing_netids(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    rows = _rows(3)

    r = hapi.req(
        "POST", f"/host/courses/{course}/roster/import", host, json={"rows": rows}
    )
    assert r.status_code == 200, r.text
    roster = _roster(hapi, host, course)
    assert {n: e["is_active"] for n, e in roster.items()} == {
        row["netid"]: True for row in rows
    }

    # Re-upload without the first student: they are deactivated, not deleted.
    r = hapi.req(
        "POST", f"/host/courses/{course}/roster/import", host, json={"rows": rows[1:]}
    )
    assert r.status_code == 200, r.text
    roster = _roster(hapi, host, course)
    assert roster[rows[0]["netid"]]["is_active"] is False
    assert all(roster[row["netid"]]["is_active"] for row in rows[1:])

    # Uploading them again reactivates them.
    hapi.req("POST", f"/host/courses/{course}/roster/import", host, json={"rows": rows})
    assert _roster(hapi, host, course)[rows[0]["netid"]]["is_active"] is True


def test_roster_endpoints_403_for_a_non_host(hapi):
    course, other = hapi.course(), hapi.course()
    _, host = hapi.host_of(course)
    hapi.req(
        "POST", f"/host/courses/{course}/roster/import", host, json={"rows": _rows(1)}
    )
    rid = next(iter(_roster(hapi, host, course).values()))["id"]

    _, outsider = hapi.user()
    player_id, player = hapi.user()
    hapi.grant_course(player_id, course, role="PLAYER")
    _, other_host = hapi.host_of(other)
    for who, token in [
        ("no access", outsider),
        ("PLAYER role", player),
        ("HOST of another course", other_host),
    ]:
        assert (
            hapi.req("GET", f"/host/courses/{course}/roster", token).status_code == 403
        ), who
        r = hapi.req(
            "POST",
            f"/host/courses/{course}/roster/import",
            token,
            json={"rows": _rows(1)},
        )
        assert r.status_code == 403, who
        r = hapi.req(
            "PATCH",
            f"/host/courses/{course}/roster/{rid}",
            token,
            json={"is_active": False},
        )
        assert r.status_code == 403, who
    # Nothing changed.
    assert len(_roster(hapi, host, course)) == 1


def test_roster_patch_with_another_courses_row_is_404(hapi):
    course_a, course_b = hapi.course(), hapi.course()
    host_id, host = hapi.host_of(course_a)
    hapi.grant_course(host_id, course_b)  # HOSTs both: the course check passes for A
    hapi.req(
        "POST", f"/host/courses/{course_b}/roster/import", host, json={"rows": _rows(1)}
    )
    row_b = next(iter(_roster(hapi, host, course_b).values()))

    r = hapi.req(
        "PATCH",
        f"/host/courses/{course_a}/roster/{row_b['id']}",
        host,
        json={"is_active": False},
    )
    assert r.status_code == 404, r.text
    assert _roster(hapi, host, course_b)[row_b["netid"]]["is_active"] is True

    # Through its own course the same PATCH works, with the admin route's normalisation.
    r = hapi.req(
        "PATCH",
        f"/host/courses/{course_b}/roster/{row_b['id']}",
        host,
        json={
            "is_active": False,
            "netid": "  MixedCase ",
            "full_name": "  Renamed  ",
            "email": "A@Example.com",
        },
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["is_active"],
        r.json()["netid"],
        r.json()["full_name"],
        r.json()["email"],
    ) == (
        False,
        "mixedcase",
        "Renamed",
        "a@example.com",
    )
