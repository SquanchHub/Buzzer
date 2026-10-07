"""
Player socket lifetime — browser e2e.

Regression tests for the player socket being torn down and reopened on every page change
(GameLayout's socket effect depended on `navigate`), which lost answers submitted right
after `new_question` and could strand a phone on the previous results screen.
"""

from __future__ import annotations

import re

from playwright.sync_api import BrowserContext, Page, expect

from .conftest import url

OPTIONS = ["Red", "Green", "Blue", "Yellow"]


def _question(n: int) -> dict:
    return {
        "type": "multiple_choice",
        "grading_type": "ACCURACY",
        "prompt": f"Question {n}: pick Green.",
        "config": {"options": OPTIONS},
        "answer_data": {"answer_points": [0.0, 1.0, 0.0, 0.0]},
        "time_limit_seconds": 120,
        "points_value": 1000,
    }


def _game(api, questions: int = 2) -> str:
    course, game = api.course_and_game("Socket")
    for n in range(1, questions + 1):
        api.question(game, _question(n))
    return api.room(course, game)


def _join(ctx: BrowserContext, code: str, name: str) -> Page:
    page = ctx.new_page()
    page.sockets = []  # type: ignore[attr-defined]
    page.on(
        "websocket",
        lambda ws: "/socket.io" in ws.url and page.sockets.append(ws.url),  # type: ignore[attr-defined]
    )
    page.goto(url(f"/player/join?code={code}"))
    page.get_by_placeholder("Your name").fill(name)
    page.get_by_placeholder("you@example.com").fill(f"{name.lower()}@example.com")
    page.get_by_role("button", name="Join Game").click()
    page.wait_for_url(re.compile(r"/lobby$"))
    return page


def _host(new_context, api, code: str) -> Page:
    host = new_context(token=api.token).new_page()
    host.goto(url(f"/host/game/{code}/lobby"))
    return host


def _pick_green(phone: Page) -> None:
    phone.get_by_role("button", name=re.compile(r"Green")).click()


def test_one_socket_for_the_whole_game(api, new_context):
    """Navigating question → feedback → results → question must not reopen the socket."""
    code = _game(api)
    host = _host(new_context, api, code)
    phone_ctx = new_context(phone=True)
    phone = _join(phone_ctx, code, "Solo")

    host.get_by_role("button", name="Start Game").click()
    for _ in range(2):
        phone.wait_for_url(re.compile(r"/question$"))
        _pick_green(phone)
        phone.wait_for_url(re.compile(r"/feedback$"))
        host.get_by_role("button", name="Show Results").click()
        phone.wait_for_url(re.compile(r"/results$"))
        host.get_by_role(
            "button", name=re.compile(r"^(Next Question|Show Final Results)$")
        ).click()
    phone.wait_for_url(re.compile(r"/gameover$"))

    # The socket opened on reaching the lobby carries the whole game.
    assert len(phone.sockets) == 1, phone.sockets  # type: ignore[attr-defined]
    assert phone_ctx.problems == []


def test_answer_immediately_after_new_question_is_scored(api, new_context):
    """An answer sent the moment the question appears is acknowledged and scored."""
    code = _game(api)
    host = _host(new_context, api, code)
    phone_ctx = new_context(phone=True)
    phone = _join(phone_ctx, code, "Quick")

    host.get_by_role("button", name="Start Game").click()
    for n in (1, 2):
        phone.wait_for_url(re.compile(r"/question$"))
        _pick_green(phone)  # no pause: inside the old reconnect window
        expect(phone.get_by_text("Answer locked in!")).to_be_visible()
        host.get_by_role("button", name="Show Results").click()
        expect(phone.get_by_text("Correct!")).to_be_visible()
        if n == 1:
            host.get_by_role("button", name="Next Question").click()
    assert phone_ctx.problems == []


def test_reload_after_answering_shows_waiting(api, new_context):
    """sync_state's hasAnswered restores the waiting screen after a reload."""
    code = _game(api, questions=1)
    host = _host(new_context, api, code)
    phone = _join(new_context(phone=True), code, "Reload")

    host.get_by_role("button", name="Start Game").click()
    phone.wait_for_url(re.compile(r"/question$"))
    _pick_green(phone)
    expect(phone.get_by_text("Answer locked in!")).to_be_visible()

    phone.reload()
    expect(phone.get_by_text("Answer locked in!")).to_be_visible()
    expect(phone.get_by_text("Loading question…")).to_have_count(0)

    host.get_by_role("button", name="Show Results").click()
    expect(phone.get_by_text("Correct!")).to_be_visible()


def test_reload_on_locked_unanswered_question_restores_it(api, new_context):
    """A locked question is not re-sent as new_question; sync_state must restore it."""
    code = _game(api, questions=1)
    host = _host(new_context, api, code)
    phone = _join(new_context(phone=True), code, "Locked")

    host.get_by_role("button", name="Start Game").click()
    phone.wait_for_url(re.compile(r"/question$"))
    host.get_by_role("button", name="Lock Question").click()
    expect(phone.get_by_text("Answers locked — waiting for results…")).to_be_visible()

    phone.reload()
    expect(phone.get_by_text("Answers locked — waiting for results…")).to_be_visible()
    expect(phone.get_by_text("Loading question…")).to_have_count(0)
    for text in OPTIONS:
        expect(phone.get_by_text(text)).to_be_visible()
