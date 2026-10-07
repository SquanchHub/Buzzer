# T9 — Look-and-feel and theming: "Riso Press" (light *Paper*, dark *Night*)

Owner: Vincent (vzhou2). Branch: `feat/t9-theming` (from `main` at `60ee669`).
Status: design. Committed before any implementation code (T3 step 4).

## 1. Problem

All three apps (`frontend/host`, `frontend/player`, `frontend/admin`) hardcode one dark slate
palette. There are 1,149 raw Tailwind palette utilities (`text-slate-400`, `bg-indigo-600`, …),
about 30 hex literals in canvas code, and a hex `body` background in each `index.css`. The look
is a generic Kahoot clone: navy background, indigo buttons, and red/blue/yellow/green answer
tiles with white text.

T9 asks for the following (instructions.md T9, rubric R9, 9 points):

- a semantic token layer that components consume, with raw palette utilities removed outside the
  token definitions;
- complete light and dark themes in all three apps;
- a visible toggle per app that follows `prefers-color-scheme` on the first visit and persists;
- WCAG 2.1 AA text contrast (4.5:1) and visible focus states;
- context fit: the player is thumb-friendly, the host is readable from the back of a classroom,
  and the admin is dense but scannable;
- before/after screenshots in `docs/ui/`;
- the T7/T8 surfaces themed as well (question editors, hotspot canvas, ordering, image
  management).

The user also wants the design to be **bold and distinctive**, so that it doesn't look like
every other party-quiz clone, while staying intuitive.

## 2. The design idea

**Riso Press** borrows from risograph-printed zines and game-show tickets.

**Paper (light theme).** Warm newsprint background, near-black ink outlines, and **hard offset
shadows** with no blur.

**Night (dark theme).** The same inks on a deep violet-black, with cream outlines and a violet
"extrusion" shadow.

Seven signature elements give it its identity. Each one also has a job:

| # | Element | Where | Why it isn't just decoration |
|---|---|---|---|
| S1 | **Ink outline + hard shadow, press-down.** Interactive fills have a 2px `line` border and a hard `shadow`. On `:active` they move by the shadow offset and the shadow drops to 0, like a physical buzzer. | All buttons, answer tiles, cards (lighter in admin) | Makes the affordance obvious and gives touch feedback without animation libraries |
| S2 | **Riso option inks.** Eight flat, fluorescent answer colours with **ink-coloured (dark) text** and a faint halftone dot texture. | Player answer tiles; host option tiles and result bars use the *same* ink per option letter | Dark text on bright ink keeps every tile ≥ 4.5:1 (white on yellow does not today). Host and phone colours match, so "the pink one" means the same thing on both. |
| S3 | **Rubber-stamp verdicts.** A rotated, double-bordered stamp: `CORRECT`, `PARTIAL`, `NOT QUITE`, `LOCKED IN`. | Player feedback/results; host results mark the correct answer with a small `✓ ANSWER` stamp | A legible verdict that doesn't rely on colour alone (it has a word) |
| S4 | **Ticket room code.** The room code is printed on a ticket stub with notched sides and a perforation line. | Host lobby (giant), player lobby, host corner badge | Easy to read from the back of the room, and memorable |
| S5 | **Type pairing.** *Bricolage Grotesque* (variable, 800 weight, tight tracking) for display and body. *JetBrains Mono* for codes, timers, scores and uppercase eyebrow labels. Both are self-hosted. | Everywhere | Mono numerals don't jitter while a timer counts down, and the code is unambiguous (0/O) |
| S6 | **Paper grain.** A very faint SVG noise on `body`. Light theme ≤ 5% opacity, dark ≤ 4%. It is never placed between text and its background tile. | `body` background only | Gives the print feel. Contrast is computed on the flat colours, and the grain changes them by less than 1%. |
| S7 | **"Paper / Night" toggle.** A two-position pill switch that reads `PAPER ☀` / `NIGHT ☾`. | One per app (§5.4) | Visible and labelled, not just an icon |

Context fit:

- **Player.** Answer tiles are at least 72px tall. The primary action sits at the bottom of the
  screen on question pages. Text is at least 16px.
- **Host.** The prompt is 40px or larger, the room code 96px or larger, and the timer seconds
  are mono at 48px or larger. Big numbers sit on solid surfaces.
- **Admin.** The language is the same but quieter: 1px outlines and a 2px shadow on cards only,
  no shadow on list rows, mono for metadata, and compact padding. It stays dense.

## 3. Technical plan (summary)

1. **Tokens.** Add a token block to each app's `src/index.css`: CSS custom properties holding
   space-separated RGB channels, one set under `:root, [data-theme="light"]` and one under
   `[data-theme="dark"]`. The block is **byte-identical in all three apps**, and a test enforces
   that.
2. **Tailwind.** Each app's `tailwind.config.ts` **replaces** `theme.colors` (it does not extend
   it) with the token names, mapped as `rgb(var(--x) / <alpha-value>)`, plus `transparent`,
   `current` and `inherit`. Raw palette classes such as `bg-slate-800` then generate no CSS at
   all. The config also adds `boxShadow` (`hard-sm`, `hard`, `hard-lg`) and `fontFamily`
   (`sans`/`display` = Bricolage, `mono` = JetBrains Mono).
3. **Runtime.** `src/lib/theme.ts` (identical copy per app) and
   `src/components/ThemeToggle.tsx` hold the theme logic. Before first paint, an inline script in
   each `index.html` sets `<html data-theme>` from storage or the OS.
4. **Migration.**
   - Every raw colour in `src/**/*.{ts,tsx}` is replaced by a token (mapping in §6). Canvas
     drawing reads tokens through `cssColor('--x')` and redraws when the theme changes.
   - The primitives (`Button`, `Card`, `Input`, `TimerBar`) are rebuilt in the new language.
   - The signature elements are applied screen by screen (§7).
