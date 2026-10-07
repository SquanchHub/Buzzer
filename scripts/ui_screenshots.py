"""
Capture the T9 before/after screenshots of all three apps (docs/plans/t9-theming.md §8).

Imports the Food Fight sample game (every question type, with images) into a fresh course,
then drives the built apps through nginx with Playwright: admin and host management pages,
then a live game with one host and two phones. Each run writes
`<out>/<tag>-<theme>-<app>-<screen>.png`.

    python scripts/ui_screenshots.py --tag before --themes dark
    python scripts/ui_screenshots.py --tag after --themes light,dark

`--themes` sets the browser's `prefers-color-scheme`, which the themed apps follow on a first
visit; the starter apps ignore it. Needs the stack (`docker compose up -d`), a fresh
`npm run build`, and `pip install -r tests/e2e/requirements.txt`.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import Browser, Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.e2e.conftest import BASE_URL, Api  # noqa: E402

BUNDLE = ROOT / "sample_games" / "food_fight_party.json"
DESKTOP = {"viewport": {"width": 1366, "height": 900}}
PHONE = {
    "viewport": {"width": 390, "height": 844},
    "has_touch": True,
    "is_mobile": True,
    "device_scale_factor": 2,
}


def url(path: str) -> str:
    return f"{BASE_URL}{path}"


class Shooter:
    def __init__(self, browser: Browser, out: Path, tag: str, theme: str, token: str):
        self.browser, self.out, self.tag, self.theme = browser, out, tag, theme
        self.token = token

    def context(self, *, phone: bool = False, token: str | None = None):
        ctx = self.browser.new_context(
            **(PHONE if phone else DESKTOP), color_scheme=self.theme
        )
        if token:
            ctx.add_init_script(f"localStorage.setItem('token', {token!r});")
        return ctx

    def shot(self, page: Page, app: str, screen: str) -> None:
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(400)  # let images and transitions settle
        path = self.out / f"{self.tag}-{self.theme}-{app}-{screen}.png"
        page.screenshot(path=str(path))
        print(f"  {path.relative_to(ROOT)}")


def import_game(api: Api) -> tuple[int, int]:
    tag = uuid.uuid4().hex[:4]
    course = api.ok(
        "POST", "/admin/courses", json={"name": f"Food Science {tag}", "semester": "Fall 2026"}
    )["id"]
    r = httpx.post(
        url("/api/admin/games/import"),
        headers={"Authorization": f"Bearer {api.token}"},
        files={"file": (BUNDLE.name, BUNDLE.read_bytes(), "application/json")},
        data={"course_id": str(course)},
        timeout=30,
    )
    r.raise_for_status()
    game = r.json()["game_id"]
    api._games.append(game)
    return course, game


def management(s: Shooter, course: int, game: int) -> None:
    ctx = s.context()
    page = ctx.new_page()
    page.goto(url("/admin/login"))
    s.shot(page, "admin", "login")
    page.goto(url("/host/login"))
    s.shot(page, "host", "login")
    ctx.close()

    ctx = s.context(token=s.token)
    page = ctx.new_page()
    for path, name in (
        ("/admin/courses", "courses"),
        (f"/admin/courses/{course}", "course-detail"),
        ("/admin/games", "games"),
        (f"/admin/games/{game}/questions", "question-editor"),
        (f"/admin/courses/{course}/images", "images"),
        ("/admin/sessions", "sessions"),
    ):
        page.goto(url(path))
        s.shot(page, "admin", name)
    # The hotspot editor: open the fourth question (hotspot) for editing.
    page.goto(url(f"/admin/games/{game}/questions"))
    page.get_by_role("button", name=re.compile("^Edit$")).nth(3).click()
    s.shot(page, "admin", "hotspot-editor")

    for path, name in (
        ("/host/home", "home"),
        (f"/host/courses/{course}", "course"),
        (f"/host/games/{game}/edit", "question-editor"),
    ):
        page.goto(url(path))
        s.shot(page, "host", name)
    ctx.close()


def join(s: Shooter, code: str, name: str, shoot: bool) -> Page:
    page = s.context(phone=True).new_page()
    page.goto(url(f"/player/join?code={code}"))
    page.wait_for_url(re.compile(r"/name/"))  # a ?code= link goes straight on
    if shoot:
        empty = s.context(phone=True).new_page()
        empty.goto(url("/player/join"))
        s.shot(empty, "player", "join")
        empty.context.close()
    page.get_by_placeholder("Your name").fill(name)
    page.get_by_placeholder("you@example.com").fill(f"{name.lower()}@example.com")
    if shoot:
        s.shot(page, "player", "name")
    page.get_by_role("button", name="Join Game").click()
    page.wait_for_url(re.compile(r"/lobby$"))
    return page


def live_game(s: Shooter, api: Api, course: int, game: int) -> None:
    code = api.room(course, game)
    host = s.context(token=s.token).new_page()
    host.goto(url(f"/host/game/{code}/lobby"))
    ada = join(s, code, "Ada", shoot=True)
    bo = join(s, code, "Bo", shoot=False)
    expect(host.get_by_text("2 players joined")).to_be_visible()
    s.shot(host, "host", "lobby")
    s.shot(ada, "player", "lobby")

    def start_next() -> None:
        host.get_by_role(
            "button", name=re.compile("Start Game|Next Question")
        ).click()
        for p in (ada, bo):
            p.wait_for_url(re.compile(r"/question$"))

    def results(prefix: str) -> None:
        host.get_by_role("button", name="Show Results").click()
        host.wait_for_url(re.compile(r"/results$"))
        ada.wait_for_url(re.compile(r"/results$"))
        s.shot(host, "host", f"{prefix}-results")
        s.shot(ada, "player", f"{prefix}-results")

    # Q1 multiple choice: Ada right (Peanut), Bo wrong.
    start_next()
    s.shot(host, "host", "mc-question")
    s.shot(ada, "player", "mc-question")
    ada.get_by_role("button", name=re.compile("Peanut")).click()
    bo.get_by_role("button", name=re.compile("Almond")).click()
    s.shot(ada, "player", "mc-answered")
    results("mc")

    # Q2 ordering: Ada submits the display order as is.
    start_next()
    s.shot(host, "host", "ordering-question")
    for d in range(6):
        item = ada.get_by_test_id(f"ordering-item-{d}")
        if item.count():
            item.click()
    s.shot(ada, "player", "ordering-question")
    ada.get_by_test_id("ordering-submit").click()
    results("ordering")

    # Q3 true/false.
    start_next()
    s.shot(ada, "player", "tf-question")
    results("tf")

    # Q4 hotspot: Ada taps near the target.
    start_next()
    s.shot(host, "host", "hotspot-question")
    canvas = ada.locator("canvas").first
    box = canvas.bounding_box()
    if box:
        ada.mouse.click(box["x"] + box["width"] * 0.52, box["y"] + box["height"] * 0.47)
    s.shot(ada, "player", "hotspot-question")
    submit = ada.get_by_role("button", name=re.compile("Submit"))
    if submit.count():
        submit.first.click()
    results("hotspot")

    # Q5 multi-select, then skip to the end.
    start_next()
    s.shot(ada, "player", "multiselect-question")
    s.shot(host, "host", "multiselect-question")
    results("multiselect")
    while True:
        btn = host.get_by_role(
            "button", name=re.compile("Next Question|Show Final Results")
        )
        final = btn.inner_text().startswith("Show Final")
        btn.click()
        if final:
            break
        host.get_by_role("button", name="Show Results").click()
        host.wait_for_url(re.compile(r"/results$"))
    host.wait_for_url(re.compile(r"/gameover$"))
    ada.wait_for_url(re.compile(r"/gameover$"))
    s.shot(host, "host", "gameover")
    s.shot(ada, "player", "gameover")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", required=True, help="before | after")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--out", default=str(ROOT / "docs" / "ui" / "t9"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    api = Api()
    try:
        course, game = import_game(api)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for theme in args.themes.split(","):
                print(f"{args.tag} / {theme}")
                s = Shooter(browser, out, args.tag, theme, api.token)
                management(s, course, game)
                live_game(s, api, course, game)
            browser.close()
    finally:
        api.cleanup()


if __name__ == "__main__":
    main()
