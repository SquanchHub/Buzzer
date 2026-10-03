"""
Probe: does a write's commit land before its HTTP response?

FastAPI runs a yield dependency's exit code after the response is sent unless it is
function-scoped, so before database.DbSession (docs/plans/t4-ui-restructuring.md §6.2.5 k)
get_db committed after the client already had its 2xx, and a keep-alive client that acted
right after a write could see stale or missing data. Each pattern does write-then-act rounds
on ONE keep-alive client and counts rounds whose second request didn't see the write.
Expected: 0 everywhere. tests/integration/test_commit_timing.py runs the same patterns
(via run_patterns) as a regression test.

Run from the repo root against the live stack:  .venv/bin/python scripts/probe_commit_timing.py [N]
(N rounds per pattern, default 200; pattern 7 runs N // 5 because each round creates a
user. BASE_URL defaults to http://localhost:8000; admin credentials come from .env.)
Creates one course per run (courses can't be deleted) and deletes its games and users.
"""

import os
import sys
import time
import uuid

import httpx
from dotenv import dotenv_values

MC = {
    "type": "multiple_choice",
    "grading_type": "ACCURACY",
    "prompt": "p0",
    "config": {"options": ["a", "b"]},
    "answer_data": {"answer_points": [1, 0]},
    "points_value": 1,
}


def run_patterns(c: httpx.Client, api: str, n: int) -> dict[str, tuple[int, int]]:
    """{pattern: (stale, rounds)}. `c` is an admin-authenticated keep-alive client and
    `api` the base URL ending in /api. Writes must succeed (raises otherwise), so a failed
    write can't pass as a fresh read. The exceptions are responses that are themselves the
    symptom: pattern 5's delete 404ing (it couldn't see the just-created question) and
    pattern 7's game grant 409ing (it couldn't see the just-written course grant)."""

    def ok(r: httpx.Response) -> httpx.Response:
        r.raise_for_status()
        return r

    def visible(url: str) -> None:
        """Setup only (not measured): wait until a just-written row is readable."""
        for _ in range(50):
            if c.get(url).status_code == 200:
                return
            time.sleep(0.02)
        raise RuntimeError(f"{url} never became visible")

    cid = ok(
        c.post(
            f"{api}/admin/courses",
            json={"name": "commit-timing probe", "semester": "T"},
        )
    ).json()["id"]
    games: list[int] = []
    users: list[str] = []

    def new_game(path: str) -> int:
        gid = ok(
            c.post(f"{api}{path}", json={"title": "probe", "course_id": cid})
        ).json()["id"]
        games.append(gid)
        return gid

    results: dict[str, tuple[int, int]] = {}
    try:
        # 1. host create -> read (content_service flushes only; get_db commits)
        bad = 0
        for _ in range(n):
            gid = new_game("/host/games")
            bad += c.get(f"{api}/host/games/{gid}").status_code == 404
        results["POST /host/games -> GET"] = (bad, n)

        # 2. admin update -> read (handler without its own commit)
        gid = new_game("/admin/games")
        visible(f"{api}/admin/games/{gid}")
        bad = 0
        for i in range(n):
            ok(c.put(f"{api}/admin/games/{gid}", json={"title": f"t{i}"}))
            bad += c.get(f"{api}/admin/games/{gid}").json()["title"] != f"t{i}"
        results["PUT /admin/games/{id} -> GET"] = (bad, n)

        # 3. admin create -> read (control: the handler commits itself)
        bad = 0
        for _ in range(n):
            g = new_game("/admin/games")
            bad += c.get(f"{api}/admin/games/{g}").status_code == 404
        results["POST /admin/games -> GET"] = (bad, n)

        # 4. host question update -> read
        gid = new_game("/host/games")
        visible(f"{api}/host/games/{gid}")
        qid = ok(c.post(f"{api}/host/games/{gid}/questions", json=MC)).json()["id"]
        time.sleep(0.2)  # setup: let the question's commit land before measuring
        bad = 0
        for i in range(n):
            url = f"{api}/host/games/{gid}/questions"
            ok(c.put(f"{url}/{qid}", json={"prompt": f"p{i + 1}"}))
            bad += c.get(url).json()[0]["prompt"] != f"p{i + 1}"
        results["PUT /host/games/{id}/questions/{q} -> GET"] = (bad, n)

        # 5. host question delete -> read
        bad = 0
        for _ in range(n):
            url = f"{api}/host/games/{gid}/questions"
            q = ok(c.post(url, json=MC)).json()["id"]
            r = c.delete(f"{url}/{q}")
            if r.status_code == 404:  # the delete couldn't see the create: stale too
                bad += 1
                continue
            ok(r)
            bad += q in [x["id"] for x in c.get(url).json()]
        results["DELETE /host/games/{id}/questions/{q} -> GET"] = (bad, n)

        # 6. admin game delete -> read (the delete handler relies on get_db)
        bad = 0
        for _ in range(n):
            g = new_game("/admin/games")  # create commits itself
            ok(c.delete(f"{api}/admin/games/{g}"))
            bad += c.get(f"{api}/admin/games/{g}").status_code != 404
        results["DELETE /admin/games/{id} -> GET"] = (bad, n)

        # 7. course grant -> game grant: a write that depends on the previous write.
        #    The game grant is a 409 unless the user already HOSTs the game's course.
        gid = new_game("/admin/games")
        visible(f"{api}/admin/games/{gid}")
        rounds = max(1, n // 5)
        bad = 0
        for _ in range(rounds):
            name = f"probe_{uuid.uuid4().hex[:8]}"
            uid = ok(
                c.post(
                    f"{api}/admin/users",
                    json={
                        "username": name,
                        "display_name": "probe",
                        "password": "probe-pw1",
                    },
                )
            ).json()["id"]  # create commits itself
            users.append(uid)
            ok(
                c.post(
                    f"{api}/admin/users/{uid}/course-access",
                    json={"course_id": cid, "role": "HOST"},
                )
            )
            r = c.post(f"{api}/admin/users/{uid}/game-access", json={"game_id": gid})
            if r.status_code == 409:  # the grant couldn't see the course grant
                bad += 1
            else:
                ok(r)
        results["POST course-access -> POST game-access"] = (bad, rounds)
    finally:
        for u in users:
            c.delete(f"{api}/admin/users/{u}")
        for g in games:
            c.delete(f"{api}/admin/games/{g}")
    return results


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    api = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/") + "/api"
    env = dotenv_values(".env")
    tok = httpx.post(
        f"{api}/auth/login",
        json={
            "username": env.get("ADMIN_USERNAME", "admin"),
            "password": env.get("ADMIN_PASSWORD", "changeme123"),
        },
    ).json()["access_token"]
    with httpx.Client(headers={"Authorization": f"Bearer {tok}"}, timeout=10) as c:
        results = run_patterns(c, api, n)
    for name, (bad, rounds) in results.items():
        print(f"{bad:>4}/{rounds:<4} stale  {name}")
    return 1 if any(bad for bad, _ in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
