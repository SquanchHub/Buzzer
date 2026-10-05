# ruff: noqa: F811  (pytest fixtures are parameters named like the imported fixture)
"""
T8 — image upload, fetch and management (docs/plans/t8-image-support.md).

Test numbers refer to the design doc's §7. Behaviour under test:

- Uploads are judged by their bytes (PNG, JPEG, WebP only), capped at 2 MB and
  4096 px per side, and re-saved without metadata (rotation applied) when they
  carry any (D2). Identical bytes in one course reuse the existing row (D2).
- Images belong to a course: only an admin or a HOST of that course can upload
  (D3, D4). Any logged-in token, guests included, can fetch the bytes, which are
  served with an immutable private cache header (C3).
"""

from __future__ import annotations

import asyncio
import hashlib

import httpx
import pytest

from .host_helpers import hapi, mysql  # noqa: F401 (fixture)
from .image_helpers import (
    MAX_BYTES,
    image_bytes,
    noise_png,
    opened,
    png,
    rotated_jpeg_with_gps,
)

CACHE = "private, max-age=31536000, immutable"
NGINX = "http://localhost:8080"


def _detail_msg(r: httpx.Response) -> str:
    return r.json()["detail"][0]["msg"]


# ── 1. Valid uploads ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "fmt, ctype", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_upload_and_fetch_identical_bytes(hapi, fmt, ctype):
    course = hapi.course()
    _, host = hapi.host_of(course)
    data = image_bytes(fmt, (64, 32))
    r = hapi.upload(course, data, host, name="ignored-name.gif")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["course_id"] == course
    assert body["content_type"] == ctype
    assert (body["width"], body["height"]) == (64, 32)
    assert body["byte_size"] == len(data)

    got = hapi.req("GET", f"/images/{body['id']}", host)
    assert got.status_code == 200
    assert got.content == data
    assert got.headers["content-type"] == ctype


def test_admin_can_upload_into_any_course(hapi):
    course = hapi.course()
    r = hapi.upload(course, png())
    assert r.status_code == 201, r.text


# ── 2. Rejections ───────────────────────────────────────────────────────────

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.mark.parametrize(
    "data, msg",
    [
        (b"just some text, not an image", "File is not a PNG, JPEG or WebP image"),
        (SVG, "File is not a PNG, JPEG or WebP image"),
        (image_bytes("GIF"), "File is not a PNG, JPEG or WebP image"),
        (b"", "File is empty"),
        (png()[:60], "Image file is damaged or incomplete"),
        (
            image_bytes("PNG", (5000, 10)),
            "Image is 5000 × 10 px; the limit is 4096 px per side",
        ),
    ],
    ids=["text", "svg", "gif", "empty", "truncated", "too-wide"],
)
def test_upload_rejections(hapi, data, msg):
    course = hapi.course()
    before = mysql(f"SELECT COUNT(*) FROM images WHERE course_id = {course}").strip()
    r = hapi.upload(course, data)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "VALIDATION_ERROR"
    assert _detail_msg(r) == msg
    after = mysql(f"SELECT COUNT(*) FROM images WHERE course_id = {course}").strip()
    assert before == after == "0"


def test_upload_just_over_the_size_limit(hapi):
    course = hapi.course()
    data = noise_png(840, 840)  # ~2.1 MB of incompressible pixels
    assert len(data) > MAX_BYTES
    r = hapi.upload(course, data)
    assert r.status_code == 422, r.text
    assert _detail_msg(r).endswith("the limit is 2 MB")


# ── 3. Metadata stripped, rotation applied ──────────────────────────────────


def test_rotated_jpeg_is_stored_upright_without_exif(hapi):
    course = hapi.course()
    r = hapi.upload(course, rotated_jpeg_with_gps())
    assert r.status_code == 201, r.text
    assert (r.json()["width"], r.json()["height"]) == (20, 40)  # rotated 90°
    stored = hapi.req("GET", f"/images/{r.json()['id']}").content
    img = opened(stored)
    assert img.size == (20, 40)
    assert len(img.getexif()) == 0  # no orientation, no GPS


def test_image_without_metadata_is_stored_byte_for_byte(hapi):
    course = hapi.course()
    data = image_bytes("JPEG", (30, 30), quality=75)
    iid = hapi.image(course, data)
    assert hapi.req("GET", f"/images/{iid}").content == data


