# docs/ui/

Screenshots of the apps, referenced from the individual documents (T10). The T8 / T7 hotspot ones
below were captured on 2026-10-05/06 with Playwright (Chrome, headless) during the T8 A5 and A6
verification on `feat/t8-arjun`: desktop 1366 × 900 for the host app, a 390 × 844 phone for the
player app. The images shown are uploaded through the image picker; the hotspot image is the
self-made CC0 test pattern (a coordinate grid with a red dot, a green square and a blue
triangle).

| File | What it shows |
|---|---|
| `t8-hotspot-editor-picker.png` | Host question editor, hotspot question: the prompt-image picker, the hotspot image chosen with the image picker (thumbnail, Change, Remove), the target placed on the red dot, and the inner/outer ring and partial-credit sliders. |
| `t8-host-question-images.png` | Host question screen for a multiple-choice question with a prompt image (large, above the prompt) and option images (tiles; option B is image-only, so it shows only its letter). |
| `t8-hotspot-phone-question.png` | Player phone, hotspot question with the uploaded image: the marker placed on the red dot, Submit enabled. |
| `t8-hotspot-host-results.png` | Host results for that hotspot question: the uploaded image, the target rings, the tap coloured by band, and the band legend. |
| `t8-hotspot-phone-result.png` | Player phone result: "Bullseye!", the player's own tap inside the rings, and the points. |

## T9 theming — `t9/` before / after

Captured on 2026-10-06 by `scripts/ui_screenshots.py` (Playwright, headless Chrome) against the
built apps behind nginx: desktop 1366 × 900 for admin and host, a 390 × 844 phone (2× DPR) for
the player. Each run imports `sample_games/food_fight_party.json` (every question type, with
images) into a fresh course and plays a live game with one host and two phones (Ada, Bo).
Design and rationale: `docs/plans/t9-theming.md` ("Riso Press": Paper light theme, Night dark
theme).

File names are `<tag>-<theme>-<app>-<screen>.png`:

- `before-dark-*` (38): the starter UI on `main`, which had one hard-coded dark palette and
  ignored `prefers-color-scheme`, so there is no "before light".
- `after-light-*` and `after-dark-*` (38 each): the same screens on `feat/t9-theming` in Paper
  and Night. The `after` images are saved as 256-colour PNGs, which keeps the paper grain small.

Recapture with `python scripts/ui_screenshots.py --tag after --themes light,dark`. This needs
`docker compose up -d`, a fresh `npm run build`, and `pip install -r tests/e2e/requirements.txt`.

| Screen | Before | After (Paper / Night) | What changed |
|---|---|---|---|
| Host lobby | `before-dark-host-lobby.png` | `after-light-host-lobby.png` / `after-dark-host-lobby.png` | The room code sits on a notched ticket stub, the QR is in an ink frame with a hard shadow, the player count is a big mono pill, and the theme toggle is in the corner. |
| Phone question (MC) | `before-dark-player-mc-question.png` | `after-light-player-mc-question.png` / `after-dark-player-mc-question.png` | Option tiles in riso inks with halftone dots and inverted letter discs; they press down into their shadow. There is a sticky top bar with the room code and toggle. |
| Host results (MC) | `before-dark-host-mc-results.png` | `after-light-host-mc-results.png` / `after-dark-host-mc-results.png` | Each bar keeps its option's ink (never dimmed), and the answer is marked with a "✓ ANSWER" rubber stamp. |
| Phone results | `before-dark-player-mc-results.png` | `after-light-player-mc-results.png` / `after-dark-player-mc-results.png` | A rubber-stamp verdict, mono points, and Total / Rank cards. |
| Hotspot (host results) | `before-dark-host-hotspot-results.png` | `after-light-host-hotspot-results.png` / `after-dark-host-hotspot-results.png` | The canvas draws from theme tokens and repaints on toggle; the legend swatches use the same tokens. |
| Ordering (phone) | `before-dark-player-ordering-question.png` | `after-light-player-ordering-question.png` / `after-dark-player-ordering-question.png` | Placed items in accent with ink position badges; six items fit on a 375 × 667 phone. |
| Game over (host) | `before-dark-host-gameover.png` | `after-light-host-gameover.png` / `after-dark-host-gameover.png` | "FINAL" stamp, a halftone histogram on one baseline, and mono stat cards. |
| Admin courses | `before-dark-admin-courses.png` | `after-light-admin-courses.png` / `after-dark-admin-courses.png` | Dense outlined rows. The sidebar is an ink slab in Paper and a dark slab with a cream rule in Night; the Paper/Night toggle sits in its footer. |
| Admin question editor | `before-dark-admin-question-editor.png` | `after-light-admin-question-editor.png` / `after-dark-admin-question-editor.png` | Mono chips (Q-number, type, Accuracy / Participation), and literal `·` escapes fixed. |