5. **Enforcement.**
   - A Python unit test scans the sources: no raw palette utilities, no hex or `rgb(` literals
     outside the token block, identical token blocks, and a WCAG contrast check for every
     declared text/background pair in both themes. It also runs in CI.
   - A Playwright e2e file covers the OS default, the toggle, persistence and focus outlines in
     all three apps.
6. **Evidence.**
   - `scripts/ui_screenshots.py` (already written) captures the same 38 screens. It writes
     `docs/ui/t9/before-dark-*.png` (starter look, captured on `main` `60ee669`) and
     `after-{light,dark}-*.png`.
   - `docs/ui/README.md` indexes them.

## 4. Decisions (with rationale and self-critique)

### D1. CSS variables plus a *replaced* Tailwind palette, not `dark:` variants

`darkMode: 'class'` with `dark:bg-…` would double every class string. It would also keep raw
palette names in components, which T9 forbids.

With variables, a component says `bg-surface text-ink` once, and the theme switch is a single
attribute on `<html>`. Replacing `theme.colors` means leftover raw classes produce nothing. That
is a silent failure, which is why the static check in D9 is mandatory.

*Critique:* opacity modifiers (`bg-accent/20`) only work because the variables hold bare
channels (`255 62 165`), not `#hex`. Every token must use that format; the unit test checks it.

### D2. Same token *names and values* in all three apps, copied, with equality enforced

The apps share no code by convention (frontend/README.md). A shared package would need
workspace and build changes in three Vite configs, the CI job and the nginx Dockerfile.

Instead the block between `/* tokens:start */` and `/* tokens:end */` is copied verbatim, and
`test_theme_tokens.py` asserts the three copies are identical. App-specific styling (admin
density, host sizes) lives in components, not in different token values.

### D3. Two-state toggle; the OS preference applies until the first click

- **Storage.** `localStorage['buzzer-theme']` is `'light'`, `'dark'` or absent.
- **No stored value.** The app follows `matchMedia('(prefers-color-scheme: dark)')`, live,
  including OS changes mid-session.
- **Clicking the toggle.** It stores the opposite of the *current effective* theme. From then on
  the OS preference is ignored.
- **Other tabs.** A `storage` event updates other open tabs.

*Critique:* there is no way back to "follow system" short of clearing site data. That is
accepted because the requirement says "toggle". A three-state control (light/dark/system) is
harder to read at a glance on a projector.

### D4. One storage key shared by all three apps

The apps share the nginx origin (`localhost:8080`), so they share `localStorage`. One key means
an instructor who picks Night in the host app also gets it in admin, which is consistent.

*Critique:* on the same browser, you can't run the host in Night on the projector while admin is
in Paper in another tab. That is rare, and either app's toggle fixes it in one click. In dev
(three ports) the apps have separate storage, which is harmless.

### D5. No flash of the wrong theme

An inline `<script>` in `<head>` of each `index.html` reads storage, falls back to `matchMedia`,
and sets `document.documentElement.dataset.theme` before CSS paints. Without it, every reload
would flash Paper before React mounts.

There is no CSP in `nginx/` (checked), so inline scripts are allowed. Also added to the head:

- `<meta name="color-scheme" content="light dark">`;
- `color-scheme: light|dark` in each token block, so native controls (date inputs, scrollbars,
  `<select>`) follow the theme.

### D6. Focus states: one global rule

`index.css`:

```
:focus-visible {
  outline: 3px solid rgb(var(--focus));
  outline-offset: 2px;
}
```

This covers every raw `<button>`, `<a>`, `<input>` and `<select>` in about 70 files without
touching each one.

Outlines already follow `border-radius`, so the rule needs nothing more.

`focus:outline-none` is allowed **only** together with a ring on the same pseudo-class. Inputs,
selects and textareas use exactly `focus:outline-none focus:ring-[3px] focus:ring-focus` (the
ring shows on any focus). `focus-visible:ring-0` is never used. Everything else relies on the
global outline.

The outline sits 2px *outside* the element, so it must contrast with the backdrop, not with the
element's own fill. `focus` must be ≥ 3:1 against `canvas`, `surface` and `sunken` in both themes
(WCAG 1.4.11; tested).

The one failing backdrop is the admin sidebar slab (`bg-ink`; Night `focus` on `ink` is 2.18).
Inside `.slab`, `:focus-visible` uses `outline-color: rgb(var(--canvas))` instead (≥ 15:1,
tested).

### D7. Dark text on saturated fills

Accent, success, danger, warning and the eight option inks all use `on-fill` text, which is
`#17141F` in both themes, never white. All 12 fills pass 4.5:1 with it (§6.2).

*Critique:* a dark-on-fluorescent look is the "bold" part. The starter's white-on-yellow tile is
~2:1 and fails today.

### D8. Self-hosted variable fonts via `@fontsource-variable`

The packages are `@fontsource-variable/bricolage-grotesque` and
`@fontsource-variable/jetbrains-mono` (5.3.0), imported in each app's `main.tsx`.

Google Fonts CDN is rejected: classroom networks can block it, it leaks player IPs to a third
party, and the nginx Docker build already runs `npm ci`, so packages cost nothing extra. Only
the Latin subset downloads, thanks to `unicode-range`. The cost is about 60 kB woff2 per family.
`font-display: swap` is the fontsource default, and the fallback is the current system stack.

*Critique:* Bricolage's quirky shapes could hurt the readability of long admin tables. Its
optical-size axis is narrower at 14px, and admin body text keeps the regular weight. If
screenshots show poor density, admin body falls back to the system stack (a one-line
`fontFamily` change). Record that in §12 if done.

