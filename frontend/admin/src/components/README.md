# frontend/admin/src/components/

Reusable UI primitives for the Admin app, in the shadcn/ui style: small typed wrappers around
native elements that apply a fixed set of Tailwind classes and accept `className` overrides
(merged with `cn` from `lib/utils.ts`), plus composites: `ImageThumb` and `ImagePicker` (T8), and `HotspotEditor` and `OrderingEditor`,
unchanged copies of the host app's components. Pages otherwise build their own tables, forms and panels inline.

## Files

| File | Purpose |
|---|---|
| `ui/button.tsx` | `Button` — `<button>` with `variant` (`default` indigo, `outline`, `ghost`, `destructive` red) and `size` (`sm`, `md`, `lg`). |
| `ui/card.tsx` | `Card`, `CardHeader`, `CardContent` — bordered, rounded, semi-transparent slate panels with padding presets. |
| `ui/input.tsx` | `Input` — full-width text input with slate border/background and an indigo focus ring. |
| `HotspotEditor.tsx` | Hotspot authoring panel (image id, click to place the target, radii, partial credit). **Copy** of `frontend/host/src/components/HotspotEditor.tsx` (T7 H9), identical apart from its header note — keep both in sync. See the host components README for its props and image-ready signal. |
| `OrderingEditor.tsx` | Ordering authoring panel and payload helpers (items in correct order, partial credit, "Players see" shuffle preview). **Copy** of `frontend/host/src/components/OrderingEditor.tsx` (`docs/plans/t7-ordering.md` §6.9), identical apart from its header note — keep both in sync. See the host components README for its props. |
| `ImageThumb.tsx` | `ImageThumb` — shows a stored image (T8) letterboxed in a box: loads it through `lib/images.ts` into a blob URL (revoked on unmount), with Loading… and Image unavailable states. Copied between admin and host — keep in sync. |
| `ImagePicker.tsx` | `ImagePicker({courseId, value, onChange, label?})` — choose a question image (T8 §3 contract): the chosen thumbnail with Choose / Change / Remove, and a dialog listing the course's images 24 per page (`listImages`) with **Upload new** (`uploadImage`, selected straight away). Returns only the id; `null` = no image. Escape or a backdrop click closes it. Copied between admin and host — keep in sync. |

## Key entry points

- `<Button variant? size? {...buttonProps}>` — defaults to `variant="default"`, `size="md"`.
  Disabled buttons get `opacity-50` and no pointer events. Focus shows a 2px ring offset against
  `slate-900`.
- `<Card className?>…</Card>` with optional `<CardHeader>` / `<CardContent>` children.
- `<Input {...inputProps}>` — passes every native input prop through.
- All three spread remaining props onto the native element and let `className` win over the
  defaults via `tailwind-merge`.

## Depends on

- `frontend/admin/src/lib/utils.ts` — `cn`.
- React (types only: `React.ButtonHTMLAttributes`, etc.) and Tailwind CSS.

## Depended on by

- `frontend/admin/src/pages/` — every page imports `Button`, `Card` and `Input`.
  `SessionsPage` uses `Card` without `CardHeader`/`CardContent`.

## Gotchas found while reading

- **Hardcoded dark palette.** Colors are raw Tailwind utilities (`bg-indigo-600`, `border-slate-600`,
  `bg-slate-800/60`, `focus:ring-offset-slate-900`, …). T9's token layer has to replace these here
  first, since every page inherits them.
- **Copied, not shared.** These three files are byte-for-byte identical to
  `frontend/host/src/components/ui/`; the player app's `button.tsx` differs (larger padding,
  `rounded-xl`, `active:scale-95`). Any change — including theming — must be repeated per app.
- **No `select` or `textarea` primitive.** Pages style raw `<select>` and `<textarea>` elements with
  long inline class strings (`QuestionEditorPage`, `GamesPage`, `UserDetailPage`, `RosterPage`), so
  those controls drift from `Input` and will each need theming separately.
- **Focus styles use `focus:` not `focus-visible:`**, so mouse clicks also show the ring. Plain
  `<button>` elements built inline in pages (reorder arrows, role toggles, filter tabs) have no
  styled focus state and rely on the browser's default outline, which is easy to miss on the dark
  background — relevant to T9's visible-focus requirement.
