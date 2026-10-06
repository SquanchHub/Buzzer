"""
Render the two sample-game hotspot images (docs/plans/t7-hotspot.md §8; see README.md here).

    python sample_games/images/render_images.py path/to/ne_110m_admin_0_countries.geojson

- world_map.png: unlabelled country outlines from Natural Earth 1:110m Admin 0 (public
  domain), plain equirectangular projection over exactly -180..180 longitude and -90..90
  latitude, no margins, so a point maps to x = (lon + 180) / 360, y = (90 - lat) / 180.
- savanna.png: a self-made savanna scene (elephant, giraffe, zebra) drawn here with
  Pillow; GIRAFFE is the hotspot target (its centre, as fractions of the image).

Both are drawn at 2x and downsampled (antialiasing), then saved as palette PNGs.
Requires Pillow.
"""

import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1200, 600  # both images are 2:1
S = 2  # supersampling factor

# Savanna target: the giraffe's centre (fractions of width and height).
GIRAFFE = (0.545, 0.52)  # the neck base; see README.md for the rings


def _save(img: Image.Image, name: str, colors: int) -> None:
    img = img.resize((W, H), Image.LANCZOS)
    img = img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    path = os.path.join(HERE, name)
    img.save(path, optimize=True)
    print(f"{name}: {W}x{H}, {os.path.getsize(path) / 1024:.0f} KB")


def world_map(geojson_path: str) -> None:
    ocean, land, border = (168, 208, 230), (242, 239, 230), (110, 110, 110)
    img = Image.new("RGB", (W * S, H * S), ocean)
    draw = ImageDraw.Draw(img)

    def xy(ring):
        return [
            ((lon + 180) / 360 * W * S, (90 - lat) / 180 * H * S) for lon, lat in ring
        ]

    for feature in json.load(open(geojson_path))["features"]:
        geom = feature["geometry"]
        polygons = (
            geom["coordinates"]
            if geom["type"] == "MultiPolygon"
            else [geom["coordinates"]]
        )
        for polygon in polygons:
            exterior, *holes = polygon
            draw.polygon(xy(exterior), fill=land, outline=border, width=S)
            for hole in holes:
                draw.polygon(xy(hole), fill=ocean, outline=border, width=S)
    _save(img, "world_map.png", colors=16)


def savanna() -> None:
    img = Image.new("RGB", (W * S, H * S))
    draw = ImageDraw.Draw(img)

    def p(x, y):  # fractions of the image -> supersampled pixels
        return (x * W * S, y * H * S)

    def box(x0, y0, x1, y1):
        return [p(x0, y0), p(x1, y1)]

    horizon = 0.62
    for row in range(int(horizon * H * S)):  # sky: light blue fading to pale yellow
        t = row / (horizon * H * S)
        c = tuple(
            int(a + (b - a) * t) for a, b in zip((120, 180, 230), (250, 230, 170))
        )
        draw.line([(0, row), (W * S, row)], fill=c)
    draw.rectangle(box(0, horizon, 1, 1), fill=(214, 178, 96))  # dry grass
    draw.ellipse(box(0.86, 0.06, 0.94, 0.22), fill=(255, 214, 90))  # sun

    def acacia(x, h):
        draw.line(
            [p(x, horizon + 0.02), p(x, horizon - h)], fill=(90, 60, 30), width=10 * S
        )
        draw.ellipse(
            box(x - 0.08, horizon - h - 0.07, x + 0.08, horizon - h + 0.03),
            fill=(80, 120, 50),
        )

    acacia(0.30, 0.25)
    acacia(0.97, 0.18)

    # Elephant (left)
    grey = (120, 120, 125)
    draw.ellipse(box(0.08, 0.50, 0.30, 0.74), fill=grey)  # body
    for lx in (0.11, 0.16, 0.22, 0.26):
        draw.rectangle(box(lx, 0.68, lx + 0.035, 0.86), fill=grey)  # legs
    draw.ellipse(box(0.02, 0.46, 0.13, 0.66), fill=grey)  # head
    draw.ellipse(box(0.06, 0.47, 0.13, 0.62), fill=(105, 105, 110))  # ear
    draw.line([p(0.035, 0.60), p(0.03, 0.80)], fill=grey, width=14 * S)  # trunk
    draw.line(
        [p(0.05, 0.62), p(0.035, 0.68)], fill=(245, 240, 225), width=5 * S
    )  # tusk

    # Giraffe (centre): body, legs, neck, head, ossicones, spots; everything is offset by G
    # so the target (GIRAFFE) and the drawing move together.
    g = -0.08
    tan, leg, spot = (232, 176, 72), (176, 118, 40), (110, 60, 20)

    def gp(x, y):
        return p(x + g, y)

    draw.ellipse([gp(0.53, 0.52), gp(0.66, 0.64)], fill=tan)  # body
    for lx in (0.545, 0.57, 0.615, 0.64):
        draw.line([gp(lx, 0.60), gp(lx, 0.82)], fill=leg, width=9 * S)  # legs
    draw.polygon(
        [gp(0.615, 0.56), gp(0.645, 0.55), gp(0.665, 0.24), gp(0.645, 0.23)], fill=tan
    )  # neck
    draw.ellipse([gp(0.640, 0.17), gp(0.700, 0.27)], fill=tan)  # head
    for ox in (0.652, 0.672):
        draw.line([gp(ox, 0.18), gp(ox, 0.13)], fill=spot, width=4 * S)  # ossicones
    for sx, sy in (
        (0.56, 0.56),
        (0.595, 0.59),
        (0.625, 0.555),
        (0.585, 0.545),
        (0.635, 0.45),
        (0.645, 0.36),
        (0.652, 0.29),
        (0.61, 0.61),
    ):
        draw.ellipse(
            [gp(sx - 0.009, sy - 0.016), gp(sx + 0.009, sy + 0.016)], fill=spot
        )

    # Zebra (right)
    white, black = (240, 240, 235), (30, 30, 30)
    draw.ellipse(box(0.74, 0.56, 0.90, 0.70), fill=white)  # body
    for lx in (0.76, 0.79, 0.85, 0.88):
        draw.rectangle(box(lx, 0.66, lx + 0.018, 0.85), fill=white)  # legs
    draw.polygon(
        [p(0.88, 0.60), p(0.92, 0.48), p(0.95, 0.50), p(0.91, 0.62)], fill=white
    )  # neck
    draw.ellipse(box(0.915, 0.44, 0.975, 0.52), fill=white)  # head
    for i in range(9):
        x = 0.755 + i * 0.017
        draw.line([p(x, 0.57), p(x + 0.01, 0.69)], fill=black, width=5 * S)  # stripes
    for i in range(4):
        y = 0.70 + i * 0.035
        for lx in (0.76, 0.79, 0.85, 0.88):
            draw.line([p(lx, y), p(lx + 0.018, y)], fill=black, width=3 * S)

    # Grass tufts in the foreground
    for i in range(40):
        x = (i * 0.0271 + 0.013) % 1
        y = 0.86 + (i * 37 % 11) / 100
        draw.line([p(x, y), p(x + 0.006, y - 0.03)], fill=(170, 135, 60), width=3 * S)
    _save(img, "savanna.png", colors=128)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    world_map(sys.argv[1])
    savanna()
    gx, gy = GIRAFFE
    print(f"giraffe target: x = {gx}, y = {gy}")
    print(
        f"Cairo target:   x = {(31.24 + 180) / 360:.4f}, y = {(90 - 30.04) / 180:.4f}"
    )