### D9. Static enforcement test, run in CI

`tests/unit/test_theme_tokens.py` needs only the standard library and pytest. It does not import
`app`, so CI can run it without backend deps. Checks:

1. **No raw palette utilities.** No match for
   `(bg|text|border|ring|ring-offset|from|via|to|fill|stroke|divide|placeholder|outline|accent|shadow|decoration|caret)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black)(-\d+)?\b`
   anywhere in `frontend/{host,player,admin}/src/**/*.{ts,tsx}`.
2. **No colour literals and no dynamic colour classes** in those files:
   - no `['"\`(\s:,]#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?\b` (a quote, paren, space, colon or comma
     before the `#`, so `#1` rank labels pass);
   - no `rgb(` / `rgba(` / `hsl(` except the one `rgb(${…})` template in `lib/theme.ts`
     `cssColor()`;
   - no `(bg|text|border|ring|from|to|fill|stroke)-\$\{` (D10a).
3. **`index.css`.**
   - Outside the token block there is no hex literal, and every `rgb(` / `rgba(` / `hsl(` is
     immediately followed by `var(--`. So `rgb(var(--on-fill) / .12)` is fine and `rgb(0 0 0)`
     is not.
   - CSS keywords are allowed where only alpha matters: the `.ticket` notch masks use `black` and
     `transparent`.
   - The grain is an SVG data URI (`feTurbulence` plus an alpha-only `feColorMatrix`) with
     numbers but no colour literals. It is drawn on `body::before`: fixed, full-screen,
     `pointer-events: none`, opacity from a `--grain` number variable in the token block. So
     `body`'s `background-color` stays exactly `canvas`.
4. **Identical token blocks.** The three token blocks are byte-identical, and each declares
   every name in §6.1 for both themes, in `R G B` channel format.
5. **Text contrast.** Every pair in §6.2's contrast table is ≥ 4.5:1 for text pairs and ≥ 3:1
   for UI pairs, in both themes, computed from the token values (WCAG 2.1 relative luminance).
6. **Palette replaced.** Each `tailwind.config.ts` sets `colors:` directly under `theme` (not
   under `extend`).

The file needs only the standard library and pytest (`pytest tests/unit/test_theme_tokens.py -q`).
*(Dropped at push time: a planned `frontend-theme-tokens` CI job. Rubric R2 forbids altering the
pipeline, so these tests run locally and with the rest of `tests/unit`.)*

### D10. Canvas drawing reads tokens at draw time

`HotspotCanvas` (player), `HotspotView` (host) and `HotspotEditor` (host and the identical admin
copy) currently hardcode hex values. They will:

- call `cssColor('--success')` and similar from `lib/theme.ts`, which returns
  `rgb(R G B)` from `getComputedStyle(document.documentElement)`;
- add the current theme (from `useTheme()`) to the draw effect's dependencies, so a toggle
  repaints.

The existing `--hotspot-inner|outer|miss|neutral` CSS-variable hooks and their hex fallbacks
are deleted. They map to tokens as follows:

| Band / use | Token |
|---|---|
| inner | `--success` |
| outer | `--warning` |
| miss | `--danger` |
| neutral | `--ink-soft` |
| no-band marker (player, before results) | `--accent` |
| image-free placeholder (`#1e293b` fill, `#94a3b8` text) | `--sunken` / `--ink-soft` |

Markers are outlined with `--on-fill` inside and `--canvas` outside, so they stay visible on any
photo.

### D10a. No dynamically built colour class names

Tailwind's JIT only emits classes that appear literally in the source. Every variable colour is
a **static lookup map** of whole class strings. Examples:

- `const OPTION_BG = ['bg-opt-1', …, 'bg-opt-8']`
- `const STAMP_TONE = { success: 'text-success-ink', … }`

Templates such as `` `bg-opt-${n}` `` are forbidden, and D9.2 checks for them.

### D11. Scope boundaries

**In scope:**

- every page and component in the three apps, including T7 (ordering, hotspot) and T8 (image
  picker, image library) surfaces;
- admin JSX text containing JavaScript escapes (the backslash-u-00b7 / -2026 / -00b1 sequences
  render literally, as the "before" admin question-editor shot shows), since this is
  look-and-feel;
- the `docs/ui` evidence.

**Out of scope:**

- layout or behaviour changes beyond what the design needs;
- the player's fragile socket flows (separate fix branch);
- new features;
- HTML-rendered prompts;
- backend changes (none needed).

## 5. Theme runtime (identical in all three apps)

### 5.1 `src/lib/theme.ts`

- `export type Theme = 'light' | 'dark'`
- `const KEY = 'buzzer-theme'`
- `storedTheme(): Theme | null`: reads `localStorage` in try/catch (private mode can throw).
  Anything other than `'light'` or `'dark'` → `null`.
- `systemTheme(): Theme`: `matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'`.
- `effectiveTheme(): Theme`: `storedTheme() ?? systemTheme()`.
- `applyTheme(t)`: sets `document.documentElement.dataset.theme = t`.
- `setTheme(t)`: stores `t` (try/catch), applies it, and notifies subscribers.
- `subscribe(cb)`: listens to the `storage` event (key match → apply and notify) and to
  `matchMedia` `change` (only when `storedTheme()` is null → apply and notify). Returns an
  unsubscribe function.
- `useTheme(): [Theme, (t: Theme) => void]`: `useSyncExternalStore(subscribe, effectiveTheme)`
  plus `setTheme`.
- `cssColor(name: string, alpha = 1): string`: returns `rgb(${channels} / ${alpha})` from the
  computed style. The fallback when empty is `rgb(128 128 128 / alpha)`.

