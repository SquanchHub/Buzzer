"""
Read-your-writes: a write is committed before its response is sent
(docs/plans/t4-ui-restructuring.md §6.2.5 k, backend/app/database.py DbSession).

`database.get_db` commits after `yield`. With FastAPI's default dependency scope
("request") that cleanup runs *after* the response has been sent, so a client on a
keep-alive connection that acts right after a write can miss it. This test runs the seven
write-then-act patterns of scripts/probe_commit_timing.py — imported, not copied, so the
probe and the test can't drift — on one keep-alive connection and allows zero stale
rounds. The patterns cover host and admin creates, updates and deletes, a control whose
handler commits itself, and a write that depends on the previous write (course grant →
game grant).
"""

from __future__ import annotations

import importlib.util

import httpx

from .conftest import _REPO_ROOT

_N = 50  # rounds per pattern; the course → game grant pattern runs _N // 5

_spec = importlib.util.spec_from_file_location(
    "probe_commit_timing", _REPO_ROOT / "scripts" / "probe_commit_timing.py"
)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def test_writes_are_visible_to_the_next_request(docker_stack, base_url, admin_token):
    # One client = one keep-alive connection, so the next request can arrive before
    # the previous handler's cleanup would have finished under the old scope.
    with httpx.Client(
        headers={"Authorization": f"Bearer {admin_token}"}, timeout=10.0
    ) as client:
        results = probe.run_patterns(client, f"{base_url}/api", _N)
    assert len(results) == 7, results
    stale = {name: f"{bad}/{rounds}" for name, (bad, rounds) in results.items() if bad}
    assert not stale, f"rounds that missed the preceding write: {stale}"
