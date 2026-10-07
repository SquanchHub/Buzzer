"""
T9 theme token layer — static checks (docs/plans/t9-theming.md §8.1, D9).

Standard library only (no `app` import), so CI runs it without backend dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APPS = ("host", "player", "admin")
FRONTEND = ROOT / "frontend"

TOKENS = (
    "canvas surface sunken ink ink-muted ink-soft line line-soft shadow "
    "accent accent-ink success success-ink danger danger-ink warning warning-ink "
    "focus on-fill qr scrim opt-1 opt-2 opt-3 opt-4 opt-5 opt-6 opt-7 opt-8"
).split()
THEMES = ("light", "dark")

RAW_UTILITY = re.compile(
    r"\b(?:bg|text|border|ring|ring-offset|from|via|to|fill|stroke|divide|placeholder|"
    r"outline|accent|shadow|decoration|caret)-(?:slate|gray|zinc|neutral|stone|red|orange|"
    r"amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|"
    r"pink|rose|white|black)(?:-\d+)?\b"
)
HEX_LITERAL = re.compile(r"""['"`(\s:,]#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b""")
COLOUR_FN = re.compile(r"\b(?:rgba?|hsla?)\(")
DYNAMIC_CLASS = re.compile(r"\b(?:bg|text|border|ring|from|to|fill|stroke)-\$\{")


def _sources():
    for app in APPS:
        for path in sorted((FRONTEND / app / "src").rglob("*")):
            if path.suffix in (".ts", ".tsx"):
                yield path


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _css(app: str) -> str:
    return (FRONTEND / app / "src" / "index.css").read_text()


def _token_block(app: str) -> str:
    m = re.search(r"/\* tokens:start \*/(.*?)/\* tokens:end \*/", _css(app), re.S)
    assert m, f"{app}: no /* tokens:start */ … /* tokens:end */ block in index.css"
    return m.group(1)


def _theme_values(app: str) -> dict[str, dict[str, tuple[int, int, int]]]:
    block = _token_block(app)
    rules = {
        "light": re.search(
            r':root,\s*\[data-theme="light"\]\s*\{(.*?)\}', block, re.S
        ),
        "dark": re.search(r'\[data-theme="dark"\]\s*\{(.*?)\}', block, re.S),
    }
    out = {}
    for theme, m in rules.items():
        assert m, f"{app}: no {theme} rule in the token block"
        out[theme] = {
            name: tuple(int(c) for c in value.split())
            for name, value in re.findall(r"--([\w-]+):\s*([^;]+);", m.group(1))
            if re.fullmatch(r"\d{1,3} \d{1,3} \d{1,3}", value.strip())
        }
    return out


def _lum(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, alpha: float, bg):
    return tuple(round(alpha * f + (1 - alpha) * b) for f, b in zip(fg, bg))


# ── §6.2 pairs ────────────────────────────────────────────────────────────────

TEXT = ["ink", "ink-muted", "ink-soft", "accent-ink", "success-ink", "danger-ink", "warning-ink"]
BACKDROPS = ["canvas", "surface", "sunken"]
FILLS = ["accent", "success", "danger", "warning"] + [f"opt-{i}" for i in range(1, 9)]
TINTS = [("accent-ink", "accent", 0.15), ("success-ink", "success", 0.15),
         ("danger-ink", "danger", 0.15), ("warning-ink", "warning", 0.20)]

TEXT_PAIRS = (
    [(fg, bg, None) for fg in TEXT for bg in BACKDROPS]
    + [("on-fill", fill, None) for fill in FILLS]
    + [(fg, (fill, a, bg), None) for fg, fill, a in TINTS for bg in ("surface", "canvas")]
    + [("canvas", "ink", None), (("canvas", 0.7, "ink"), "ink", None)]
)
UI_PAIRS = [("focus", bg) for bg in BACKDROPS] + [
    ("canvas", "ink"),
    ("line", "canvas"),
    ("ink", "canvas"),
]


def _colour(values, spec):
    if isinstance(spec, tuple):
        top, alpha, under = spec
        return blend(values[top], alpha, values[under])
    return values[spec]


def _name(spec) -> str:
    return spec if isinstance(spec, str) else f"{spec[0]}/{int(spec[1] * 100)} over {spec[2]}"


# ── tests ─────────────────────────────────────────────────────────────────────


def test_no_raw_palette_utilities():
    hits = [
        f"{_rel(p)}:{n}: {m.group(0)}"
        for p in _sources()
        for n, line in enumerate(p.read_text().splitlines(), 1)
        for m in RAW_UTILITY.finditer(line)
    ]
    assert not hits, f"{len(hits)} raw palette utilities:\n" + "\n".join(hits[:60])


def test_no_colour_literals_in_components():
    hits = []
    for p in _sources():
        for n, line in enumerate(p.read_text().splitlines(), 1):
            for rx in (HEX_LITERAL, DYNAMIC_CLASS):
                hits += [f"{_rel(p)}:{n}: {m.group(0).strip()}" for m in rx.finditer(line)]
            if COLOUR_FN.search(line) and not (
                p.name == "theme.ts" and "rgb(${" in line
            ):
                hits.append(f"{_rel(p)}:{n}: {line.strip()[:80]}")
    assert not hits, f"{len(hits)} colour literals:\n" + "\n".join(hits[:60])


@pytest.mark.parametrize("app", APPS)
def test_index_css_colours_only_in_token_block(app):
    css = re.sub(r"/\* tokens:start \*/.*?/\* tokens:end \*/", "", _css(app), flags=re.S)
    assert "tokens:start" in _css(app), f"{app}: no token block"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), f"{app}: hex outside token block"
    for m in re.finditer(r"\b(?:rgba?|hsla?)\(", css):
        assert css[m.end():].startswith("var(--"), (
            f"{app}: colour function without a token: {css[m.start():m.start() + 40]}"
        )


