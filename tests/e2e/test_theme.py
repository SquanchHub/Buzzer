"""
T9 light/dark themes — browser e2e (docs/plans/t9-theming.md §8.2).

Runs against the built apps through nginx; rebuild (`npm run build`) after UI changes.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

from .conftest import BASE_URL, DESKTOP, PHONE, url

_CSS = Path(__file__).resolve().parents[2] / "frontend" / "host" / "src" / "index.css"
ENTRY = {"admin": "/admin/login", "host": "/host/login", "player": "/player/join"}


def _canvas(theme: str) -> str:
    """The token's colour in the browser's computed-style format, `rgb(r, g, b)`."""
    css = _CSS.read_text()
    sel = r':root,\s*\[data-theme="light"\]' if theme == "light" else r'\[data-theme="dark"\]'
    rule = re.search(sel + r"\s*\{(.*?)\}", css, re.S).group(1)
    r, g, b = re.search(r"--canvas:\s*(\d+) (\d+) (\d+);", rule).groups()
    return f"rgb({r}, {g}, {b})"


def _ctx(browser: Browser, scheme: str, *, phone: bool = False, token: str | None = None) -> BrowserContext:
    ctx = browser.new_context(**(PHONE if phone else DESKTOP), color_scheme=scheme)
    if token:
        ctx.add_init_script(f"localStorage.setItem('token', {token!r});")
    return ctx


def _theme(page: Page) -> str | None:
    return page.evaluate("document.documentElement.dataset.theme ?? null")


def _stored(page: Page) -> str | None:
    return page.evaluate("localStorage.getItem('buzzer-theme')")


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("app", list(ENTRY))
def test_first_visit_follows_os(browser, app, scheme):
    ctx = _ctx(browser, scheme, phone=app == "player")
    page = ctx.new_page()
    page.goto(url(ENTRY[app]))
    assert _theme(page) == scheme
    assert _stored(page) is None
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bg == _canvas(scheme)
    ctx.close()


@pytest.mark.parametrize("app", list(ENTRY))
def test_toggle_flips_and_persists(browser, app):
    ctx = _ctx(browser, "light", phone=app == "player")
    page = ctx.new_page()
    page.goto(url(ENTRY[app]))
    toggle = page.get_by_test_id("theme-toggle")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("aria-checked", "false")
    toggle.click()
    assert _theme(page) == "dark"
    assert _stored(page) == "dark"
    expect(toggle).to_have_attribute("aria-checked", "true")

    # The inline <head> script applies the stored choice before the app mounts.
    page.reload(wait_until="domcontentloaded")
    assert _theme(page) == "dark"
    page.wait_for_load_state("networkidle")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == _canvas("dark")

    page.get_by_test_id("theme-toggle").click()
    assert _theme(page) == "light"
    assert _stored(page) == "light"
    ctx.close()


def test_choice_beats_os_and_is_shared(browser):
    ctx = _ctx(browser, "light", phone=True)
    page = ctx.new_page()
    page.goto(url("/player/join"))
    page.get_by_test_id("theme-toggle").click()
    assert _stored(page) == "dark"
    page.goto(url("/host/login"))
    assert _theme(page) == "dark"
    page.goto(url("/admin/login"))
    assert _theme(page) == "dark"
    ctx.close()


def _join(ctx: BrowserContext, code: str, name: str) -> Page:
    page = ctx.new_page()
    page.goto(url(f"/player/join?code={code}"))
    page.get_by_placeholder("Your name").fill(name)
    page.get_by_placeholder("you@example.com").fill(f"{name.lower()}@example.com")
    page.get_by_role("button", name="Join Game").click()
    page.wait_for_url(re.compile(r"/lobby$"))
    return page


def test_toggle_on_signed_in_screens(browser, api):
    course, game = api.course_and_game("Theme toggle")
    api.question(
        game,
        {
            "type": "true_false",
            "grading_type": "ACCURACY",
            "prompt": "Paper is light.",
            "config": {},
            "answer_data": {"answer_points": {"true": 100, "false": 0}},
            "time_limit_seconds": 60,
            "points_value": 100,
        },
    )
    ctx = _ctx(browser, "dark", token=api.token)
    page = ctx.new_page()
    for path in ("/admin/users", "/host/home"):
        page.goto(url(path))
        expect(page.get_by_test_id("theme-toggle")).to_be_visible()
    code = api.room(course, game)
    page.goto(url(f"/host/game/{code}/lobby"))
    expect(page.get_by_test_id("theme-toggle")).to_be_visible()

    phone = _join(_ctx(browser, "dark", phone=True), code, "Toggle")
    expect(phone.get_by_test_id("theme-toggle")).to_be_visible()
    box = phone.get_by_test_id("theme-toggle").bounding_box()
    assert box and box["width"] >= 44 and box["height"] >= 44, box
    phone.context.close()
    ctx.close()


def test_keyboard_focus_visible(browser):
    ctx = _ctx(browser, "light")
    page = ctx.new_page()
    page.goto(url("/host/login"))
    page.wait_for_load_state("networkidle")
    seen = 0
    for _ in range(6):
        page.keyboard.press("Tab")
        style = page.evaluate(
            """() => { const el = document.activeElement;
                 if (!el || el === document.body) return null;
                 const s = getComputedStyle(el);
                 return {tag: el.tagName, outline: s.outlineStyle, width: s.outlineWidth,
                         shadow: s.boxShadow}; }"""
        )
        if style is None:
            continue
        seen += 1
        visible = (style["outline"] != "none" and style["width"] != "0px") or (
            style["shadow"] not in ("none", "")
        )
        assert visible, f"no visible focus on {style}"
    assert seen >= 2


def _png(width: int, height: int) -> bytes:
    from PIL import Image  # e2e requirements include Pillow via the backend venv

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (120, 160, 200)).save(buf, "PNG")
    return buf.getvalue()


def test_hotspot_canvas_repaints_on_toggle(browser, api):
    course, game = api.course_and_game("Theme hotspot")
    r = httpx.post(
        f"{BASE_URL}/api/images",
        headers={"Authorization": f"Bearer {api.token}"},
        files={"file": ("strip.png", _png(400, 100), "image/png")},
        data={"course_id": str(course)},
        timeout=30,
    )
    assert r.is_success, r.text
    image_id = r.json()["id"]
    api.question(
        game,
        {
            "type": "hotspot",
            "grading_type": "ACCURACY",
            "prompt": "Tap the middle.",
            "config": {"imageId": image_id, "aspectRatio": 4},
            "answer_data": {
                "x": 0.5,
                "y": 0.5,
                "innerRadius": 0.05,
                "outerRadius": 0.1,
                "partialFraction": 0.5,
            },
            "time_limit_seconds": 120,
            "points_value": 100,
        },
    )
    code = api.room(course, game)
    host_ctx = _ctx(browser, "light", token=api.token)
    host = host_ctx.new_page()
    host.goto(url(f"/host/game/{code}/lobby"))
    phone = _join(_ctx(browser, "light", phone=True), code, "Tapper")
    host.get_by_role("button", name="Start Game").click()
    phone.wait_for_url(re.compile(r"/question$"))

    canvas = phone.locator("canvas").first
    expect(canvas).to_be_visible()
    box = canvas.bounding_box()
    assert box
    phone.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    phone.wait_for_timeout(300)
    before = hash(canvas.evaluate("c => c.toDataURL()"))
    phone.get_by_test_id("theme-toggle").click()
    phone.wait_for_timeout(300)
    after = hash(canvas.evaluate("c => c.toDataURL()"))
    assert before != after, "hotspot canvas did not repaint on theme change"
    phone.context.close()
    host_ctx.close()