### 5.2 `index.html` inline script (each app, inside `<head>`)

The script mirrors `effectiveTheme()`:

```
(function(){
  try {
    var t = localStorage.getItem('buzzer-theme');
  } catch (e) {}
  if (t !== 'light' && t !== 'dark')
    t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.dataset.theme = t;
})();
```

`<head>` also gets `<meta name="color-scheme" content="light dark">`.

### 5.3 `src/components/ThemeToggle.tsx`

- A `<button type="button" role="switch" aria-checked={theme === 'dark'}>` with
  `aria-label="Dark theme"` and `data-testid="theme-toggle"`.
- Visual:
  - a `bg-surface` pill with a 2px `line` border and `shadow-hard-sm`, split into two halves;
  - each half is a lucide icon (`Sun`, `Moon`) followed by `PAPER` / `NIGHT` in mono 11–12px
    uppercase;
  - the active half is `bg-ink text-canvas`, the inactive half `text-ink-soft`.
- Accessibility: the visible text is decorative. The name comes from `aria-label`, the state
  from `aria-checked`.
- `compact?: boolean`: only the active half's icon, no words. Used on the player's game top bar
  and the host's game screens. Minimum touch target 44×44px.
- `onSlab?: boolean`: for the admin sidebar. The pill is `bg-ink border-canvas`, the active half
  `bg-canvas text-ink`, the inactive half `text-canvas/70`.

### 5.4 Where the toggle lives

| App | Location |
|---|---|
| Admin, signed in | Sidebar footer, above "Open Host app" (`onSlab`) |
| Admin, login | Top-right corner |
| Host, management | `ManagementLayout` header, right side |
| Host, login | Top-right corner |
| Host, game screens (`GameLayout`) | Fixed top-right, `compact`. The fixed QR badge stays bottom-right. |
| Player, Join / Name / Login | Top-right corner |
| Player, game screens (`GameLayout`) | Inside a new slim top bar, 48px: room code (mono) on the left, compact toggle on the right. Page content starts below it. |

## 6. Tokens

### 6.1 Names and values (`R G B` channels; hex shown for readability)

| Token | Role | Paper (light) | Night (dark) |
|---|---|---|---|
| `canvas` | page background | `#F3EDE2` | `#13111A` |
| `surface` | cards, inputs, panels | `#FFFBF4` | `#1D1A26` |
| `sunken` | wells, hover fills, table headers, placeholders | `#E7DECD` | `#0B0A10` |
| `ink` | primary text, strong outlines | `#17141F` | `#F6F0E6` |
| `ink-muted` | secondary text | `#4A4352` | `#CBC3D3` |
| `ink-soft` | tertiary text, captions, placeholders | `#5F5868` | `#A79FB2` |
| `line` | strong outlines (S1) | `#17141F` | `#E9E1D4` |
| `line-soft` | dividers, quiet borders (non-text, decorative) | `#CFC4B0` | `#3A3447` |
| `shadow` | hard-shadow colour | `#17141F` | `#4B3F6B` |
| `accent` | primary action fill (fluorescent pink) | `#FF3EA5` | `#FF5CB4` |
| `accent-ink` | accent-coloured text/links on canvas/surface | `#B0105E` | `#FF8FCB` |
| `success` / `success-ink` | correct, saved | `#1FC77A` / `#0A6E3E` | `#3BE08E` / `#5BE8A0` |
| `danger` / `danger-ink` | errors, destructive, wrong | `#FF5A36` / `#B42A0C` | `#FF7452` / `#FF9479` |
| `warning` / `warning-ink` | locked, participation, partial | `#FFC530` / `#7A5000` | `#FFD45C` / `#FFD45C` |
| `focus` | focus outline or ring only (never text, never a selection indicator) | `#2448E0` | `#7FA2FF` |
| `on-fill` | text on any saturated fill | `#17141F` | `#17141F` |
| `qr` | QR code background (must stay white) | `#FFFFFF` | `#FFFFFF` |
| `scrim` | modal backdrop (used at `/60`) | `#17141F` | `#000000` |
| `opt-1`…`opt-8` | answer inks A–H | `#FF5A36` `#3D7BFF` `#FFC530` `#1FC77A` `#A879FF` `#FF9A1F` `#FF6FC0` `#22C3C3` | same |

**Exact token list (test 4).** 30 names, each a CSS variable `--<name>`:

- surfaces and text: `canvas`, `surface`, `sunken`, `ink`, `ink-muted`, `ink-soft`
- lines: `line`, `line-soft`, `shadow`
- fills and their text colours: `accent`, `accent-ink`, `success`, `success-ink`, `danger`,
  `danger-ink`, `warning`, `warning-ink`
- utility: `focus`, `on-fill`, `qr`, `scrim`
- option inks: `opt-1` to `opt-8`

There is no `info` token: links use `accent-ink`. The token block also sets `color-scheme` and
the non-colour `--grain` opacity.

The option inks are deliberately the same in both themes, so an option is recognisable across
devices with different themes. On Night their 2px border is `on-fill` (dark), so they read as
printed stickers.

### 6.2 Contrast pairs enforced by the test

All values below were measured in design. The test recomputes them from the CSS.

**Text pairs (≥ 4.5).**

- Paper:
  - `ink` / `ink-muted` / `ink-soft` / `accent-ink` / `success-ink` / `danger-ink` /
    `warning-ink` on `canvas`, `surface` and `sunken`. The lowest is `success-ink` on `sunken`
    at 4.75.
  - `on-fill` on `accent`, `success`, `danger`, `warning` and `opt-1…8`. The lowest is
    `opt-2` blue at 4.74.
- Night: the same pairs. The lowest is `ink-soft` on `surface` at 6.71.