def test_token_blocks_identical_and_complete():
    blocks = {app: _token_block(app) for app in APPS}
    assert blocks["host"] == blocks["player"] == blocks["admin"], (
        "token blocks differ between apps"
    )
    values = _theme_values("host")
    for theme in THEMES:
        missing = [t for t in TOKENS if t not in values[theme]]
        assert not missing, f"{theme}: missing or not 'R G B': {missing}"
        for name, rgb in values[theme].items():
            assert all(0 <= c <= 255 for c in rgb), (theme, name, rgb)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize(
    "fg,bg", [(fg, bg) for fg, bg, _ in TEXT_PAIRS], ids=lambda s: _name(s)
)
def test_text_contrast_aa(theme, fg, bg):
    values = _theme_values("host")[theme]
    ratio = contrast(_colour(values, fg), _colour(values, bg))
    assert ratio >= 4.5, f"{theme}: {_name(fg)} on {_name(bg)} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("fg,bg", UI_PAIRS, ids=lambda s: s)
def test_ui_contrast(theme, fg, bg):
    values = _theme_values("host")[theme]
    ratio = contrast(values[fg], values[bg])
    assert ratio >= 3, f"{theme}: {fg} against {bg} is {ratio:.2f}:1"


@pytest.mark.parametrize("app", APPS)
def test_tailwind_palette_replaced(app):
    cfg = (FRONTEND / app / "tailwind.config.ts").read_text()
    assert re.search(r"theme:\s*\{\s*colors\s*:", cfg), (
        f"{app}: theme.colors must be replaced at the top of `theme`, not extended"
    )
    extend = re.search(r"extend:\s*\{(.*)", cfg, re.S)
    assert not (extend and re.search(r"^\s*colors\s*:", extend.group(1), re.M)), (
        f"{app}: colors inside extend"
    )


@pytest.mark.parametrize("app", APPS)
def test_theme_bootstrap_in_index_html(app):
    html = (FRONTEND / app / "index.html").read_text()
    head = html.split("</head>")[0]
    assert re.search(r"<script>.*buzzer-theme.*</script>", head, re.S), (
        f"{app}: no inline theme script in <head>"
    )
    assert "prefers-color-scheme: dark" in head
    assert re.search(r'<meta name="color-scheme" content="light dark"', head)
