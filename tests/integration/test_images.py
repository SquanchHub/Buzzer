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
import json

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


# ── 9. Questions using images (§5, D3, D5) ──────────────────────────────────


def _mc(**overrides) -> dict:
    body = {
        "type": "multiple_choice",
        "grading_type": "ACCURACY",
        "prompt": "Which one?",
        "config": {"options": ["A", "B"]},
        "answer_data": {"answer_points": [10, 0]},
        "time_limit_seconds": 30,
        "points_value": 10,
    }
    body.update(overrides)
    return body


def _host_with_images(hapi, n: int = 2) -> tuple[str, int, int, list[int]]:
    """A HOST's empty game and `n` images in its course → (token, course, game, ids)."""
    course = hapi.course()
    _, token = hapi.host_of(course)
    game = hapi.host_game(token, course, questions=0)
    ids = [hapi.image(course, png((10 + i, 10)), token) for i in range(n)]
    return token, course, game, ids


def _err(r: httpx.Response) -> tuple[list, str]:
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "VALIDATION_ERROR"
    first = r.json()["detail"][0]
    return first["loc"], first["msg"]


def test_prompt_and_option_images_round_trip(hapi):
    token, _, game, (a, b) = _host_with_images(hapi)
    url = f"/host/games/{game}/questions"
    body = _mc(
        prompt_image_id=a,
        config={"options": ["", "Beta"], "optionImageIds": [b, None]},
    )
    q = hapi.ok("POST", url, token, json=body)
    assert q["prompt_image_id"] == a
    assert q["config"] == {"options": ["", "Beta"], "optionImageIds": [b, None]}
    [listed] = hapi.ok("GET", url, token)
    assert listed == q

    # Updates: swap the prompt image, then remove it with an explicit null.
    swapped = hapi.ok("PUT", f"{url}/{q['id']}", token, json={"prompt_image_id": b})
    assert swapped["prompt_image_id"] == b
    removed = hapi.ok("PUT", f"{url}/{q['id']}", token, json={"prompt_image_id": None})
    assert removed["prompt_image_id"] is None
    assert removed["config"]["optionImageIds"] == [b, None]  # untouched


def test_question_without_images_has_null_prompt_image(hapi):
    token, _, game, _ = _host_with_images(hapi, 0)
    q = hapi.ok("POST", f"/host/games/{game}/questions", token, json=_mc())
    assert q["prompt_image_id"] is None


def test_multi_select_option_images(hapi):
    token, _, game, (a, _) = _host_with_images(hapi)
    body = _mc(
        type="multi_select",
        config={"options": ["One", "Two"], "optionImageIds": [None, a]},
        answer_data={"answer_points": [5, 5]},
    )
    r = hapi.req("POST", f"/host/games/{game}/questions", token, json=body)
    assert r.status_code == 201, r.text


def test_unknown_image_ids_are_422_per_field(hapi):
    token, _, game, (a, _) = _host_with_images(hapi)
    url = f"/host/games/{game}/questions"
    loc, msg = _err(hapi.req("POST", url, token, json=_mc(prompt_image_id=999999999)))
    assert (loc, msg) == (["body", "prompt_image_id"], "Image 999999999 does not exist")
    body = _mc(config={"options": ["A", "B"], "optionImageIds": [a, 999999999]})
    loc, msg = _err(hapi.req("POST", url, token, json=body))
    assert loc == ["body", "config", "optionImageIds", 1]
    assert hapi.ok("GET", url, token) == []


def test_other_course_image_is_refused(hapi):
    token, course, game, _ = _host_with_images(hapi, 0)
    other = hapi.course()
    foreign = hapi.image(other, png((77, 7)))
    r = hapi.req(
        "POST",
        f"/host/games/{game}/questions",
        token,
        json=_mc(prompt_image_id=foreign),
    )
    loc, msg = _err(r)
    assert msg == f"Image {foreign} belongs to a different course"


def test_update_to_other_course_image_is_refused(hapi):
    token, _, game, _ = _host_with_images(hapi, 0)
    foreign = hapi.image(hapi.course(), png((78, 7)))
    url = f"/host/games/{game}/questions"
    q = hapi.ok("POST", url, token, json=_mc())
    _, msg = _err(
        hapi.req("PUT", f"{url}/{q['id']}", token, json={"prompt_image_id": foreign})
    )
    assert msg == f"Image {foreign} belongs to a different course"
    assert hapi.ok("GET", url, token)[0]["prompt_image_id"] is None


