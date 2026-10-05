"""Image bytes for the T8 tests (docs/plans/t8-image-support.md §7), built with Pillow."""

from __future__ import annotations

import io
import os

from PIL import Image

MAX_BYTES = 2 * 1024 * 1024


def image_bytes(
    fmt: str = "PNG", size: tuple[int, int] = (40, 20), color=(200, 30, 30), **save
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt, **save)
    return buf.getvalue()


def png(size: tuple[int, int] = (40, 20), color=(200, 30, 30)) -> bytes:
    return image_bytes("PNG", size, color)


def noise_png(width: int, height: int) -> bytes:
    """Random pixels: PNG can't compress them, so the file is about width × height × 3 bytes."""
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def rotated_jpeg_with_gps() -> bytes:
    """A 40 × 20 JPEG tagged "rotate 90°" (EXIF orientation 6) with a GPS block, as a phone
    portrait photo is stored."""
    img = Image.new("RGB", (40, 20), (10, 120, 200))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to display
    exif[0x8825] = {
        1: "N",
        2: (43.0, 4.0, 30.0),
        3: "W",
        4: (89.0, 24.0, 0.0),
    }  # GPSInfo
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))