**Composite text pairs (≥ 4.5; the tint is alpha-blended over the backdrop first).**

- `accent-ink` on `accent/15`, `success-ink` on `success/15`, `danger-ink` on `danger/15`, and
  `warning-ink` on `warning/20`, each over both `surface` and `canvas`.
  - The lowest is Paper `danger-ink` over `canvas` at 4.71.
  - Tinted chips and notices use **only** these alphas.
- `canvas` on `ink` (slab text, segmented controls, nav pills): 15.59 / 16.50.
- `canvas/70` over `ink` (slab eyebrows): 8.07 / 6.59.

**UI pairs (≥ 3).**

- `focus` on `canvas`, `surface` and `sunken`: Paper ≥ 5.1, Night ≥ 7.
- `canvas` on `ink` (slab focus outline).
- `line` on `canvas`.
- `ink` on `canvas` (the multi-select selection ring).

### 6.3 Raw → token mapping for the migration

This table is guidance for the mechanical pass. Each hit is still reviewed in context, because
`text-white` means `on-fill` on a fill and `ink` elsewhere.

| Raw | Token |
|---|---|
| `bg-slate-900` (`/xx`) | `bg-canvas` |
| `bg-slate-800` (`/xx`) | `bg-surface` |
| `bg-slate-700` / `-600` (`/xx`) | `bg-sunken` (hover/well) |
| `text-white`, `text-slate-100`, `-200` | `text-ink` (or `text-on-fill` on a fill) |
| `text-slate-300`, `-400` | `text-ink-muted` |
| `text-slate-500`, `-600`, `placeholder-slate-*` | `text-ink-soft`, `placeholder-ink-soft` |
| `border-slate-*`, `divide-slate-*` | `border-line-soft` (cards/inputs upgraded to `border-line` per §7) |
| `bg-indigo-500/600`, `border-indigo-*` | `bg-accent`, `border-accent` |
| `text-indigo-300/400/700`, `bg-indigo-900` chips | `text-accent-ink`; chips become `bg-accent/15 text-accent-ink` |
| `ring-indigo-*`, `ring-slate-*`, `ring-white` | `ring-focus` |
| `accent-indigo-500` (checkbox) | `accent-accent` |
| `ring-offset-slate-900` | `ring-offset-canvas` |
| red / green, emerald / amber, yellow (text) | `danger-ink` / `success-ink` / `warning-ink` |
| red / green / amber (fills, tinted bgs `/10`–`/50`) | `danger` / `success` / `warning` at the same alpha |
| `bg-white` behind QR | `bg-qr` |
| `bg-white/90` behind option images | `bg-qr` (images need a neutral light backdrop) |
| `bg-black/60` modal | `bg-scrim/60` |
| player `OPTION_COLORS` 8 entries | `bg-opt-1 … bg-opt-8`, text `on-fill`, border `border-on-fill` |
| `TimerBar` green/yellow/red | `success` / `warning` / `danger` |
| `OrderingView`/`OrderingPicker` `var(--ordering-*, #hex)` hooks | Hooks deleted. Classes `bg-success` (correct), `bg-accent` (bar / selected), `bg-warning` (misplaced). |
| Hotspot canvases' `--hotspot-*` hooks and hex | Hooks deleted; tokens via `cssColor()` as in D10 |

## 7. Screens (what "deliberate, not recoloured" means per screen)

### 7.1 Primitives (each app's `components/ui/`)

**`Button`.** Base: `inline-flex items-center justify-center gap-2 font-bold border-2
border-line rounded-xl transition-[transform,box-shadow] duration-75 shadow-hard
active:translate-x-1 active:translate-y-1 active:shadow-none disabled:opacity-50
disabled:shadow-none disabled:pointer-events-none`. Variants:

- `default`: `bg-accent text-on-fill`
- `outline`: `bg-surface text-ink`
- `ghost`: `border-transparent shadow-none bg-transparent text-ink-muted hover:bg-sunken
  hover:text-ink`, with no press translate
- `destructive`: `bg-danger text-on-fill`

Admin `Button` uses `shadow-hard-sm`, `active:translate-x-0.5 active:translate-y-0.5` and
`border` (1px) at `sm` size.

**`Card`.** `rounded-2xl border-2 border-line bg-surface shadow-hard` in host and player.
`rounded-xl border border-line bg-surface shadow-hard-sm` in admin.

**`Input`.** `bg-surface text-ink border-2 border-line rounded-xl placeholder:text-ink-soft
focus:outline-none focus:ring-[3px] focus:ring-focus` (D6).

**`TimerBar`.** A chunky track: `h-4` (player) or `h-6` (host), `bg-sunken border-2
border-line rounded-full`. The fill is `success`, then `warning` at ≤ 30%, then `danger` at
≤ 10%. Seconds are shown in mono. The host shows them at `text-5xl`.

**Tailwind extras (config):**

- `boxShadow`: `hard-sm` = `2px 2px 0 0 rgb(var(--shadow))`, `hard` = `4px 4px 0 0 …`,
  `hard-lg` = `6px 6px 0 0 …`.
- The press-down translates match the shadows: `translate-x/y-0.5`, `-1` and `-1.5`.
- `ringColor.DEFAULT` = `rgb(var(--focus))`, so a bare `ring-2` never falls back to Tailwind's
  built-in blue.
- Tailwind 3 has no text-shadow utility. The wordmark uses the arbitrary property
  `[text-shadow:4px_4px_0_rgb(var(--accent))]`.

