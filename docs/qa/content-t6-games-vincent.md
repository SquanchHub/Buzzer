# QA report — `content/t6-games-vincent` (T6 sample games)

Date: 2026-10-05. An independent browser QA pass following the `qa-pass` checklist, covering
Vincent's two new games, `sample_games/reading_the_data_stats.json` (classroom) and
`sample_games/food_fight_party.json` (party).

- **Tools:** Python Playwright 1.63 (headless Chromium). Phones are 375 × 667 with touch; desktop
  is 1280 × 800.
- **Stack:** `docker compose` with all services healthy, serving apps rebuilt from this branch
  (`npm run build`) through nginx on port 8080.
- **Origins:** every flow ran on both `http://localhost:8080` and `http://127.0.0.1:8080`.
- **Roles:**
  - the **admin**, signing in through the admin login page;
  - a real non-admin **host** created for the run (HOST on a fresh course), signing in through the
    host login page;
  - two **guest players** on phones: **Ada** answers every question correctly, **Bo** answers every
    question wrongly.
- **Evidence:** screenshots in [`content/t6-games-vincent/`](content/t6-games-vincent/), a
  representative subset of 111 captured. Raw results are in
  [`qa-results.json`](content/t6-games-vincent/qa-results.json).

## Checklist and results

| # | Flow | Roles | Cross-app | localhost | 127.0.0.1 |
|---|---|---|---|---|---|
| F1 | Admin imports **Reading the Data** through the Admin UI (Games → course → Import JSON); the question list renders the ordering items | admin | — | ✅ | ✅ |
| F2 | Host imports **Food Fight** through the Host UI (course page → Import JSON) and lands in the editor; the imported hotspot question opens in the editor and its image loads from the imported bytes | host | — | ✅ | ✅ |
| F3 | Host creates a room from Home and plays **Food Fight** end to end (13 questions); Ada and Bo answer on phones; host reveals each question | host, player | host ↔ player | ✅ | ✅ |
| F4 | The same for **Reading the Data** (13 questions). The host needed a game grant first: an admin-imported game is admin-only until granted, as designed in T4 | host, player, admin | host ↔ player | ✅ | ✅ |
| F5 | Host downloads the session report (Sessions → Download summary (HTML)); it has the Hotspot and Ordering sections | host | — | ✅ | ✅ |

**Scoring:**
- Across both games and both origins, 104 phone answers each scored exactly what the answer key
  says. Ada got full points on every ACCURACY question (both hotspots per game hit the inner ring;
  every ordering was "Perfect order!"). Bo got 0 on every ACCURACY question (hotspots "Miss",
  reversed orders 0). COMPLETENESS questions gave both players full points.
- This also confirms that the hotspot targets in the imported bundles line up with the drawn
  images, and the ordering keys with their stored shuffles.

**Console and network:** in the final, fully passing run there were zero console errors, failed requests or HTTP
≥ 400 responses across all 12 browser contexts (6 per origin).

### Screenshots (localhost unless marked)

- **Imports:**
  - Admin import: [game list](content/t6-games-vincent/localhost-01-admin-imported-classroom.png) · [question list](content/t6-games-vincent/localhost-02-admin-classroom-questions.png)
  - Host import: [editor after import](content/t6-games-vincent/localhost-03-host-imported-party-editor.png) · [imported hotspot in the editor](content/t6-games-vincent/localhost-04-host-editor-hotspot.png)
  - Same flows on 127.0.0.1: [admin](content/t6-games-vincent/127-01-admin-imported-classroom.png) · [host](content/t6-games-vincent/127-03-host-imported-party-editor.png)
- **Reading the Data:**
  - Outlier hotspot: [phone](content/t6-games-vincent/localhost-classroom-q02-phone-hotspot-tapped.png) · [host results](content/t6-games-vincent/localhost-classroom-q02-host-results.png)
  - SD ordering: [phone](content/t6-games-vincent/localhost-classroom-q04-phone-ordering.png) · [host results](content/t6-games-vincent/localhost-classroom-q04-host-results.png)
  - Median hotspot: [phone](content/t6-games-vincent/localhost-classroom-q06-phone-hotspot-tapped.png) · [host results](content/t6-games-vincent/localhost-classroom-q06-host-results.png)
  - Hypothesis-test ordering: [phone](content/t6-games-vincent/localhost-classroom-q09-phone-ordering.png) · [host results](content/t6-games-vincent/localhost-classroom-q09-host-results.png)
  - Game over: [host](content/t6-games-vincent/localhost-classroom-zz-host-gameover.png) · [phone](content/t6-games-vincent/localhost-classroom-zz-phone-Ada-gameover.png)
