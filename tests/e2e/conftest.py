"""
Browser e2e fixtures (docs/plans/t7-ordering.md §9.3).

Runs real Chromium (sync Playwright API) against the live Docker stack, through nginx, so
the built apps (`npm run build`) are what gets tested. Plain Playwright, not the
pytest-playwright plugin: that plugin registers a `--base-url` option that clashes with
tests/integration/conftest.py when both suites share one virtualenv.

Each browser context has its own localStorage, so a host and several players can share
one origin without overwriting each other's `token`.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

_REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8080").rstrip("/")
PHONE = {"viewport": {"width": 375, "height": 667}, "has_touch": True, "is_mobile": True}
DESKTOP = {"viewport": {"width": 1280, "height": 800}}
_TIMEOUT = 10.0


def _env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env = _REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.partition("=")[2].strip()
    return None


class Api:
    """The stack's REST API as the admin; tracks what it creates for teardown."""

    def __init__(self) -> None:
        r = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "username": _env("ADMIN_USERNAME") or "admin",
                "password": _env("ADMIN_PASSWORD") or "",
            },
            timeout=_TIMEOUT,
        )
        assert r.status_code == 200, f"admin login failed: {r.text}"
        self.token: str = r.json()["access_token"]
        self._games: list[int] = []
        self._sessions: list[str] = []

    def req(self, method: str, path: str, **kw) -> httpx.Response:
        return httpx.request(
            method,
            f"{BASE_URL}/api{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=_TIMEOUT,
            **kw,
        )

    def ok(self, method: str, path: str, **kw):
        r = self.req(method, path, **kw)
        assert r.is_success, f"{method} {path} -> {r.status_code}: {r.text}"
        return r.json() if r.content else None

    def course_and_game(self, title: str = "E2E game") -> tuple[int, int]:
        tag = uuid.uuid4().hex[:6]
        course = self.ok(
            "POST", "/admin/courses", json={"name": f"E2E {tag}", "semester": "Test"}
        )["id"]
        game = self.ok(
            "POST", "/admin/games", json={"title": f"{title} {tag}", "course_id": course}
        )["id"]
        self._games.append(game)
        return course, game

    def question(self, game_id: int, body: dict) -> dict:
        return self.ok("POST", f"/admin/games/{game_id}/questions", json=body)

    def questions(self, game_id: int) -> list[dict]:
        return self.ok("GET", f"/admin/games/{game_id}/questions")

    def room(self, course_id: int, game_id: int) -> str:
        r = self.ok(
            "POST", "/game/rooms", json={"course_id": course_id, "game_id": game_id}
        )
        self._sessions.append(r["session_id"])
        return r["room_code"]

    def cleanup(self) -> None:
        for sid in self._sessions:
            self.req("DELETE", f"/game/sessions/{sid}")  # also clears Redis
        for gid in self._games:
            self.req("DELETE", f"/admin/games/{gid}")


@pytest.fixture(scope="session")
def browser():
    try:
        httpx.get(f"{BASE_URL}/api/health", timeout=5.0).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.exit(f"Stack not reachable at {BASE_URL} ({exc}); run docker compose up")
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def api():
    a = Api()
    yield a
    a.cleanup()


@pytest.fixture()
def new_context(browser: Browser, request):
    """Factory: new_context(token=None, phone=False) → BrowserContext. Each context
    records console errors and failed requests in `context.problems`."""
    contexts: list[BrowserContext] = []

    def make(token: str | None = None, phone: bool = False) -> BrowserContext:
        ctx = browser.new_context(**(PHONE if phone else DESKTOP))
        ctx.problems = []  # type: ignore[attr-defined]
        if token:
            ctx.add_init_script(f"localStorage.setItem('token', {token!r});")

        def watch(page: Page) -> None:
            page.on(
                "console",
                lambda m: m.type == "error"
                and ctx.problems.append(f"console: {m.text}"),  # type: ignore[attr-defined]
            )
            page.on(
                "requestfailed",
                lambda r: ctx.problems.append(  # type: ignore[attr-defined]
                    f"request failed: {r.method} {r.url} {r.failure}"
                ),
            )

        ctx.on("page", watch)
        contexts.append(ctx)
        return ctx

    yield make
    for ctx in contexts:
        ctx.close()


def url(path: str) -> str:
    return f"{BASE_URL}{path}"
