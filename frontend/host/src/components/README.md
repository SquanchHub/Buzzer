# frontend/host/src/components/

Presentational building blocks for the Host app: generic primitives in `ui/`, plus two
hotspot components, `HotspotView.tsx` (display) and `HotspotEditor.tsx` (authoring), and two
ordering components, `OrderingView.tsx` (display) and `OrderingEditor.tsx` (authoring). Other
game-specific pieces (charts, word cloud, histogram, question cards) are defined inline inside
the page files in `frontend/host/src/pages/game/`. None of the `ui/` components touch the
network, sockets, or global state; both hotspot components fetch their image via `lib/images.ts`.

## Files

| File | Purpose |
|---|---|
| `ui/button.tsx` | `Button` — Riso Press `<button>` (T9): ink outline and a hard shadow it presses into; `variant` (`default` accent, `outline`, `ghost`, `destructive`) and `size` (`sm`, `md`, `lg`). |
| `ui/card.tsx` | `Card`, `CardHeader`, `CardContent` — `surface` panel with an ink outline and `shadow-hard`. |
| `ui/input.tsx` | `Input` — `<input>` with an ink outline and a 3px `focus` ring. |
| `ui/TimerBar.tsx` | `TimerBar` — a self-running countdown bar (`success` → `warning` ≤ 30% → `danger` ≤ 10%) with mono seconds, that can be paused. |
| `ui/Stamp.tsx` | `Stamp({tone})` — rubber-stamp verdict word (`success`/`warning`/`danger`/`accent`, static class map). |
| `ui/Ticket.tsx` | `Ticket({code, size})` — the room code on a notched ticket stub (`lg`/`md`/`sm`, `data-testid="room-code"`). |
| `ThemeToggle.tsx` | `ThemeToggle({compact?, onSlab?})` — the Paper/Night switch (`role="switch"`, `data-testid="theme-toggle"`), identical in all three apps. |
| `HotspotView.tsx` | `HotspotView` — display-only hotspot `<canvas>` (`docs/plans/t7-hotspot.md` §7.8): image, optional rings, optional taps coloured by band, optional legend; `ringsFromReveal(reveal)` helper. |
| `HotspotEditor.tsx` | `HotspotEditor` — hotspot authoring panel (§7.9, §13.2): Image ID field (or T8 picker slot), canvas preview with live rings, click to place the centre, sliders for the radii and partial fraction. Exports `HOTSPOT_DEFAULT_TARGET`, `HOTSPOT_ASPECT_MIN`/`MAX` and its prop types. |
| `OrderingView.tsx` | `OrderingItems({items})` — the items in display order while a question is open (`data-testid="ordering-host-items"`); `OrderingView({items, correctOrder?, distribution?, meanPositions?, accuracy, invalidKey?, compact?})` — results: correct order, one bar per "k out of place" bucket, and the room's order sorted by mean position (`docs/plans/t7-ordering.md` §6.8). Perfect bucket in `success`, others in `accent` (T9 tokens). |
| `OrderingEditor.tsx` | `OrderingEditor({state, grading, onChange})` — ordering authoring (§6.9): item rows typed in the **correct** order (move up/down, remove, add; 3–6), partial-credit checkbox and a "Players see" preview of the stored shuffle with **Shuffle again**. Pure helpers the page uses: `orderingFromQuestion`, `orderingToPayload`, `orderingProblems`, `shuffleDisplay` (never the identity; "submit as shown" worth ≤ half), `longestRunLength`. Moves keep each item's display slot unless that breaks the shuffle rule. Admin copy: `frontend/admin/src/components/OrderingEditor.tsx`. |
| `ImageThumb.tsx` | `ImageThumb` — shows a stored image (T8) letterboxed in a box: loads it through `lib/images.ts` into a blob URL (revoked on unmount), with Loading… and Image unavailable states. Copied between admin, host and player (the player copy shows option images, T8 D8) — keep the three in sync. |
| `ImagePicker.tsx` | `ImagePicker({courseId, value, onChange, label?})` — choose a question image (T8 §3 contract): the chosen thumbnail with Choose / Change / Remove, and a dialog listing the course's images 24 per page (`listImages`) with **Upload new** (`uploadImage`, selected straight away). Returns only the id; `null` = no image. Escape or a backdrop click closes it. Copied between admin and host — keep in sync. |

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
  - Colours are T9 tokens read with `cssColor()` at draw time (inner `success`, outer `warning`, miss `danger`, neutral `ink-soft`); the draw effect depends on `useTheme()` so a theme toggle repaints. The frame is a `ring` (box-shadow), never a border — a border would shrink the bitmap and offset `getBoundingClientRect()` clicks.

- `HotspotEditor({ config, answerData, onChange, renderImagePicker? })`
  - Controlled: every edit calls `onChange(config, answerData)`; the parent holds the state.
  - **Image-ready signal:** `config.aspectRatio` is sent only once the current `imageId`'s image
    has loaded (`naturalWidth / naturalHeight`) and is dropped whenever `imageId` changes,
    including on mount for a stored question. A parent enables Save on "`aspectRatio` is a number
    in [`HOTSPOT_ASPECT_MIN`, `HOTSPOT_ASPECT_MAX`]" (§13.2 G4). An in-flight load is cancelled
    when the ID changes.
  - Clicks map to fractions of the drawn image, rounded to 4 decimal places; clicks in the
    letterbox bars, or before the image has loaded, are ignored.
  - Inner radius 0.02–0.5 (raising it past the outer radius pushes the outer one up), outer
    radius inner–1, partial fraction 0–1 in steps of 0.05.
  - Imports only `lib/images.ts`, `lib/theme.ts`, `lib/utils.ts` and `components/ui/*` (H9), so the admin copy
    differs only in import paths.

## Depends on

- `frontend/host/src/lib/utils.ts` — `cn()` (`clsx` + `tailwind-merge`), used by `button`, `card`, `input`, `HotspotEditor`.
- `frontend/host/src/lib/images.ts` — `loadImageUrl`, used by `HotspotView` and `HotspotEditor`.
- npm: `react` (`TimerBar` only). Styling is Tailwind utility classes only.

## Depended on by

- `frontend/host/src/pages/`:
  - `LoginPage.tsx`, `CoursePage.tsx`, `RosterPage.tsx` — `Button`, `Input`, `Card*`
  - `HomePage.tsx`, `SessionsPage.tsx` — `Button`, `Card*`
  - `QuestionEditorPage.tsx` — `HotspotEditor`, `OrderingEditor` (+ helpers), `ImagePicker` (prompt, option and hotspot images), `Button`, `Input`, `Card*`
  - `game/LobbyPage.tsx` — `Button`
  - `game/QuestionPage.tsx` — `Button`, `TimerBar`, `HotspotView`, `OrderingItems`, `ImageThumb` (prompt image, option tiles)
  - `game/ResultsPage.tsx`, `game/GameOverPage.tsx` — `Button`, `HotspotView`, `ringsFromReveal`, `OrderingView`, `ImageThumb` (prompt and option thumbnails)
- Nothing outside the host app imports these; the player and admin apps have their own copies.

## Gotchas found while reading

- **Hotspot drawing exists four times.** `HotspotView.tsx` repeats the layout/ring
  maths of `frontend/player/src/components/HotspotCanvas.tsx` (the apps share no code), and
  `HotspotEditor.tsx` repeats `HotspotView`'s image loading and letterbox maths, because the
  editor may import only `lib/images`, `lib/utils` and `ui/` (§13.2). `HotspotEditor` has an
  identical admin copy (`frontend/admin/src/components/`, T4 phase 3). A change to the layout
  rule must be made in every copy.

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
