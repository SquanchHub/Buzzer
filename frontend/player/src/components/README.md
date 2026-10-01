# frontend/player/src/components/

Small presentational building blocks for the Player (phone) app. Everything lives in `ui/`;
there are no game-specific components here. The answer buttons, the fill-in-the-blank input
and the recap rows are written inline in `frontend/player/src/pages/game/*.tsx`. None of these
components touch the network, sockets, or global state.

## Files

| File | Purpose |
|---|---|
| `ui/button.tsx` | `Button` — a styled `<button>` with `variant` (`default`, `outline`, `ghost`, `destructive`) and `size` (`sm`, `md`, `lg`); larger touch targets and an `active:scale-95` press effect. |
| `ui/card.tsx` | `Card`, `CardHeader`, `CardContent` — rounded, padded panel wrappers around `<div>`. |
| `ui/input.tsx` | `Input` — a styled `<input>` with phone-sized padding and `text-base`. |
| `ui/TimerBar.tsx` | `TimerBar` — a self-running countdown bar (green → yellow → red) that can be paused. |

## Key entry points

- All exports are named (no default exports). `Button`, `Card*` and `Input` pass through all
  native HTML attributes and merge extra `className` values with `cn()`.
- `TimerBar({ totalSeconds, paused? })`
  - It always starts full at `totalSeconds` and counts down on its own with a 100ms interval
    against a wall-clock end time.
  - `paused` freezes it; when unpaused it resumes from the frozen value.
  - Props are **read once, at mount** (empty dependency list), so `QuestionPage` remounts it
    with `key={currentQuestion.questionId}` for each question.

## Depends on

- `frontend/player/src/lib/utils.ts` — `cn()` (`clsx` + `tailwind-merge`), used by `button`, `card`, `input`.
- npm: `react` (`TimerBar` only). Styling is Tailwind utility classes only.

## Depended on by

- `frontend/player/src/pages/`:
  - `JoinPage.tsx`, `NamePage.tsx` — `Button`, `Input`, `Card*`
  - `game/GameOverPage.tsx` — `Button` (`variant="outline"`)
  - `game/QuestionPage.tsx` — `TimerBar`
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
