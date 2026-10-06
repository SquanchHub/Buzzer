# QA report — `feat/t7-ordering` (ordering question type)

Date: 2026-10-05. Independent browser QA following the `qa-pass` checklist, after the
implementation, the full test run and the `mean-review` fixes.

- **Browser tool:** Python Playwright 1.63, headless Chromium. Phone contexts are 375 × 667 with
  touch; desktop contexts are 1280 × 800.
- **Stack:** `docker compose` (backend, MySQL, Redis, nginx), all healthy. Apps were rebuilt with
  `npm run build` just before the run and served by nginx on port 8080.
- **Roles:** a real non-admin **host** account created for the run, which signs in through the host
  login page; the **admin**, signing in through the admin login page; and two **guest players**
  joining by room code on phones.
- **Origins:** every flow ran on both `http://localhost:8080` and `http://127.0.0.1:8080`.
- **Screenshots:** under [`docs/qa/feat/t7-ordering/`](feat/t7-ordering/), prefixed `localhost-` or
  `127-`. Raw pass/fail results and collected problems are in
  [`qa-results.json`](feat/t7-ordering/qa-results.json).

## Scope

The flows that the ordering work changes:

- authoring in the host and admin editors;
- the host's live question, results and game-over screens;
- the player's answer, results and recap screens;
- the session report.

The branch also carries the not-yet-merged T8 image work, the T4 phase 3 work and
`fix/get-db-commit-timing`, because it was built on top of them. Those were QA'd on their own
branches and are **not** re-tested here; see "Not tested".

## Checklist and results

| # | Flow | Roles | Cross-app | localhost | 127.0.0.1 |
|---|---|---|---|---|---|
| F1 | Sign in, author an ACCURACY ordering question and a COMPLETENESS one in the host editor; refresh mid-flow; re-open and check the typed order is shown | host | — | ✅ | ✅ |
| F2 | Admin edits the same question: move an item, save; stored key maps back to the new order | admin | — | ✅ | ✅ |
| F2b | Admin sidebar "Open Host app" link, plus back and forward | admin | admin → host | ✅ | ✅ |
| F3 | Host creates a room from Home, starts the game, sees items (no stats) while open, refreshes mid-question, reveals results | host | host ↔ player | ✅ | ✅ |
| F4 | Player joins on a phone; every item and Submit is inside the viewport; wrong tap, Undo, partial taps, Reset, full order, Submit | player | player ↔ host | ✅ | ✅ |
| F4b | Second player **reloads mid-question** before answering, then answers with one item moved | player | — | ✅ | ✅ |
| F4c | Results labels: "Perfect order!" and "1 item out of place", with the out-of-place item marked | player | — | ✅ | ✅ |
| F5 | COMPLETENESS round: no correct order on the host, room's order shown, "Answer recorded!" on phones | host, player | — | ✅ | ✅ |
| F6 | Game over: host cards and player recap; player presses Back after game over | host, player | — | ✅ | ✅ |
| F7 | Host downloads the session report (HTML) from Sessions; it contains the ordering sections | host | — | ✅ | ✅ |

**Console and network:** zero console errors, failed requests, HTTP ≥ 400 responses or websocket
errors in any of the 8 browser contexts (4 per origin). There were no CORS or websocket problems on
`127.0.0.1`.

### Screenshots (localhost; the `127-` set matches)

