# frontend/host/src/components/

Presentational building blocks for the Host app: generic primitives in `ui/`, plus one
game-specific component, `HotspotView.tsx`. Other game-specific pieces (charts, word cloud,
histogram, question cards) are defined inline inside the page files in
`frontend/host/src/pages/game/`. None of the `ui/` components touch the network, sockets, or
global state; `HotspotView` fetches its image via `lib/images.ts`.

## Files

| File | Purpose |
|---|---|
| `ui/button.tsx` | `Button` — a styled `<button>` with `variant` (`default`, `outline`, `ghost`, `destructive`) and `size` (`sm`, `md`, `lg`). |
| `ui/card.tsx` | `Card`, `CardHeader`, `CardContent` — bordered, padded panel wrappers around `<div>`. |
| `ui/input.tsx` | `Input` — a styled `<input>`. |
| `ui/TimerBar.tsx` | `TimerBar` — a self-running countdown bar (green → yellow → red) that can be paused. |
| `HotspotView.tsx` | `HotspotView` — display-only hotspot `<canvas>` (`docs/plans/t7-hotspot.md` §7.8): image, optional rings, optional taps coloured by band, optional legend; `ringsFromReveal(reveal)` helper. |

## Key entry points

- All exports are named (no default exports). Every component except `TimerBar` passes through
  all native HTML attributes and merges extra `className` values with `cn()`.
- `TimerBar({ totalSeconds, initialSeconds?, paused? })`
  - It starts at `initialSeconds` (or `totalSeconds`) and counts down on its own with a 100ms
    `setInterval` against a wall-clock end time.
  - `paused` freezes the display; when unpaused it resumes from the frozen value.
  - `totalSeconds` and `initialSeconds` are **read once, at mount**. The interval effect has an
    empty dependency list, so callers must remount it with a `key` to restart it for a new
    question (`QuestionPage` uses `key={currentQuestion.questionId}`).
  - It shows `Math.ceil(timeLeft)` seconds next to the bar.

- `HotspotView({ imageId, aspectRatio, label, rings?, taps?, legend?, maxHeightVh? })`
  - Loads its own image (`loadImageUrl`) and revokes the URL on change/unmount; failure draws
    "Image unavailable" at the bottom edge, rings and taps still drawn.
  - Same layout rule as the player's `HotspotCanvas`: image letterboxed by `aspectRatio`,
    points as fractions of the image, ring radii as fractions of the **longer side**.
  - `legend.accuracy` → "Bullseye N · Close N · Miss N" from `legend.distribution`; otherwise
    (COMPLETENESS) "N taps", or "500+ taps" at the server's cap.
  - Colours from CSS variables `--hotspot-inner|outer|miss|neutral` (fallbacks until T9).

## Depends on

- `frontend/host/src/lib/utils.ts` — `cn()` (`clsx` + `tailwind-merge`), used by `button`, `card`, `input`.
- npm: `react` (`TimerBar` only). Styling is Tailwind utility classes only.

## Depended on by

- `frontend/host/src/pages/`:
  - `LoginPage.tsx` — `Button`, `Input`, `Card*`
  - `HomePage.tsx` — `Button`, `Card*`
  - `game/LobbyPage.tsx`, `game/ResultsPage.tsx`, `game/GameOverPage.tsx` — `Button`
  - `game/QuestionPage.tsx` — `Button`, `TimerBar`
- Nothing outside the host app imports these; the player and admin apps have their own copies.

## Gotchas found while reading

- **Hotspot drawing exists twice.** `HotspotView.tsx` repeats the layout/ring maths of
  `frontend/player/src/components/HotspotCanvas.tsx` (the apps share no code). Change both
  together. The same will apply to `HotspotEditor` (T7 stage B), which gets an admin copy in
  T4 phase 3 — keep that copy in sync too.

- **Copies in each app:** `button`, `card` and `input` are byte-identical to the copies in
  `frontend/admin/src/components/ui/`. They differ from `frontend/player/src/components/ui/`
  in rounding, padding and an `active:scale-95` press effect. The player `TimerBar` lacks
  `initialSeconds`. A style fix here has to be repeated by hand in the other apps.
- **Timer drift on lock:** `TimerBar` ignores later changes to `initialSeconds`. When the server
  sends `question_locked` with its own `remainingSeconds`, the bar just freezes at whatever its
  local clock reached. Resuming continues from that local value, so the bar can drift slightly
  from the server's timer (which is what actually locks the question).
- **Timer never stops:** the interval keeps running every 100ms after the bar reaches 0 and while
  paused, until the component unmounts. It is harmless, but never stops on its own.
- **Implicit submit buttons:** `Button` does not set a default `type`, so inside a `<form>` it
  submits unless the caller passes `type="button"`. The current callers are fine: the only form,
  in `LoginPage`, uses it as its submit button.
