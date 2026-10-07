# T6 — Vincent's sample games: "Reading the Data" (classroom) and "Food Fight" (party)

Status: **plan agreed; Goldfish-tested and fact-checked 2026-10-05, revised (§8).** Owner: Vincent Zhou. Branch: `content/t6-games-vincent`
(from `main` after T7 ordering, T8 and Arjun's T6 games merged).

## 1. Problem

T6 (`instructions.md`) asks each team member for two game JSON files under `sample_games/`:
one classroom game (educational, professional tone) and one party game (fun, broadly
accessible). The rules:

| Requirement | How these games meet it |
|---|---|
| Every original type in **each** game: `multiple_choice`, `true_false`, `fill_in_the_blank`, `multi_select` | Both games have ≥ 1 of each (§4 matrix) |
| Both grading modes in **each** game | Both games mix ACCURACY and COMPLETENESS |
| One classroom and one party game per member | Reading the Data = classroom; Food Fight = party |
| The team's new types (T7) in at least one game per member | **Both** games have `hotspot` and `ordering` questions. That is stricter than required, so the "every supported type" wording can't be read against us |
| Conform to the schema and import cleanly (Admin UI or API) | Built through the API and exported by the server, then checked by a dedicated integration test, the existing per-sample import tests and a browser QA pass |
| Ship `"version": 1`, or bump if T8 extends the format, as long as unmodified v1 files still import | Both are **version 2**: hotspot needs its image, and v1 bundles with hotspot are rejected (T8 D7). The 14 existing v1 files stay untouched and keep importing (existing tests) |
| New, distinctly named files committed under `sample_games/` | `sample_games/reading_the_data_stats.json`, `sample_games/food_fight_party.json` |

## 2. Approach

1. **Images are self-made**, drawn with Pillow by a generator script, so there are no licensing
   questions (hotspot H10's rule). Each is small (< 100 KB) and has the exact aspect ratio stored
   in its hotspot config.
2. **Build through the real app, then export.** The generator script creates a course and game
   through the admin API, uploads the images, creates every question (so the server validates
   each one with `QuestionCreate`), exports the game with `GET /api/admin/games/{id}/export`, and
   writes the bundle to `sample_games/`. It then deletes the temporary game. This is the
   recommended "author in the app, then export" path: the server writes the v2 `images` block
   and the `imageRef`s, so they can't be hand-written wrong. The ordering display shuffles are
   chosen in the plan (§4) and checked against O3's fairness rule ("submit as shown" earns at
   most half).
3. **Test-first:** `tests/integration/test_sample_games_vincent.py` encodes the §1 requirements
   for both files (types, grading modes, new types, version, distinct titles) and imports each
   file through the host and admin routes, then plays the ordering and hotspot questions over
   Socket.io with known answers. It is written and fails before the files exist.
4. **The generator stays out of the repo** (scratchpad). The committed bundles are the artifact,
   and the images inside them are the only copy reviewers need.

Points scale: the classroom game uses **1–3 points** per question, matching Arjun's classroom
game (World Geography uses a 1–2 point scale so the CSV maps onto Canvas grades). The party game
uses **50–300 points**, like Wild Kingdom.

## 3. Images (self-drawn)

The generator draws every image with Pillow, and the hotspot target comes from the same numbers
used to draw it. Each image shows **numbers and axes only, never the answer** (no pepper names or
markers). Source fonts are ≥ 22 px, so labels stay at least about 9 px tall on a 375 px phone.
Every 1-D scale has a thin bar, so a tap at the right value anywhere across the bar scores full
points: the inner radius covers the half-range along the axis combined with the bar's half-width.

| Id | Image | Size | Drawing | Target |
|---|---|---|---|---|
| A | Scatter plot | 800 × 500 | Plot area x 70–770, y 30–440. 30 points: x ~ U(5, 95), y = 15 + 0.75x + N(0, 5), seed 7. **Outlier** at data (80, 18), about 57 below the trend. | The outlier's centre (the generator prints the pixel coordinates); inner 0.035 (28 px), outer 0.07 |
| B | Horizontal box plot | 900 × 360 | Axis 0–100 at x 60–840 (7.8 px per unit), ticks every 10. Whiskers 12–95, Q1 35, **median 48**, Q3 70; box half-height 28 px. | The median line's centre; inner 0.035 (31.5 px), which covers the whole drawn line (28 px half-height). Outer 0.07 (63 px). Q1 is 101 px away, so a quartile tap misses |
| C | Scoville scale (log) | 1000 × 300 | Axis 1 to 10M SHU at x 60–940 (125.7 px per decade); labels 1, 10, 100, 1K, 10K, 100K, 1M, 10M; green-to-red bar, half-height 15 px | **Jalapeño 4,500 SHU** (log₁₀ 3.65, the geometric middle of 2,500–8,000; ±0.25 decades = ±31.4 px); inner 0.035 (35 px ≥ √(31.4² + 15²)), outer 0.08 |
| D | Thermometer, **horizontal** | 1000 × 300 | 0–250 °C at x 80–920 (3.36 px per °C), ticks every 25 °C, labels every 50 °C with °F underneath; tube half-height 14 px | **182.5 °C**, the middle of the 175–190 °C (350–375 °F) deep-fry range: ±7.5 °C = ±25.2 px; inner 0.03 (30 px ≥ √(25.2² + 14²)), outer 0.07 |

All hotspot questions use `partialFraction` 0.5.

## 4. Questions

### Game 1 — "Reading the Data" (classroom, intro statistics)

Description: "Reading charts and summarising data: centre, spread, correlation and the logic of
a hypothesis test. Suitable as an in-class review for an introductory statistics course."

| # | Type | Grading | Prompt | Answer | Pts | s |
|---|---|---|---|---|---|---|
| 1 | multiple_choice | ACCURACY | Points rise steadily from lower left to upper right, tightly clustered around a straight line. Which correlation coefficient fits best? | −0.9 / 0.0 / 0.3 / **0.9** | 1 | 25 |
| 2 | hotspot | ACCURACY | Tap the outlier in this scatter plot. | Image A | 2 | 25 |
| 3 | true_false | ACCURACY | A correlation of 0.9 between two variables proves that one causes the other. | **False** | 1 | 15 |
| 4 | ordering | ACCURACY, partial credit | Order these data sets from smallest to largest standard deviation. | {5, 5, 5, 5} → {4, 5, 5, 6} → {1, 5, 5, 9} → {−10, 0, 10, 20} | 2 | 40 |
| 5 | multi_select | ACCURACY | Which of these are measures of centre? Select all that apply. | **Mean, Median, Mode** (+1 each); Range, Standard deviation, Interquartile range (−1 each) | 3 | 25 |
| 6 | hotspot | ACCURACY | Tap the median of this box plot. | Image B | 2 | 20 |
| 7 | fill_in_the_blank | ACCURACY | The middle value of a sorted data set is called the ___. | **median** (1 typo allowed) | 1 | 20 |
| 8 | true_false | ACCURACY | The median is more resistant to outliers than the mean. | **True** | 1 | 15 |
| 9 | ordering | ACCURACY, partial credit (textbooks differ on steps 1–2) | Put the steps of a hypothesis test in order, first to last. | State the null and alternative hypotheses → Choose a significance level → Collect data and compute the test statistic → Find the p-value → Compare the p-value with α and decide | 2 | 45 |
| 10 | multiple_choice | ACCURACY | A data set has a mean of 50 and a median of 42. Its distribution is most likely… | **Skewed right** / Skewed left / Symmetric / Uniform | 1 | 20 |
| 11 | fill_in_the_blank | ACCURACY | The distance from the first quartile to the third quartile is called the ___. | **interquartile range**, **inter-quartile range**, **IQR** (1 typo allowed) | 2 | 25 |
| 12 | multiple_choice | COMPLETENESS | Which chart type do you find easiest to read? | Bar chart / Histogram / Box plot / Scatter plot | 1 | 20 |
| 13 | fill_in_the_blank | COMPLETENESS | In one or two words, which statistics topic would you like to review next? | any | 1 | 30 |

Ordering display orders (stored `config.items`; checked against O3: not the identity, and the
display order submitted as-is scores at most half):
- Q4: shown as {1, 5, 5, 9}, {−10, 0, 10, 20}, {5, 5, 5, 5}, {4, 5, 5, 6} → `correctOrder`
  [2, 3, 0, 1]; as shown r = [2, 3, 0, 1], L = 2 → 1/3 ✓.
- Q9 (5 items, stored exactly as in the answer column): shown as "Find the p-value", "State the
  null and alternative hypotheses", "Compare the p-value with α and decide", "Collect data and
  compute the test statistic", "Choose a significance level" → `correctOrder` [1, 4, 3, 0, 2]; as
  shown r = [3, 0, 4, 2, 1], L = 2 → 1/4 ✓.
- Q4's negative number uses the Unicode minus "−" (display only; players tap, never type).

Standard deviations for Q4 (population): 0, 0.71, 2.83, 11.18. The order holds for the sample
SD too.

### Game 2 — "Food Fight" (party)

Description: "Spicy peppers, deep fryers, pesto and the great pineapple debate. A food quiz for
anyone who eats."

| # | Type | Grading | Prompt | Answer | Pts | s |
|---|---|---|---|---|---|---|
| 1 | multiple_choice | ACCURACY | Which of these "nuts" is actually a legume? | **Peanut** / Almond / Cashew / Walnut | 100 | 15 |
| 2 | ordering | ACCURACY, partial credit | Order these peppers from mildest to hottest. | Bell pepper → Jalapeño → Cayenne → Habanero → Carolina Reaper | 300 | 35 |
| 3 | true_false | ACCURACY | White chocolate contains no ingredient from the cocoa bean. | **False** (it is made with cocoa butter) | 100 | 15 |
| 4 | hotspot | ACCURACY | On this heat scale, tap where a jalapeño pepper sits. | Image C | 250 | 25 |
| 5 | multi_select | ACCURACY | Which of these go into a classic Genovese pesto? Select all that apply. | **Basil, Pine nuts, Garlic** (+100 each); Tomato, Cream, Mayonnaise (−100 each) | 300 | 25 |
| 6 | fill_in_the_blank | ACCURACY | Pasta cooked so it is still firm to the bite is called "al ___". | **dente**, **al dente** (1 typo allowed) | 200 | 20 |
| 7 | true_false | ACCURACY | In the 1830s, tomato ketchup was promoted in the US as a medicine. | **True** (Bennett's tomato cures; tomato "pills" followed) | 100 | 15 |
| 8 | hotspot | ACCURACY | Tap the classic deep-frying temperature on this thermometer. | Image D | 250 | 25 |
| 9 | fill_in_the_blank | ACCURACY | Which spice, made from crocus flowers, is the most expensive in the world by weight? | **saffron** (1 typo allowed) | 200 | 20 |
| 10 | multiple_choice | ACCURACY | Which fruit wears its "seeds" on the outside? | **Strawberry** / Kiwi / Banana / Mango | 100 | 15 |
| 11 | ordering | COMPLETENESS | Rank these pizza toppings, favourite first. | (opinion; the host shows the room's ranking) Pepperoni, Mushrooms, Pineapple, Olives, Extra cheese | 100 | 30 |
| 12 | multiple_choice | COMPLETENESS | Pineapple on pizza? | Yes, obviously / Absolutely not / Only ironically / I'm calling the police | 50 | 15 |
| 13 | fill_in_the_blank | COMPLETENESS | Name your ultimate comfort food. | any | 50 | 25 |

Ordering display order:
- Q2: shown as Habanero, Bell pepper, Carolina Reaper, Jalapeño, Cayenne → `correctOrder`
  [1, 3, 4, 0, 2]; as shown r = [3, 0, 4, 1, 2], L = 3 (0, 1, 2) → 2/4 = 0.5 ✓ (exactly half).
- Q11 (COMPLETENESS): items in the listed order; there is no key.

Pepper ranges (SHU), which don't overlap: bell 0; jalapeño 2,500–8,000; cayenne 30,000–50,000;
habanero 100,000–350,000; Carolina Reaper ~1.5–2.2 million.

### Scoring data conventions (both games)

- **MC:** `answer_points` gives `points_value` to the key and 0 to the other options. Under
  COMPLETENESS, `answer_data` is `{}`.
- **TF:** `answer_points` `{"true": …, "false": …}`, with `points_value` on the key and 0 on the
  other.
- **FITB:** `acceptedAnswers` as listed, `answerPoints` equal to `points_value` for each, and
  `editDistance` 1. Matching is case-insensitive and whitespace-normalised (`calculate_score`), so
  no case variants are needed. COMPLETENESS FITB uses `{}` and `config.maxLength` 60.
- **MS:** `answer_points` +k on correct options and −k on the others; `points_value` is the sum
  of the positive ones.
- **Ordering:** `partialCredit` **true** on all three ACCURACY ordering questions (classroom Q4
  and Q9, party Q2). COMPLETENESS Q11 has `answer_data` `{}`.
- **Game metadata:** `max_players` 150 for both, with the descriptions given above.

### Requirements matrix

| | MC | TF | FITB | MS | Hotspot | Ordering | ACCURACY | COMPLETENESS |
|---|---|---|---|---|---|---|---|---|
| Reading the Data | 3 | 2 | 3 | 1 | 2 | 2 | 11 | 2 |
| Food Fight | 3 | 2 | 3 | 1 | 2 | 2 | 10 | 3 |

## 5. Tests

`tests/integration/test_sample_games_vincent.py`, written first:
1. **Requirements**, per file: `format`/`version` 2, title present and distinct from every other
   sample file, every type in {MC, TF, FITB, MS, hotspot, ordering} at least once, both grading
   modes, each hotspot's `imageRef` names an `images` entry, and no raw `imageId` anywhere.
2. **Imports cleanly** through `POST /api/host/games/import` and `/api/admin/games/import`; the
   imported question count matches; the imported hotspot images exist in the target course.
   Imported images are deleted on teardown.
3. **Plays correctly:** import into a course, run the game over Socket.io, and answer each
   hotspot at its target and each ordering question with its correct order. Every one of those
   scores full points, which proves the keys and image coordinates line up after a round trip.

The existing parametrised tests (`test_course_games.py`, `test_hotspot.py` test 14) also import
every `sample_games/*.json` file, so the new files join them automatically.

## 6. Alternatives considered

| Alternative | Why not |
|---|---|
| Hand-write the JSON, including base64 images | Error-prone. The server's own exporter writes exactly the format its importer reads |
| Commit the generator script | Not a requirement, and it adds a code path nobody maintains. The bundles are self-contained |
| Photos or clip-art for food hotspots | Licensing, plus large files. Drawn scales are small, exact and teach something |
| Version 1 files with only ordering as the new type | They would skip hotspot, the team's canvas type. Both new types are better shown in both games |
| T8 prompt images (e.g. a chart in Q1's prompt) | Prompt images are not yet shown on the live screens on `main` (that work is in Arjun's unmerged `feat/t8-arjun`), so players couldn't see them. Q1 describes the chart in words |

## 7. Risks

- **Fact errors** in a committed teaching artifact. Mitigation: a fresh-context fact check of §4
  before building (§8).
- **Hotspot rings too tight on a phone.** The smallest inner radius is 0.025 of the longer side
  (B: ≈ 9 px on a 375 px-wide phone, D: about 0.025 × 1000 scaled to the screen height). The QA
  pass taps on a phone-sized viewport, and the ring sizes get adjusted if they prove unfair.
- **Image D is tall (aspect 0.3)**, so on a phone it is letterboxed by height. The QA pass checks
  that it stays readable.
- **Opinion questions under COMPLETENESS score full points for anyone who answers,** by design.

## 8. Goldfish test and fact check (2026-10-05)

A fresh-context subagent checked commit 16e66d8 against the requirements, recomputed every
ordering check and both SD orders, and fact-checked every ACCURACY question. It confirmed the
requirements matrix and found no wrong keys. Four items were blocking:

a. **Food Q3 (white chocolate):** "cocoa solids" is contested (EU labelling counts cocoa butter).
   Reworded to "contains no ingredient from the cocoa bean" → False.
b. **Food Q5 (pesto):** "Butter" could be argued (Hazan's and older Ligurian recipes include it).
   Replaced with "Mayonnaise".
c. **Image B:** a tap on the drawn median line could fall outside the inner ring. The box
   half-height is now 28 px, with inner 0.035 (31.5 px).
d. **Images C and D:** a tap at the right value but off the bar's centreline lost points. Both now
   pin the bar thickness, axis extent and centre, with inner radii computed to cover the full
   range (§3). Image D is now horizontal, for legible labels on a phone.

Non-blocking items, all applied:
- Food Q7 reworded to "promoted … as a medicine".
- The deep-fry target moved to 182.5 °C, covering 175–190 °C.
- Classroom Q9 now gives partial credit.
- Added "al dente" and "inter-quartile range" as accepted answers.
- Exact item strings and the Unicode minus are stated.
- Scoring conventions are written out.
- Images carry numbers only, with minimum font sizes.
- The scatter seed, trend and outlier are given.
- "seeds" is in quotes in Food Q10.

The generator deletes its temporary game and images. Its build course stays behind as an inert
row, because courses have no delete endpoint.

**Image provenance (hotspot H10):** all four images are drawn by the generator from the
parameters in §3. There are no third-party assets and no licensing questions.

**Outside this plan:** Arjun's two T6 games (World Geography, Wild Kingdom) are version 1 and
contain no hotspot or ordering questions. T6 requires each member to have at least one game that
uses each new type, so his set still needs one.