- **Food Fight:**
  - Pepper ordering: [phone](content/t6-games-vincent/localhost-party-q02-phone-ordering.png) · [host results](content/t6-games-vincent/localhost-party-q02-host-results.png)
  - Scoville hotspot: [phone](content/t6-games-vincent/localhost-party-q04-phone-hotspot-tapped.png) · [host results](content/t6-games-vincent/localhost-party-q04-host-results.png)
  - Deep-fry hotspot: [phone](content/t6-games-vincent/localhost-party-q08-phone-hotspot-tapped.png) · [host results](content/t6-games-vincent/localhost-party-q08-host-results.png)
  - Pizza poll: [phone](content/t6-games-vincent/localhost-party-q11-phone-ordering.png) · [host room ranking](content/t6-games-vincent/localhost-party-q11-host-results.png)
  - Game over: [host](content/t6-games-vincent/localhost-party-zz-host-gameover.png) · [phone](content/t6-games-vincent/localhost-party-zz-phone-Ada-gameover.png)
- **Wrong-answer phone (Bo):** e.g. [Scoville miss](content/t6-games-vincent/localhost-party-q04-phone-Bo-results.png) · [reversed order](content/t6-games-vincent/localhost-classroom-q04-phone-Bo-results.png)
- **Report:** [session report](content/t6-games-vincent/localhost-05-report.png)

## Bugs in this branch

**None.** The games imported, played and scored exactly as specified on both origins. No
Playwright regression tests or fixes were needed.

## Problems hit during QA, and why they are not bugs in this branch

1. **QA driver bugs (fixed in the driver, not the app).**
   - "0.9" substring-matched the "−0.9" option, so the driver tapped the wrong answer.
   - Admin-imported games need a game grant before a non-admin host can run them, which is T4's
     access model working as designed.
2. **Pre-existing player socket race (intermittent, not caused by this branch).** In early runs the
   driver answered about 30 ms after each question appeared. Two things then happened:
   - An answer was occasionally lost: "Answer submitted" never received `answer_received`, and a
     correct answer showed +0 pts.
   - Once, a phone was stranded on the results screen when the next question started.

   The websocket trace showed `new_question` arriving **twice** per question for each player. That
   is the documented gotcha in `frontend/player/src/pages/README.md`: "The socket reconnects on
   every page change", plus "Reconnect gaps" (`sync_state`'s `currentQuestion` is ignored). An
   answer or `new_question` that lands during the reconnect window is lost.

   Answering at human speed (1.2 s after the question appears) stopped the lost answers. The
   **stranded phone still happened once at human speed**: on 127.0.0.1, after the Food Fight Q8
   results, one phone never got question 9. The final full run on both origins was clean, and a
   single-player trace at full speed scored all 12 answered questions correctly. So the race is
   intermittent and **can affect real players**, but neither symptom comes from the game files.

   **Not fixed here:** it lives in `GameLayout`'s shared socket effect (`[code, navigate]`
   dependencies), affects every question type, and has nothing to do with game content.
   **Recommended:** a separate fix branch that keeps one socket for the whole game, with a Playwright
   test that answers immediately after `new_question`.

## Observations (not bugs)

- **Small labels on phones.** On a 375 px phone, the 1-D scale images (thermometer, Scoville, box
  plot) render about 343 px wide, so their axis labels are about 8–10 px tall
  ([thermometer](content/t6-games-vincent/localhost-party-q08-phone-hotspot-tapped.png)).
  They are legible and taps land accurately, and the host screen shows them large. A future
  revision could use fewer, bigger labels.
- **The host results ring overlay** (inner and outer rings) makes each hotspot's scoring tolerance
  visible to the room, e.g. the Scoville inner ring covers about 2.5K–8K SHU.

## Not tested, and why

- **Real phones** (iOS Safari, Android Chrome): only Chromium's mobile emulation was used.
- **Auto-advance and timer expiry.** These are existing behaviour that the content doesn't change.
- **T8 prompt images on the live screens:** that work is in Arjun's unmerged `feat/t8-arjun`, and
  these games deliberately use no prompt images (plan §6).