**New: `Stamp`** (host and player). Props `tone: 'success' | 'warning' | 'danger' | 'accent'`
and `children`. It renders as
`inline-block -rotate-6 border-[3px] border-current px-4 py-1 font-mono font-black uppercase
tracking-widest` plus the tone's text class from a static map (`text-success-ink`, …; D10a), with an inner 1px inset outline (`outline outline-1
outline-current outline-offset-[-6px]`).

**New: `Ticket`** (host and player). Props `code` and `size: 'lg' | 'md' | 'sm'`. It renders a
`bg-surface border-2 border-line shadow-hard` box holding the mono code. Notches on the left and
right edges are drawn with `mask` radial gradients (in `index.css` as `.ticket`), with a dashed
`border-line-soft` divider and a tiny `ROOM` eyebrow.

**New: `.halftone` utility** in `index.css`:
`background-image: radial-gradient(rgb(var(--on-fill) / .12) 1px, transparent 1.2px);
background-size: 8px 8px`. It is used on option tiles and result bars.

### 7.2 Player

| Screen | Treatment |
|---|---|
| Join | A huge `BUZZER` wordmark in Bricolage 800 with a 4px offset `accent` text-shadow. The code input is a mono ticket-styled `Input`, uppercase, `tracking-[0.3em]`. A full-width `Join` button sits at the bottom. |
| Name | Mode tabs (Guest / Sign in) become a segmented control: `border-2 border-line`, with the active segment `bg-ink text-canvas`. Inputs and buttons are the primitives. |
| Lobby | `Ticket` (md) with the code, a `Stamp tone="success"` reading "YOU'RE IN", the player's name in display type, and a gentle three-dot "waiting for host" pulse (disabled under `prefers-reduced-motion`). |
| Question: MC | Tiles are `bg-opt-N text-on-fill border-2 border-on-fill shadow-hard rounded-2xl halftone`, with press-down. The letter sits in a 40px circle `bg-on-fill text-opt-N` (inverted). Tiles are at least 72px tall. Image tiles get `bg-qr` behind the image. |
| Question: TF | Two giant tiles, `opt-4` (True ✓) and `opt-1` (False ✗), each with a word and an icon. |
| Question: fill in the blank | A large `Input`, with the submit `Button lg` full width at the bottom. |
| Question: multi-select | Tiles show a check box square (`border-2 border-on-fill`; checked = `bg-on-fill` with a ✓ in `opt-N`). The selected tile also gets `ring-4 ring-ink ring-offset-2 ring-offset-canvas`. The ring is drawn on the canvas, not the fill, so it is ≥ 15:1 in both themes. `focus` stays reserved for keyboard focus. Submit sits at the bottom. |
| Question: ordering (`OrderingPicker`) | Unplaced: `bg-surface border-2 border-line`. Placed: `bg-accent text-on-fill`, with the position badge as an ink circle. |
| Question: hotspot (`HotspotCanvas`) | Canvas in a `border-2 border-line` frame. Colours come from tokens. |
| Feedback / answered | A `Stamp tone="accent"` "LOCKED IN" plus "waiting for results…". |
| Results | A big `Stamp` (CORRECT / PARTIAL / NOT QUITE / NO ANSWER, mapped from the existing outcome logic), points in mono `text-5xl`, total and rank in a `Card`. The answer reveal uses the same opt colours. |
| Game over | Rank as a large mono `#N`, score, and a recap list of `Card` rows with small stamps. The "Play again" button is the primitive. |
| Host-disconnected banner | `bg-warning text-on-fill border-b-2 border-line`. |

### 7.3 Host

| Screen | Treatment |
|---|---|
| Login | A centred `Card` with the wordmark, primitives, and the toggle at top-right. |
| `ManagementLayout` | A header bar `bg-surface border-b-2 border-line` with the `BUZZER·HOST` wordmark (accent dot), nav links (active = `bg-ink text-canvas` pill) and the toggle. |
| Home, Course, Roster, Sessions, Images, question editor, `OrderingEditor`, `HotspotEditor`, `ImagePicker` | Token migration plus primitives. Section headings are display type, metadata is mono `text-ink-soft`. Tables use `bg-sunken` header rows and `divide-line-soft`. Chips: `ACCURACY` = `bg-accent/15 text-accent-ink`, `PARTICIPATION` = `bg-warning/20 text-warning-ink`. |
| Lobby | Two columns: the QR in a `bg-qr border-2 border-line shadow-hard` frame, and a giant `Ticket` (lg, `text-[8rem]`). Above them, the game title in display `text-5xl` and the join URL in mono. The player count is a big mono number in a pill. The auto-advance switch uses the same pill language as the toggle. Start is `Button lg`. |
| Question | An eyebrow row in mono uppercase (`Q 3 / 13 · HOTSPOT · ACCURACY` as chips). The timer is host-size. The prompt is display `text-5xl` (`md:text-6xl`). Option-image tiles use `opt-N` borders and letter badges. Answered count is mono `text-3xl`. Lock and Show Results are primitives. When locked, a `Stamp tone="warning"` reads "LOCKED". |
| Results | Each option's bar is `bg-opt-N halftone border-2 border-line` with the count in mono. The correct option gets a `Stamp tone="success"` "✓ ANSWER" beside the bar, and wrong bars are not dimmed. `HotspotView` and `OrderingView` use tokens. |
| Game over | The histogram's bars are in `accent` with ink outlines. The stat cards (avg / high / players) are `Card`s with mono numbers. |
| Corner badge (QR + code) | `Ticket` (sm) with the QR on `bg-qr`. |

### 7.4 Admin

| Area | Treatment |
|---|---|
| Sidebar | `bg-ink text-canvas` in **both** themes: an ink slab in Paper, and a cream slab in Night (because `ink` inverts). The active link is `bg-accent text-on-fill`. The section eyebrows are mono `text-canvas/70`. The toggle sits in the footer, styled for the slab. |
| Lists (Users, Courses, Games, Sessions, Guests) | Rows on `surface`, `divide-y divide-line-soft`, no shadows. Status chips: active = `success`, completed = `accent/15`, and so on. |
| Question editor, hotspot, ordering, image picker, images page | Token migration and primitives. Literal `·` escapes become real characters. |

