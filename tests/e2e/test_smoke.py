"""Harness smoke test: the built player app loads through nginx."""

from __future__ import annotations

from playwright.sync_api import expect

from .conftest import url


def test_player_join_page_loads(new_context):
    page = new_context(phone=True).new_page()
    page.goto(url("/player/join"))
    expect(page.get_by_text("Enter your room code to join")).to_be_visible()