- **Host editor:** [ACCURACY with shuffle preview](feat/t7-ordering/localhost-01-host-editor-accuracy.png) · [COMPLETENESS](feat/t7-ordering/localhost-02-host-editor-completeness.png)
- **Admin:** [admin editor after a move](feat/t7-ordering/localhost-03-admin-editor-after-move.png) · [admin → host link](feat/t7-ordering/localhost-04-admin-to-host.png)
- **Host game screens:** [lobby](feat/t7-ordering/localhost-05-host-lobby.png) · [question open](feat/t7-ordering/localhost-06-host-question-open.png) · [results](feat/t7-ordering/localhost-09-host-results.png) · [COMPLETENESS results](feat/t7-ordering/localhost-12-host-completeness-results.png) · [game over](feat/t7-ordering/localhost-13-host-gameover.png)
- **Player:**
  - Question screens: [question](feat/t7-ordering/localhost-07-player-question.png) · [all tapped](feat/t7-ordering/localhost-08-player-all-tapped.png) ([settled colours](feat/t7-ordering/localhost-08b-player-all-tapped-settled.png))
  - Results: [perfect](feat/t7-ordering/localhost-10-player-results-perfect.png) · [one out of place](feat/t7-ordering/localhost-11-player-results-partial.png)
  - After the game: [recap](feat/t7-ordering/localhost-14-player-gameover.png) · [recap, partial](feat/t7-ordering/localhost-15-player-gameover-partial.png) · [Back after game over](feat/t7-ordering/localhost-16-player-back-after-gameover.png)
- **Report:** [session report](feat/t7-ordering/localhost-17-report.png)

## Bugs

**None found in this QA pass.** No new Playwright tests or fixes were needed.

The bugs found earlier by the adversarial `mean-review` were fixed before QA. Each fix is its own
commit, and the e2e tests cover the user-visible ones:

| Symptom | Root cause | Fix commit |
|---|---|---|
| Editor froze on a question whose stored item list was corrupted to 0–1 items | The reshuffle `useEffect` re-fired forever, because no non-identity order of fewer than 2 items exists | `46b712a` |
| Editor showed "partial credit" for a stored key missing `partialCredit`, which the server scores as invalid | The client key check was weaker than the server's | `46b712a` |
| After a reload, the player's results said "No answer" next to earned points | The label only looked at local `lastAnswerData`, not the server's `yourOrdering` | `aa6e4c6` |
| Recap cut a 6-item answer to its first item | The shared "Your answer" span used `truncate` | `aa6e4c6` |
| Item buttons were 48 px, not the specified 56 px | `min-h-12` instead of `min-h-14` (the no-scroll e2e check still passes at 56 px) | `aa6e4c6` |

## Observed, judged not to be bugs in this branch

- **Two tapped items look unselected in [all tapped](feat/t7-ordering/localhost-08-player-all-tapped.png).**
  The screenshot was taken during the 150 ms `transition-colors` animation. Once settled, all four
  items read `rgb(79, 70, 229)` (the selected colour); see the
  [settled screenshot](feat/t7-ordering/localhost-08b-player-all-tapped-settled.png).
- **Pressing Back after game over shows the last results page with "Waiting for next question…"**
  ([screenshot](feat/t7-ordering/localhost-16-player-back-after-gameover.png)).
  - This is **pre-existing** and the same for every question type: `ResultsPage` is shared, and the
    player router lets Back return to `/results` after `game_over`. This branch only added the
    ordering label to that page.
  - Nothing breaks (no errors, and the score is right), but it is misleading. It should be a
    separate fix on its own branch, because it touches the shared player routing.
- **"+0.67 pts" on the partial-credit phone.** That is correct for the editor's default
  `points_value` of 1: one item out of place out of four earns (3 − 1)/(4 − 1) = 0.67.

## Not tested, and why

- **T8 image flows, T4 phase 3 admin pages and `fix/get-db-commit-timing`.** They are in this
  branch's diff against `main` only because the branch is built on them. Their own branches carry
  their tests and QA, and this branch did not change them. Ordering with a T8 **prompt image** is
  covered by integration test 13.
- **Real phones (iOS Safari, Android Chrome).** Only Chromium's mobile emulation was used, so
  real-device tap behaviour and safe-area insets are untested.
- **Auto-advance mode and question timer expiry with no answer.** These are existing behaviour that
  ordering doesn't change; the integration suite covers expiry in `--fast` mode.
- **Late joiners mid-question** (spec §11 risk). They get the existing shortened timer, which this
  branch doesn't change.
