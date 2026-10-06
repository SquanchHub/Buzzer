"""
Ordering question type — browser e2e (docs/plans/t7-ordering.md §9.3).

Questions and rooms are created over the API; only the UI under test is driven.
"""

from __future__ import annotations

import re

from playwright.sync_api import BrowserContext, Page, expect

from .conftest import url

LONG = (
    "Metaphase: the chromosomes line up along the middle of the cell, ready to split."
)
assert len(LONG) == 80
# Display order (what players see). Correct order: P, M(LONG), A, T, C, I.
ITEMS = ["Anaphase", "Telophase", LONG, "Cytokinesis", "Prophase", "Interphase"]
CORRECT = [4, 2, 0, 1, 3, 5]
# Correct with Prophase moved to the end: one item out of place.
ONE_MOVED = [2, 0, 1, 3, 5, 4]


def _question(**overrides) -> dict:
    body = {
        "type": "ordering",
        "grading_type": "ACCURACY",
        "prompt": "Order the stages, first to last.",
        "config": {"items": ITEMS},
        "answer_data": {"correctOrder": CORRECT, "partialCredit": True},
        "time_limit_seconds": 120,
        "points_value": 1000,
    }
    body.update(overrides)
    return body


def _join(ctx: BrowserContext, code: str, name: str) -> Page:
    page = ctx.new_page()
    page.goto(url(f"/player/join?code={code}"))
    page.get_by_placeholder("Your name").fill(name)
    page.get_by_placeholder("you@example.com").fill(f"{name.lower()}@example.com")
    page.get_by_role("button", name="Join Game").click()
    page.wait_for_url(re.compile(r"/lobby$"))
    return page


def _open_host(new_context, api, code: str) -> Page:
    host = new_context(token=api.token).new_page()
    host.goto(url(f"/host/game/{code}/lobby"))
    return host


def _tap_order(page: Page, order: list[int]) -> None:
    for d in order:
        page.get_by_test_id(f"ordering-item-{d}").click()


def test_player_answers_on_a_phone(api, new_context):
    """§9.3 test 2."""
    course, game = api.course_and_game()
    api.question(game, _question())
    code = api.room(course, game)
    host = _open_host(new_context, api, code)
    phone_ctx = new_context(phone=True)
    phone = _join(phone_ctx, code, "Phone")

    host.get_by_role("button", name="Start Game").click()
    phone.wait_for_url(re.compile(r"/question$"))

    # Every item fits on screen with no scrolling and is a comfortable tap target.
    viewport = phone.viewport_size
    for d in range(len(ITEMS)):
        item = phone.get_by_test_id(f"ordering-item-{d}")
        expect(item).to_be_visible()
        box = item.bounding_box()
        assert box is not None
        assert box["height"] >= 44, (d, box)
        assert box["y"] >= 0 and box["y"] + box["height"] <= viewport["height"], (
            d,
            box,
        )
    assert (
        phone.evaluate("document.documentElement.scrollHeight")
        <= viewport["height"] + 1
    )
    submit = phone.get_by_test_id("ordering-submit")
    expect(submit).to_be_disabled()

    # A wrong first tap, undone; tapping a numbered item again does nothing.
    _tap_order(phone, [0])
    expect(phone.get_by_test_id("ordering-badge-0")).to_have_text("1")
    phone.get_by_test_id("ordering-item-0").click()
    expect(phone.get_by_test_id("ordering-badge-0")).to_have_text("1")
    phone.get_by_test_id("ordering-undo").click()
    expect(phone.get_by_test_id("ordering-badge-0")).to_have_text("")

    _tap_order(phone, CORRECT)
    for position, d in enumerate(CORRECT, start=1):
        expect(phone.get_by_test_id(f"ordering-badge-{d}")).to_have_text(str(position))
    expect(submit).to_be_enabled()
    submit.click()
    expect(phone.get_by_text("Answer locked in!")).to_be_visible()
    assert phone_ctx.problems == []


def test_host_reveal_and_player_results(api, new_context):
    """§9.3 test 3: one exact phone, one with an item out of place."""
    course, game = api.course_and_game()
    api.question(game, _question())
    code = api.room(course, game)
    host_ctx = new_context(token=api.token)
    host = host_ctx.new_page()
    host.goto(url(f"/host/game/{code}/lobby"))
    phones = [_join(new_context(phone=True), code, name) for name in ("Ada", "Bo")]

    host.get_by_role("button", name="Start Game").click()
    for phone in phones:
        phone.wait_for_url(re.compile(r"/question$"))
    # While the question is open the host shows the items, but no statistics (O11).
    expect(host.get_by_test_id("ordering-host-items")).to_contain_text("Prophase")
    expect(host.get_by_test_id("ordering-host-correct-order")).to_have_count(0)

    for phone, order in zip(phones, (CORRECT, ONE_MOVED)):
        _tap_order(phone, order)
        phone.get_by_test_id("ordering-submit").click()
        expect(phone.get_by_text("Answer locked in!")).to_be_visible()

    host.get_by_role("button", name="Show Results").click()
    correct = host.get_by_test_id("ordering-host-correct-order").locator("li")
    expect(correct).to_have_count(len(ITEMS))
    for k, d in enumerate(CORRECT):
        expect(correct.nth(k)).to_contain_text(ITEMS[d][:20])
    expect(host.get_by_test_id("ordering-host-bucket-0")).to_contain_text("Perfect")
    expect(host.get_by_test_id("ordering-host-bucket-0")).to_contain_text("1")
    expect(host.get_by_test_id("ordering-host-bucket-1")).to_contain_text(
        "1 out of place"
    )
    expect(host.get_by_test_id("ordering-host-room-order")).to_contain_text("avg")

    ada, bo = phones
    expect(ada.get_by_test_id("ordering-result-label")).to_have_text("Perfect order!")
    expect(ada.get_by_text("+1,000 pts")).to_be_visible()
    expect(bo.get_by_test_id("ordering-result-label")).to_have_text(
        "1 item out of place"
    )
    expect(bo.get_by_text("+800 pts")).to_be_visible()
    marked = bo.get_by_test_id("ordering-your-order").locator("li[data-marked]")
    expect(marked).to_have_count(1)
    expect(marked).to_contain_text("Prophase")
    assert host_ctx.problems == []