*Critique of the inverted sidebar:* in Night, a cream slab next to a dark canvas is very bright.
If the screenshots show that it overpowers the content, the sidebar switches to `bg-surface
border-r-2 border-line`, and this gets noted in §12. The check is mandatory during the
screenshot review.

## 8. Tests

### 8.1 Unit — `tests/unit/test_theme_tokens.py` (written first; fails before migration)

| # | Test | Asserts |
|---|---|---|
| 1 | `test_no_raw_palette_utilities` | The D9.1 regex finds 0 hits. The failure lists `file:line: class`. |
| 2 | `test_no_colour_literals_in_components` | D9.2 |
| 3 | `test_index_css_colours_only_in_token_block` | D9.3 |
| 4 | `test_token_blocks_identical_and_complete` | D9.4: every §6.1 name in both theme selectors, channel format `^\d{1,3} \d{1,3} \d{1,3}$` |
| 5 | `test_text_contrast_aa` (parametrized: theme × pair) | §6.2 text pairs ≥ 4.5 |
| 6 | `test_ui_contrast` | §6.2 UI pairs ≥ 3 |
| 7 | `test_tailwind_palette_replaced` | D9.6, for each app |
| 8 | `test_theme_bootstrap_in_index_html` | Each `index.html` has the inline script with `buzzer-theme` and the `color-scheme` meta |

### 8.2 Browser e2e — `tests/e2e/test_theme.py` (live stack, built apps)

Each test runs in a fresh browser context.

| # | Test | Steps and asserts |
|---|---|---|
| 1 | `test_first_visit_follows_os` (parametrized: app × scheme) | A context with `color_scheme=scheme` and no storage visits `/admin/login`, `/host/login` and `/player/join`. `html[data-theme] == scheme`, and the computed `body` background equals `rgb(canvas[scheme])`. |
| 2 | `test_toggle_flips_and_persists` (parametrized: app) | Start with `color_scheme='light'`. The toggle is visible, then clicked: `data-theme` becomes `dark` and `localStorage['buzzer-theme'] == 'dark'`. Reload: still `dark` (the inline script works; no flash, checked by reading `data-theme` at `domcontentloaded`). Click again: `light`. |
| 3 | `test_choice_beats_os_and_is_shared` | Set dark in player, then open `/host/login` in the same context with `color_scheme='light'`: it is `dark`. |
| 4 | `test_toggle_on_signed_in_screens` | Toggle visible with a token on `/admin/users`, `/host/home`, and the host lobby of a fresh room. A phone that has joined the lobby sees the toggle in the top bar. |
| 5 | `test_keyboard_focus_visible` | On `/host/login`, Tab to the first input, then to the button. The computed `outline-style` is not `none`, or the `box-shadow` contains the focus colour. |
| 6 | `test_hotspot_canvas_repaints_on_toggle` | Upload a 400×100 PNG generated with Pillow to a fresh course, create one hotspot question with it, and open a room. The player joins and the host starts the game. The player taps the canvas centre, so a marker is drawn in token colours. Read `canvas.toDataURL()`, click the compact toggle, and read it again: the two must differ. |

Colours are compared after normalising both sides. The browser reports `rgb(243, 237, 226)`, so
the test parses the token channels from `index.css` and formats them the same way.

The existing e2e files on `main` (`test_ordering_e2e.py`, `test_smoke.py`) must still pass. So
must `test_player_socket.py` once `fix/player-socket-reconnect` merges. They select by test id and text, which the migration keeps.

### 8.3 Visual review

The visual review is not automated. After the migration, run
`python scripts/ui_screenshots.py --tag after` and review every `after-*` image in both themes
against §7.

Fail the review for any of these:

- unreadable text;
- a leftover slate look;
- the toggle missing on a screen;
- overflow on the 390px phone.

## 9. Files touched

**Each app:**

- `src/index.css` (tokens, focus rule, `.halftone`, `.ticket`, grain);
- `tailwind.config.ts`, `index.html`, `src/main.tsx` (font imports);
- `package.json` and `package-lock.json` (2 fontsource deps);
- `src/lib/theme.ts` (new), `src/components/ThemeToggle.tsx` (new), `components/ui/*`;
- every page and component file with raw colours (≈ 70 files).

**Host and player:** `components/ui/Stamp.tsx` and `components/ui/Ticket.tsx` (new). Player
`GameLayout` gets the top bar.

**Tests and tooling:**

- `tests/unit/test_theme_tokens.py` (new), `tests/e2e/test_theme.py` (new);
- `scripts/ui_screenshots.py` (new);
- ~~`.gitlab-ci.yml` (new job)~~ — dropped (R2: the pipeline is not altered).

**Docs:**

- `docs/ui/t9/*.png`, `docs/ui/README.md`;
- `frontend/README.md` and the per-app `src/README.md`, `components/README.md` and
  `lib/README.md` (context-sync: the "hardcoded palette" gotchas become token docs);
- `docs/vzhou2.md` (session log). T9 also wants the screenshots cited in the individual T10
  document. The owner writes those sections, not this branch, so `docs/ui/README.md` lists the
  files to cite.

## 10. Phases and commits (test-first, atomic)

1. `docs: T9 design` (this file), `scripts/ui_screenshots.py` and the before screenshots.
   Every §5.4 toggle placement, including both login pages and the player join page, lands in
   phase 3.
