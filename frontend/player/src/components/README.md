# frontend/player/src/components/

Presentational building blocks for the Player (phone) app: generic primitives in `ui/`, plus
three game-specific components, `HotspotCanvas.tsx`, `OrderingPicker.tsx` and `ImageThumb.tsx` (a stored T8 image), plus `OptionThumbs.tsx`. The answer buttons, the fill-in-the-blank input
and the recap rows are written inline in `frontend/player/src/pages/game/*.tsx`. None of the
`ui/` components touch the network, sockets, or global state; `HotspotCanvas.tsx`'s
`useImageUrl` hook and `ImageThumb` fetch images via `lib/images.ts`.

## Files

| File | Purpose |
|---|---|
| `ui/button.tsx` | `Button` — Riso Press `<button>` (T9): ink outline and a hard shadow it presses into; `variant` (`default` accent, `outline`, `ghost`, `destructive`) and `size` (`sm`, `md`, `lg`) with phone-sized touch targets. |
| `ui/card.tsx` | `Card`, `CardHeader`, `CardContent` — `surface` panel with an ink outline and `shadow-hard`. |
| `ui/input.tsx` | `Input` — `<input>` with phone-sized padding, `text-base` and a 3px `focus` ring. |
| `ui/TimerBar.tsx` | `TimerBar` — a self-running countdown bar (`success` → `warning` → `danger`) with mono seconds, that can be paused. |
| `ui/Stamp.tsx`, `ui/Ticket.tsx` | T9 rubber-stamp verdict and room-code ticket stub (copies of the host's). |
| `ThemeToggle.tsx` | `ThemeToggle({compact?})` — the Paper/Night switch (≥ 44×44 when compact), identical in all three apps. |
| `PageShell.tsx` | `PageShell({hero?})` — pre-game page frame: wordmark + `ThemeToggle` header. |
| `ImageThumb.tsx` | `ImageThumb({ imageId, alt, className? })` — a stored image (T8) letterboxed in a box: loaded through `lib/images.ts` into a blob URL (revoked on unmount or id change), "Loading…" / "Image unavailable" otherwise. Copied from the host's `ImageThumb` (keep in sync). |
| `OptionThumbs.tsx` | `OptionThumbs({ indices, imageIds, size? })` — lettered thumbnails of the options at `indices` that have an image (T8 D8: the player's choice and the correct choice); renders nothing when none has one. |
| `HotspotCanvas.tsx` | `HotspotCanvas` — the hotspot question's `<canvas>` (`docs/plans/t7-hotspot.md` §7.6–7.7), interactive (tap to place a point) or display (rings + own tap); `useImageUrl(imageId)` for display canvases that load their own image. |
| `OrderingPicker.tsx` | `OrderingPicker({items, sequence, onTap, disabled})` — ordering answer UI (`docs/plans/t7-ordering.md` §6.7, O2): full-width buttons in display order that never move; a tapped item shows its position badge (`data-testid` `ordering-item-{d}` / `ordering-badge-{d}`). `OrderingList({items, order, marked?, title, testId})` — read-only numbered list for results, marking out-of-place items. Placed items are `bg-accent text-on-fill`; out-of-place rows get a `warning` border and chip (T9 tokens). |

## Key entry points

- All exports are named (no default exports). `Button`, `Card*` and `Input` pass through all
  native HTML attributes and merge extra `className` values with `cn()`.
- `TimerBar({ totalSeconds, paused? })`
  - It always starts full at `totalSeconds` and counts down on its own with a 100ms interval
    against a wall-clock end time.
  - `paused` freezes it; when unpaused it resumes from the frozen value.
  - Props are **read once, at mount** (empty dependency list), so `QuestionPage` remounts it
    with `key={currentQuestion.questionId}` for each question.

- `HotspotCanvas({ aspectRatio, image, label, interactive?, onPick?, marker?, rings?, maxHeightVh? })`
  - Full container width; height from `aspectRatio`, capped at `maxHeightVh` (default 60).
    The image is **letterboxed** by `aspectRatio`, so layout is fixed before it loads; taps
    in the letterbox are ignored. Backing store is CSS size × `devicePixelRatio`.
  - Points are fractions of the image (0..1, origin top-left). Ring radii are fractions of the
    image's **longer side**, drawn as true circles — what the server scores.
  - `image` is `{status: 'loading' | 'ready' (url) | 'error'}`; `'error'` draws
    "Image unavailable" (rings and marker still draw). `interactive` sets `touch-action: none`.
  - Colours are T9 tokens read with `cssColor()` at draw time (inner `success`, outer `warning`, miss `danger`, neutral `ink-soft`); the draw effect depends on `useTheme()` so a theme toggle repaints. The frame is a `ring` (box-shadow), never a border — a border would shrink the bitmap and offset `getBoundingClientRect()` clicks.

## Depends on

- `frontend/player/src/lib/utils.ts` — `cn()` (`clsx` + `tailwind-merge`), used by `button`, `card`, `input`.
- npm: `react` (`TimerBar` only). Styling is Tailwind utility classes only.

## Depended on by

- `frontend/player/src/pages/`:
  - `JoinPage.tsx`, `NamePage.tsx` — `Button`, `Input`, `Card*`
  - `game/GameOverPage.tsx` — `Button` (`variant="outline"`), `HotspotCanvas`, `OptionThumbs`
  - `game/QuestionPage.tsx` — `TimerBar`, `OrderingPicker`, `Button`, `HotspotCanvas`, `ImageThumb` (option tiles)
  - `game/ResultsPage.tsx` — `OrderingList`, `HotspotCanvas`, `OptionThumbs`
- Nothing outside the player app imports these.

## Gotchas found while reading

- **Late joiners see a full timer bar.** Unlike the host copy, this `TimerBar` has no
  `initialSeconds` prop. For a late joiner the backend rewrites `timeLimitSeconds` to the
  remaining time (min 5s, in `gateway.on_join_room`). The bar therefore starts full with a
  shortened total and does not show how much of the real question time has passed.
- **Timer drift on lock.** The bar ignores the `remainingSeconds` in `question_locked` /
  `question_unlocked`; it just freezes and resumes its own local count, so it can drift from the
  server timer that actually locks answers.
- **Copies drift between apps.** `button`, `card` and `input` differ from the host/admin copies
  (which are identical to each other) only in rounding, padding and the press effect; `TimerBar`
  differs by the missing `initialSeconds`. A bug fix in one copy has to be repeated by hand in
  the others.
- **Mostly unused.** The game screens barely use these components: the answer buttons and the
  fill-in-the-blank input in `QuestionPage` are hand-styled `<button>`/`<input>` elements, and
  no player page uses the `ghost` or `destructive` variants.
- **Timer never stops.** The interval keeps running after reaching 0 until unmount, which is
  harmless.