# ── 4. Duplicates ───────────────────────────────────────────────────────────


def test_identical_bytes_reuse_the_course_row(hapi):
    course, other = hapi.course(), hapi.course()
    data = png((33, 17), (1, 2, 3))
    first = hapi.upload(course, data)
    again = hapi.upload(course, data)
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]

    elsewhere = hapi.upload(other, data)
    assert elsewhere.status_code == 201
    assert elsewhere.json()["id"] != first.json()["id"]
    sha = hashlib.sha256(data).hexdigest()
    assert mysql(f"SELECT COUNT(*) FROM images WHERE sha256 = '{sha}'").strip() == "2"


# ── 5. Fetching ─────────────────────────────────────────────────────────────


def test_guest_can_fetch_with_cache_headers(hapi):
    course = hapi.course()
    _, host = hapi.host_of(course)
    iid = hapi.image(course, png(), host)
    game = hapi.host_game(host, course)
    code, _ = hapi.room(host, course, game)
    guest = hapi.guest(code)

    r = hapi.req("GET", f"/images/{iid}", guest)
    assert r.status_code == 200
    assert r.headers["cache-control"] == CACHE
    assert r.headers["x-content-type-options"] == "nosniff"


def test_unknown_image_is_404_without_cache_header(hapi):
    r = hapi.req("GET", "/images/999999999")
    assert r.status_code == 404
    assert (
        "cache-control" not in r.headers
        or "immutable" not in r.headers["cache-control"]
    )


def test_fetch_without_token_is_401(hapi, base_url):
    iid = hapi.image(hapi.course(), png())
    r = httpx.get(f"{base_url}/api/images/{iid}")
    assert r.status_code == 401


# ── 6. Who may upload ───────────────────────────────────────────────────────


def test_upload_refused_for_non_hosts(hapi):
    course, other = hapi.course(), hapi.course()
    player_id, player = hapi.user()
    hapi.grant_course(player_id, course, role="PLAYER")
    _, other_host = hapi.host_of(other)
    host_game_course = hapi.course()
    _, host = hapi.host_of(host_game_course)
    code, _ = hapi.room(host, host_game_course, hapi.host_game(host, host_game_course))
    guest = hapi.guest(code)

    for token in (player, other_host, guest):
        r = hapi.upload(course, png(), token)
        assert r.status_code == 403, r.text


def test_upload_to_unknown_course(hapi):
    _, user = hapi.user()
    assert hapi.upload(999999999, png()).status_code == 404  # admin
    assert hapi.upload(999999999, png(), user).status_code == 403  # T4: hosts get 403


# ── 22. Concurrent identical uploads ────────────────────────────────────────


def test_concurrent_identical_uploads_make_one_row(hapi, base_url, admin_token):
    course = hapi.course()
    data = png((51, 13), (9, 9, 9))

    async def go():
        async with httpx.AsyncClient(timeout=20) as c:
            return await asyncio.gather(
                *(
                    c.post(
                        f"{base_url}/api/images",
                        headers={"Authorization": f"Bearer {admin_token}"},
                        files={"file": ("x.png", data, "image/png")},
                        data={"course_id": str(course)},
                    )
                    for _ in range(6)
                )
            )

    results = asyncio.run(go())
    ids = {r.json()["id"] for r in results if r.status_code in (200, 201)}
    hapi._images.extend(ids)  # before asserting, so a failure still cleans up
    assert all(r.status_code in (200, 201) for r in results), [r.text for r in results]
    assert len(ids) == 1
    assert sum(r.status_code == 201 for r in results) == 1


# ── Through nginx (C8: the proxy must allow a full-size image) ─────────────


def test_large_upload_passes_nginx(hapi, admin_token):
    try:
        httpx.get(f"{NGINX}/api/health", timeout=3)
    except httpx.HTTPError:
        pytest.skip("nginx not running on :8080")
    course = hapi.course()
    data = noise_png(800, 800)  # ~1.9 MB: over nginx's 1 MB default, under 2 MB
    assert 1024 * 1024 < len(data) <= MAX_BYTES
    r = httpx.post(
        f"{NGINX}/api/images",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("big.png", data, "image/png")},
        data={"course_id": str(course)},
        timeout=30,
    )
    assert r.status_code == 201, r.text
    hapi._images.append(r.json()["id"])