def test_unassigned_game_cannot_use_images(hapi):
    image = hapi.image(hapi.course(), png((79, 7)))
    out = mysql(
        "INSERT INTO games (title, description, max_players) "
        "VALUES ('T8 legacy', '', 150); SELECT LAST_INSERT_ID();"
    )
    game = hapi.track_game(int(out.split()[-1]))
    r = hapi.req(
        "POST", f"/admin/games/{game}/questions", json=_mc(prompt_image_id=image)
    )
    _, msg = _err(r)
    assert msg == "Assign the game to a course before adding images"


@pytest.mark.parametrize(
    "body, fragment",
    [
        (
            _mc(config={"options": ["A", "B"], "optionImageIds": [None]}),
            "optionImageIds must be a list the same length as options",
        ),
        (
            _mc(config={"options": ["  ", "B"], "optionImageIds": [None, None]}),
            "option 1 needs text or an image",
        ),
        (
            _mc(config={"options": ["A", "B"], "optionImageIds": [True, None]}),
            "optionImageIds[0] must be a positive integer or null",
        ),
        (
            _mc(
                type="true_false",
                config={"optionImageIds": [None, None]},
                answer_data={"answer_points": {"true": 1, "false": 0}},
            ),
            "optionImageIds is only allowed on multiple_choice and multi_select",
        ),
        (_mc(prompt_image_id=True), "Input should be a valid integer"),
        (_mc(prompt_image_id=0), "Input should be greater than 0"),
    ],
    ids=["length", "blank-option", "bool-id", "true-false", "bool-prompt", "zero"],
)
def test_image_field_shape_errors(hapi, body, fragment):
    token, _, game, _ = _host_with_images(hapi, 0)
    _, msg = _err(hapi.req("POST", f"/host/games/{game}/questions", token, json=body))
    assert fragment in msg


@pytest.mark.parametrize(
    "question",
    [
        _mc(prompt_image_id=5),
        _mc(config={"options": ["A", "B"], "optionImageIds": [5, None]}),
    ],
    ids=["prompt", "options"],
)
def test_v1_bundle_with_image_ids_is_rejected(hapi, question):
    course = hapi.course()
    _, token = hapi.host_of(course)
    bundle = {
        "format": "buzzer/game",
        "version": 1,
        "game": {"title": "v1 with image ids"},
        "questions": [_mc(), question],
    }
    r = hapi.req(
        "POST",
        "/host/games/import",
        token,
        files={"file": ("g.json", json.dumps(bundle).encode())},
        data={"course_id": str(course)},
    )
    _, msg = _err(r)
    assert msg == (
        "Question 2: image IDs can't be imported; export the game again to get a "
        "version 2 file"
    )
    assert hapi.ok("GET", f"/host/courses/{course}/games", token) == []


# ── 7. Listing a course's images ────────────────────────────────────────────


def _list(hapi, course: int, token: str | None = None, **params) -> httpx.Response:
    return hapi.req("GET", "/images", token, params={"course_id": course, **params})


def test_list_counts_references_and_filters_unused(hapi):
    token, course, game, (used, unused) = _host_with_images(hapi)
    hapi.ok(
        "POST", f"/host/games/{game}/questions", token, json=_mc(prompt_image_id=used)
    )
    page = hapi.ok("GET", "/images", token, params={"course_id": course})
    assert page["total"] == 2 and page["page"] == 1 and page["page_size"] == 24
    by_id = {i["id"]: i for i in page["items"]}
    assert by_id[used]["reference_count"] == 1
    assert by_id[unused]["reference_count"] == 0
    assert by_id[used]["uploaded_by_name"]  # the host's display name
    assert [i["id"] for i in page["items"]] == [unused, used]  # newest first

    only_unused = _list(hapi, course, token, unused="true").json()
    assert [i["id"] for i in only_unused["items"]] == [unused]
    assert only_unused["total"] == 1


def test_list_pages_24_at_a_time(hapi):
    course = hapi.course()
    ids = [hapi.image(course, png((5 + i, 5))) for i in range(26)]
    first = _list(hapi, course).json()
    second = _list(hapi, course, page=2).json()
    assert first["total"] == second["total"] == 26
    assert len(first["items"]) == 24 and len(second["items"]) == 2
    listed = [i["id"] for i in first["items"] + second["items"]]
    assert sorted(listed) == sorted(ids)


def test_list_unknown_course(hapi):
    _, user = hapi.user()
    assert _list(hapi, 999999999).status_code == 404  # admin
    assert _list(hapi, 999999999, user).status_code == 403  # T4: hosts get 403


def test_reused_upload_reports_its_reference_count(hapi):
    token, course, game, _ = _host_with_images(hapi, 0)
    data = png((40, 41))
    image = hapi.image(course, data, token)
    hapi.ok(
        "POST", f"/host/games/{game}/questions", token, json=_mc(prompt_image_id=image)
    )
    again = hapi.upload(course, data, token)
    assert again.status_code == 200
    assert again.json()["reference_count"] == 1