2. `test: T9 token and theme tests`: unit and e2e, both failing.
3. `feat(theme): token layer, runtime, toggle, fonts, primitives`, in all three apps. Unit tests
   4–8 pass, and e2e 1–3 and 5 pass.
4. `feat(theme): player screens`.
5. `feat(theme): host screens` (including the T7/T8 editors and canvases).
6. `feat(theme): admin screens`, which also fixes the literal escapes. After this, unit tests
   1–3 pass and all e2e pass.
7. ~~`ci: theme token check`~~ — dropped before push (R2).
8. `docs: T9 after screenshots, READMEs, session log`.

A `mean-review` pass runs before step 8, and its fixes go into their own commits.

## 11. Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Tailwind `dark:` variants on every class | Doubles class strings, keeps raw palette names (fails the T9 token requirement), and only gives one alternate theme |
| Extend the palette instead of replacing it | Raw classes would keep working, so the migration couldn't be proven complete except by grep. Replacing makes them inert, and grep (D9) proves absence. |
| A shared `frontend/theme` package | Breaks the no-shared-code convention and needs build, CI and Docker changes. Copying with an equality test gets the same guarantee. |
| A "glassmorphism" or gradient-neon look | It's what most party-quiz clones already do, so it doesn't meet "bold and unique". Translucent layers also make contrast hard to guarantee. |
| shadcn/Radix Themes | Heavy dependency. Its generic look works against "unique". |
| Google Fonts CDN | Network and privacy (D8) |
| Three-state toggle (light / dark / system) | Less legible. The requirement says "toggle" (D3). |
| Per-app storage keys | Inconsistent across the instructor's tabs on one origin (D4) |
| Automated axe-core contrast scan in e2e | Needs a new npm or pip dependency and is flaky on canvas and images. Token-pair math, including the composite tints at their only allowed alphas, covers the text colours components can produce, because components can only use tokens (D9). |

## 12. Risks and open edges

- **Silent leftovers.** A raw class missed by the migration renders unstyled (inherits colour).
  Covered by D9.1. Dynamic class construction is forbidden by D10a and caught by D9.2.
- **The brutalist look may make admin noisy.** Mitigated by the lighter admin variants (§7.1,
  §7.4). The screenshot review decides.
- **Fluorescent inks wash out on projectors.** The host never relies on an ink alone: every
  option has its letter, and every verdict is a word.
- **The press-down transform shifts layout in tight rows.** `translate` doesn't affect layout.
  The shadow is outside the box, so containers with `overflow-hidden` need 4–6px padding to
  avoid clipping it. Check in the screenshots.
- **Canvas repaint.** If a component misses the theme dependency, it shows stale colours until
  the next redraw. Covered by e2e test 6 (player) and the review (host and editors).
- **Merge conflict with `fix/player-socket-reconnect`** (player `GameLayout.tsx`). Whichever
  lands second merges. Its changes are logic-only, and this branch's changes are class strings
  plus the top bar.
- **Fonts fail to load.** The system stack fallback keeps every metric reasonable. The mono
  fallback is `ui-monospace`.

## 13. Revision log

- 2026-10-06: first draft.
- 2026-10-06: revised after the Goldfish test (a fresh subagent given only this spec and the
  context READMEs).
  - **Must-fix items fixed:**
    - Input focus string: the old `focus-visible:ring-0` would have hidden keyboard focus.
    - Dropped `border-radius: inherit` from the focus rule.
    - Removed `info`. Darkened `focus` to `#2448E0` (Paper 4.44 → 5.85) and reserved it for
      focus only.
    - Added the slab focus override (Night `focus` on `ink` was 2.18).
    - Multi-select selection is now an `ink` ring offset onto the canvas, instead of `focus` on
      the fill (1.55–2.34).
    - Added the composite tint, slab and `canvas/70` pairs to the tested set (all ≥ 4.71).
    - Required static class maps (D10a).
    - Added the admin login toggle.
    - Made the `index.css` colour rules exact (halftone, ticket mask, grain).
    - Deleted the hotspot and ordering CSS-variable hooks, with an explicit band → token map.
    - Added an explicit 30-name token list.
  - **Nice-to-haves taken:**
    - shadow offsets matched to the press translates;
    - `ringColor.DEFAULT`;
    - the text-shadow arbitrary property;
    - a self-consistent toggle visual;
    - concrete e2e test 6 and colour normalisation;
    - the `test_player_socket.py` location;
    - the T10 citation note.
- **2026-10-06, during implementation.** Changes from the screenshot review and the mean-review:
  - **Night admin sidebar.** The mandatory §7.4 brightness check failed: the cream slab
    overpowered the content. Instead of switching to `bg-surface` in both themes, Paper keeps
    the ink slab. In Night, `:root[data-theme='dark'] .slab` remaps `--ink` → `--surface` and
    `--canvas` → `--line` (the `var()` references sit outside the token block), and the aside
    gets a `border-r-2 border-line` rule. The new pairs (`line` on `surface`, `line/70` over
    `surface`, `surface` on `line`) are added to the contrast tests.
  - **Canvas frames are `ring-2 ring-line`, not borders.** A border on a `<canvas>` shrank the
    drawn bitmap by 4px and shifted `HotspotEditor`'s click-to-place by the border width. A ring
    is a box-shadow, so it leaves layout and `getBoundingClientRect()` alone.
  - **Result bars:** a zero count renders no fill. Before, the `pr-4` padding drew a 16px sliver.
  - **No CI job.** The planned `frontend-theme-tokens` job was removed before the push: R2 says
    the pipeline must not be altered, and the user did not ask for a pipeline change.
  - **Screenshots** are saved as 256-colour PNGs. The paper grain defeats PNG compression, and
    quantising halves the size with no visible change.