# ── 6 (continued). Who may list and delete ──────────────────────────────────


def test_list_and_delete_refused_for_non_hosts(hapi):
    course, other = hapi.course(), hapi.course()
    image = hapi.image(course, png((61, 6)))
    player_id, player = hapi.user()
    hapi.grant_course(player_id, course, role="PLAYER")
    _, other_host = hapi.host_of(other)
    room_course = hapi.course()
    _, host = hapi.host_of(room_course)
    code, _ = hapi.room(host, room_course, hapi.host_game(host, room_course))
    guest = hapi.guest(code)
    for token in (player, other_host, guest):
        assert _list(hapi, course, token).status_code == 403
        assert hapi.req("DELETE", f"/images/{image}", token).status_code == 403
    assert hapi.req("GET", f"/images/{image}").status_code == 200  # still there


def test_delete_unknown_image_is_404(hapi):
    assert hapi.req("DELETE", "/images/999999999").status_code == 404


# ── 8. Deleting an image that is in use ─────────────────────────────────────


def _hotspot(image_id: int) -> dict:
    return {
        "type": "hotspot",
        "grading_type": "COMPLETENESS",
        "prompt": "Tap anywhere",
        "config": {"imageId": image_id, "aspectRatio": 1.1},
        "answer_data": {},
        "time_limit_seconds": 30,
        "points_value": 10,
    }


@pytest.mark.parametrize("kind", ["prompt", "option", "hotspot"])
def test_delete_refused_while_used(hapi, kind):
    token, _, game, (image, _) = _host_with_images(hapi)
    body = {
        "prompt": _mc(prompt_image_id=image),
        "option": _mc(config={"options": ["", "B"], "optionImageIds": [image, None]}),
        "hotspot": _hotspot(image),
    }[kind]
    url = f"/host/games/{game}/questions"
    q = hapi.ok("POST", url, token, json=body)

    r = hapi.req("DELETE", f"/images/{image}", token)
    assert r.status_code == 409, r.text
    assert r.json()["message"] == "Image is used by 1 question"
    assert hapi.req("GET", f"/images/{image}", token).status_code == 200

    hapi.ok("DELETE", f"{url}/{q['id']}", token)
    assert hapi.req("DELETE", f"/images/{image}", token).status_code == 204
    assert hapi.req("GET", f"/images/{image}", token).status_code == 404


def test_delete_counts_every_using_question(hapi):
    token, _, game, (image, _) = _host_with_images(hapi)
    url = f"/host/games/{game}/questions"
    hapi.ok("POST", url, token, json=_mc(prompt_image_id=image))
    hapi.ok("POST", url, token, json=_hotspot(image))
    r = hapi.req("DELETE", f"/images/{image}", token)
    assert r.json()["message"] == "Image is used by 2 questions"


# ── 19. The forward lookup and the reverse SQL agree ────────────────────────


def test_reference_count_and_delete_check_agree(hapi):
    """The list's reference_count comes from question_image_ids (Python); the delete 409
    comes from find_references (SQL). They must agree for every type, including null
    option entries and integers in config that are not image references."""
    token, course, game, ids = _host_with_images(hapi, 5)
    a, b, c, d, decoy = ids
    url = f"/host/games/{game}/questions"
    for body in [
        _mc(
            config={"options": ["", "x", "y"], "optionImageIds": [a, None, b]},
            answer_data={"answer_points": [10, 0, 0]},
        ),
        _mc(
            type="multi_select",
            config={"options": ["p", ""], "optionImageIds": [None, a]},
            answer_data={"answer_points": [1, 1]},
        ),
        _hotspot(c),
        {
            "type": "true_false",
            "grading_type": "COMPLETENESS",
            "prompt": "Yes?",
            "prompt_image_id": d,
            "config": {
                "imageId": decoy
            },  # not a reference: true_false has no image config
            "time_limit_seconds": 30,
            "points_value": 1,
        },
        {
            "type": "fill_in_the_blank",
            "grading_type": "COMPLETENESS",
            "prompt": "Type it",
            "config": {"maxLength": decoy},
            "time_limit_seconds": 30,
            "points_value": 1,
        },
    ]:
        hapi.ok("POST", url, token, json=body)

    counts = {
        i["id"]: i["reference_count"]
        for i in _list(hapi, course, token).json()["items"]
    }
    assert counts == {a: 2, b: 1, c: 1, d: 1, decoy: 0}
    for image, n in counts.items():
        r = hapi.req("DELETE", f"/images/{image}", token)
        if n:
            assert r.status_code == 409
            word = "question" if n == 1 else "questions"
            assert r.json()["message"] == f"Image is used by {n} {word}"
        else:
            assert r.status_code == 204
