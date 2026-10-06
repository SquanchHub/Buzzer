# T7 — Ordering question type (tap items into sequence, partial credit by longest in-order run)

Status: **agreed design; goldfish-tested 2026-10-05 and revised** (§13 lists what the revision
changed). Owner: Vincent Zhou.
Branch: `feat/t7-ordering`. This is the team's second T7 type; the canvas-based one is hotspot
(`docs/plans/t7-hotspot.md`, Arjun Kaneriya, implemented). Ordering has no blockers: T4 (host and
admin editors, `content_service`) and T8 (images, bundle version 2) are both on this branch.

Read with the context hierarchy: `backend/app/README.md` (its "Adding a question type touches"
list is the backbone of §6), `frontend/README.md`, and the per-directory READMEs they link
(`backend/app/{schemas,services,websocket}/README.md`,
`frontend/{host,player,admin}/src/{pages,components,lib}/README.md`). Hotspot is the model this
design copies wherever the problems are the same. Where it says "as hotspot", the hotspot code
on this branch is the reference.

## 1. Problem

T7 needs two new question types. One suits a classroom and one a party, and each needs a
deliberate scoring approach. **Ordering** is "put these items in the right order". The author
writes 3–6 short items in their correct order. Every player sees the same shuffled list on their
phone, taps the items in the order they think is right, and confirms. The server scores the
submitted order. Teachers already quiz this way: history timelines ("earliest first"), process
steps (phases of mitosis, stages of the water cycle) and algorithm steps (the steps of a merge
sort). The same mechanic works at a party ("order these films by release year") and, under
COMPLETENESS, as an opinion ranking that has no right answer ("rank these pizza toppings").

The type is a full vertical slice: validation (symmetric on create and update), scoring, live
payloads, the player UI, host live and results views, authoring in both the host and admin
editors, export/import (v1 and v2), the HTML report, the simulator, the engine mirror,
integration tests, unit tests, browser e2e tests and sample games.

## 2. Technical plan (summary)

1. **No migration.** `questions.type` is a free string and `config` / `answer_data` are
   schemaless JSON (`backend/app/models/README.md`). The new type string is `ordering`.
2. **`config`** (sent to clients) is exactly `{ items: string[] }`: 3–6 plain-text items **in
   display order**, the shuffled order every player sees. **`answer_data`** (server-only) under
   ACCURACY is exactly `{ correctOrder: int[], partialCredit: bool }`. `correctOrder[k]` is the
   display index of the item that belongs in position *k*, and it must never equal the identity
   permutation, so the shuffled display order never shows the answer.
3. **The shuffle is done when the question is authored and stored** in `config.items` (§3 O3).
   `_question_payload` already sends `config` unchanged and never sends `answer_data`, so the
   correct order stays server-only with no new code.
4. **The player submits** `{ order: int[] }`, the display indices in the chosen order. It must be
   a full permutation of `0..n-1`, and the gateway rejects anything else.
5. **Scoring (ACCURACY):** let `L` be the length of the longest run of submitted items that are
   in correct relative order (longest increasing subsequence of correct ranks). The *n − L*
   other items are the minimum number the player would have to pick up and move ("items out of
   place"). Exact order gives full points and `is_correct = true`. Otherwise, with
   `partialCredit` the player gets `round(points_value × (L − 1)/(n − 1), 2)`; without it, 0.
   `is_correct` always means "exact order".
6. **COMPLETENESS stays participation credit** (the existing early return): any valid full order
   earns full points, there is no correct order, and the reveal is `{type: "completeness"}`. This
   corrects the original brief (§3 O5).
7. **Shared helpers in `game_service`**, as for hotspot: `ordering_key` (parses stored
   data, returns `None` and logs on bad data, never raises), `ordering_item_count`,
   `ordering_submission`, `ordering_result`, `ordering_points`, `ordering_reveal`,
   `ordering_outcome`, `ordering_dist_key`, `ordering_mean_positions`. Scoring,
   `record_answer`, both summaries, the gateway and `report_service` all call these. There is no
   second copy of the rules. The validation rules live once, in `schemas/admin.py`
   (`ordering_config_error`, `ordering_answer_error`), and `ordering_key` reuses them.
8. **Results:** the host sees the correct order, a "how many out of place" distribution and the
   room's average order (mean position per item, under both gradings). Each player sees their
   own `yourOrdering` (items in order, items out of place), computed by the server.
9. **Authoring:** a self-contained `OrderingEditor` component in the host app, copied into the
   admin app with only the import paths changed (the hotspot H9 pattern). The author types the
   items in correct order, and the editor makes and previews the display shuffle.
10. **Export/import needs no new format.** Ordering has no image fields of its own, so a game
    whose only images are T8 prompt images still round-trips through the existing v1/v2 code.
    Tests prove both versions.
11. **Browser e2e tests** in a new `tests/e2e/` (Python Playwright) run against the live Docker
    stack: author in the admin app, play on a phone-sized viewport, check the reveal on the host.

## 3. Decisions (with rationale)

### O1. Type string `ordering`, classroom-first, not canvas
Hotspot already meets the canvas requirement, so ordering uses plain buttons. Plain buttons are
also easier to use and more accessible on a phone than a canvas. The design starts from a subject
teacher: sequences are how history, biology and CS are actually taught ("what comes next?"), and
one question is answered in under 30 seconds. **(User decision.)**

### O2. Tap-in-sequence, not drag-and-drop
The player taps items in the order they believe is right. Each tapped item shows its position
number (1, 2, 3, …). **Undo** removes the last tap and **Reset** clears all of them. **Submit
order** is enabled only when every item has a number. On small phones, drag-and-drop is the
riskiest UI piece: scroll fights the drag, the drop target sits under the thumb, and accessibility
is poor. Tapping uses only full-width `<button>`s, which get keyboard and screen-reader support
for free. **(User decision.)**

Details decided here:
- **Items never move when tapped.** The list stays in display order and only the badges change,
  so nothing jumps under the thumb between taps.
- **Tapping an item that already has a number does nothing.** The only ways to change the order
  are Undo and Reset. Renumbering later items after a mid-sequence removal would be confusing.
  A one-line hint says "Use Undo to change your order".
- **The last item is not filled in automatically.** It is forced, but auto-filling it would make
  Undo ambiguous (does it undo one tap or two?). It costs one extra tap.

### O3. Same shuffled order for everyone; never the correct order; stored at authoring time
**(User decision: same order for all, never the correct order.)** This design decides where the
shuffle happens: **the editor computes it when the author saves, and it is stored as
`config.items`.** The server only validates it (`correctOrder` must be a permutation and must not
be the identity).

Why stored rather than a deterministic server-side shuffle seeded by the question ID:
- `_question_payload` (gateway), `get_player_question_summary`, `get_host_question_summary` and
  the question-list APIs all pass `config` through unchanged. If `config` held the correct order,
  every one of those paths would need a transform, and any path that was missed would leak the
  answer. With the stored shuffle, `config` is safe to send anywhere by construction, exactly like
  hotspot's `config` (the target sits in `answer_data`).
- Question IDs change on import, so an ID-seeded shuffle would show a different display order on
  every server. Sample games would then not reproduce, and an e2e test could not predict the
  display order.
- `random.Random(seed).shuffle` makes no promise about stability across Python versions, and a
  seeded shuffle can produce the identity permutation, which would need a retry loop anyway.
- Authors see exactly what players will see: the editor previews it (§6.9).

**Editor shuffle rule (advisory, not validated by the server):** pick a uniformly random
permutation and accept it only if (a) it is not the identity and (b) a player who submits the
display order unchanged would get at most half the partial credit, that is
`L(display) ≤ 1 + ⌊(n − 1)/2⌋`. It tries up to 200 times and falls back to the exact reversal.
This stops "submit as shown" from earning large partial credit. The server enforces only (a). Rule
(b) is a quality heuristic, and hand-written bundles or API calls that break it are still valid.

### O4. Partial credit by longest in-order run ("items out of place")
**The user's candidate metric was Kendall-tau style (fraction of item pairs in correct relative
order). The user flagged it as hard to explain, and flagged exact-position matching as harsh.**
Four candidates were compared on n = 4 with correct order A B C D:

| Submitted | Exact positions | Kendall pairs | Adjacent pairs | **Longest run (chosen)** |
|---|---|---|---|---|
| A B C D | 4/4 | 6/6 | 3/3 | (4−1)/3 = 1 |
| B A C D (one swap) | 2/4 | 5/6 | **1/3** | (3−1)/3 = 0.67 |
| D A B C (one item moved) | **0/4** | 3/6 | 2/3 | (3−1)/3 = 0.67 |
| A C B D (one swap, middle) | 2/4 | 5/6 | **0/3** | (3−1)/3 = 0.67 |
| B A D C (two swaps) | 0/4 | 4/6 | 0/3 | (2−1)/3 = 0.33 |
| D C B A (reversed) | 0/4 | 0/6 | 0/3 | (1−1)/3 = 0 |

- **Exact position** gives 0 when the player moves just one item (D A B C). That is harsh and
  feels wrong.
- **Kendall** grades sensibly, but "5 of 6 pairs" means nothing to a student on a results screen,
  and the host cannot show it.
- **Adjacent pairs** ("correct successor pairs": how many of A→B, B→C, C→D appear next to each
  other) treats the same single swap differently depending on where it is (B A C D scores 1/3
  but A C B D scores 0/3), and moving one item (D A B C) scores better than one swap.
- **Longest in-order run** gives one plain sentence the results screen can show: *"1 item out of
  place"*, which is the smallest number of items you would have to move. Every single-move
  mistake costs the same. The out-of-place items can be highlighted, so the score can be
  explained visually.

**Normalisation `(L − 1)/(n − 1)`, not `L/n`:** any single item is trivially "in order", so
`L ≥ 1` always, and `L/n` would give a fully reversed answer 1/n of the points. With
`(L − 1)/(n − 1)` the scale runs from exactly 0 for a reversal to exactly 1 for a perfect order.
In player terms: **score = 1 − (items out of place)/(n − 1)**. n ≥ 3, so the divisor is never 0.

### O5. Grading modes: partial credit lives in ACCURACY; COMPLETENESS is participation
**Correction to the original brief.** The user's brief said "ACCURACY = all-or-nothing exact
order; COMPLETENESS = partial credit". That assumed COMPLETENESS meant "graded leniently". In this
codebase COMPLETENESS means **participation credit**: `game_service.calculate_score` returns full
`points_value` for any non-empty answer before any type branch runs. Every reveal builder returns
`{type: "completeness"}` early. Hotspot follows the same rule: a COMPLETENESS hotspot question has
no target, and its `answer_data` is not checked. Reusing the name COMPLETENESS for "partial
credit" on one type would have changed the meaning of a mode hosts already use, added a
special case before four early returns, and confused the T6 "both grading modes" requirement. The
coordinator corrected the decision before implementation. The resulting rule:

- **ACCURACY** has a correct order. The per-question flag `answer_data.partialCredit` chooses
  between partial credit by the O4 formula (`true`, the editor default) and all-or-nothing exact
  order (`false`, the user's original ACCURACY idea, still available). One boolean, not a
  `partialFraction`-style number: the O4 scale already grades by how wrong the answer is, so a
  second multiplier would add a control without adding meaning.
- **COMPLETENESS** has no correct order. Any valid full order earns full points. `answer_data` is
  not checked (as hotspot). The reveal is `{type: "completeness"}`. **The author cannot supply a
  correct order for display only.** Showing "the right order" while every player gets full points
  sends mixed signals, and the main COMPLETENESS use is opinion rankings, where no right order
  exists. This matches hotspot, which shows no rings under COMPLETENESS. Under COMPLETENESS the
  items are shown in the order the author lists them (no shuffle; there is nothing to leak). The
  host still gets the room's average order (O9), which is what makes an opinion ranking
  interesting.

### O6. `is_correct` means "exact order"
For both `partialCredit` settings, `is_correct = (L == n)`. Under COMPLETENESS the existing early
return sets `is_correct = true`, unchanged. This mirrors hotspot (partial "outer" credit is
`is_correct = false`), so `correctCount` and the report's "% correct" mean "perfect orders".

### O7. Items: 3–6, plain text, ≤ 80 characters, unique, no images
- **Minimum 3:** two items make a true/false question.
- **Maximum 6:** six full-width 56 px buttons with 8 px gaps take about 384 px. Together with the
  prompt, timer and the Undo/Reset/Submit row, that fits a 375 × 667 phone (iPhone SE) without
  scrolling, which the e2e test checks (§9.3). It also keeps the answer under about 30 s, and 6!
  = 720 orders is plenty of difficulty.
- **≤ 80 characters**, at least 1. With the badge and padding about 280 px of a 375 px phone is
  left for text, roughly 35 characters per line at 16 px, so an 80-character item takes up to
  three lines. The layout budget (and the e2e no-scroll check) uses short items plus one
  80-character item, with a one-line prompt.
- **Whitespace must already be normalised** (`item == " ".join(item.split())`: no leading or
  trailing space, no runs of spaces, no newlines). The validator rejects rather than fixes, as
  every other `QuestionCreate` rule does, and the editor trims before sending.
- **Unique**, compared case-insensitively after whitespace normalisation. Two identical items
  would make two submitted orders indistinguishable to the player but different to the scorer.
- **Plain text, not HTML.** React escapes it, and the report escapes it with `_esc`. It is not
  passed through the prompt's bleach sanitiser, because it is never rendered as HTML.
- **No per-item images** (T8 option images). `optionImageIds` exists only for `multiple_choice` /
  `multi_select` (`OPTION_IMAGE_TYPES`). Extending it would touch
  `image_service.question_image_fields`, `find_references`, export refs, copy-on-move and replace:
  five T8 paths for something timelines and process steps do not need. An ordering question
  **may** carry a T8 **prompt image** (for example a water-cycle diagram), which every type already
  supports through the generic code. That is the scope cut.

### O8. Validation is one checker, symmetric on create and update
The rules live once, in `schemas/admin.py`: `ordering_config_error(config)` and
`ordering_answer_error(config, answer_data)`. They return a message or `None` and never raise.
`QuestionCreate.validate_structure` raises with them. `QuestionUpdate` adds `ordering` to its type
regex and gets no validator of its own: `content_service.update_question` (T4 D8) merges the patch
onto the stored question and re-validates the whole result with `QuestionCreate`. Both the admin
and host routes now delegate to it (T4 phase 3), so an update cannot store anything a create would
reject. That includes cross-field breakage: a PUT that changes `config.items` to five items while
keeping a four-entry `correctOrder`, or a type change from `multiple_choice` that keeps the MC
config. The integration tests check this on both routes (§9.2 tests 3–4), because T7 explicitly
warns not to assume the two paths are symmetric.

### O9. Results show the room's order (mean positions) under both gradings
At results time the host gets `meanPositions`: for each display index, the average 1-based
position players gave that item (2 decimals), from every submitted order. Sorting by it gives the
room's order. Under ACCURACY the host compares it with the correct order ("the room put
Metaphase before Prophase"). Under COMPLETENESS it is the result of the opinion poll. It is
aggregate data with no names, so it is safe on the projector. Players do not receive it.

### O10. The player's result label comes from a server-computed outcome
As hotspot H12: the per-player results emit carries `yourOrdering: {inOrder, total, outOfPlace}`
(or `null`). The player app labels from it ("Perfect order!", "1 item out of place") and marks the
out-of-place items. Labelling from points would be wrong for `points_value = 0` or
`partialCredit = false`. Recomputing the longest run in TypeScript would create a second scorer
that could drift from the Python one (§3 O3's advisory heuristic needs only a run *length* in the
editor, which affects no scores).

### O11. Host shows no live statistics while the question is open
As hotspot H5: during `QUESTION` the host shows the prompt, the items in display order (so the
room can read them on the big screen) and the answered count. The distribution and room order
appear only at `RESULTS`, so slow players cannot copy the crowd.

### O12. Bad stored data scores as a miss, is logged, and never crashes
The same posture as hotspot §5.4, detailed in §4.6. Both write paths now validate, so bad rows
can only come from direct DB edits or legacy data. The live game must still never fail mid-question.

### O13. Browser e2e tests with Python Playwright against the live stack
**(User decision.)** Integration tests prove the protocol. Only a browser proves the tap UI fits a
phone, that the editor's shuffle round-trips through the API, and that the host reveal renders.
Python, so the team uses one language and runner (pytest) for all three test levels.

### O14. Test-first, one atomic commit per concern
**(User decision.)** Every phase in §8 starts by committing (or staging) failing tests, then the
code that makes them pass, as one commit per concern with an imperative message.

## 4. Data shape, validation, scoring

### 4.1 Stored question

- `type`: `"ordering"`.
- `config` (sent to clients), **always checked**: exactly `{ items }`.
  - `items`: list of 3–6 strings (constants `ORDERING_MIN_ITEMS = 3`, `ORDERING_MAX_ITEMS = 6`,
    `ORDERING_ITEM_MAX_LEN = 80` in `schemas/admin.py`).
  - Each item: `isinstance(item, str)`, `1 ≤ len(item) ≤ 80`, `item == " ".join(item.split())`.
  - Unique under `" ".join(item.lower().split())`.
  - Any other key → 422 (including `optionImageIds`, which `option_images_error` already rejects
    for non-MC/MS types).
  - Under ACCURACY the list is in **display (shuffled) order**. Under COMPLETENESS it is in the
    order the author listed.
- `answer_data` (server-only), **checked only under ACCURACY**: exactly
  `{ correctOrder, partialCredit }`.
  - `correctOrder`: list of ints (bool rejected) with `sorted(correctOrder) == list(range(n))`,
    where `n = len(config["items"])`. Meaning: `correctOrder[k]` = display index of the item at
    correct position `k`.
  - `correctOrder != list(range(n))`: the display order must not be the correct order (O3).
  - `partialCredit`: a real bool (`isinstance(v, bool)`). `0`/`1` are rejected.
  - Any other key → 422.
- Under COMPLETENESS `answer_data` is not checked (matches hotspot, FITB, MC). The editor sends
  `{}`.
- Keys are camelCase, matching hotspot and FITB (`schemas/README.md` asks new types to choose
  deliberately).

Error messages (exact text, so tests can assert them):

| Check | Message |
|---|---|
| config keys | `ordering config must have exactly 'items'` |
| items type/count | `ordering items must be a list of 3 to 6 strings` |
| item length | `ordering item {i} must be 1 to 80 characters` (1-based `i`) |
| item whitespace | `ordering item {i} must not have leading, trailing or repeated spaces` |
| duplicates | `ordering items must be unique` |
| answer keys | `ACCURACY ordering answer_data must have exactly 'correctOrder' and 'partialCredit'` |
| permutation | `ordering correctOrder must list each item index 0..{n-1} exactly once` |
| identity | `ordering items must be stored in a shuffled order, not the correct order` |
| partialCredit | `ordering partialCredit must be true or false` |

`ordering_answer_error(config, answer_data)` returns the config error first if `config` is
invalid, so it can be called on its own.

**Evaluation order** (the first failing check wins, so an input with two violations gets a
predictable message): config — keys → list type and count → for each item in index order:
type and length, then whitespace → duplicates. answer_data — keys → permutation → identity →
partialCredit.

**Message format in responses:** Pydantic prefixes model-validator errors with `Value error, `,
so tests assert that the message is **contained** in the 422 detail, not equal to it. An
`optionImageIds` key on an ordering question is rejected earlier by the T8 checker
(`option_images_error` runs before every type branch), with its own message
"optionImageIds is only allowed on multiple_choice and multi_select".

### 4.2 Submission

- Client sends `submit_answer` with `answer_data = { order: int[] }`.
- Valid iff `order` is a list of ints (bool rejected) and `sorted(order) == list(range(n))`, where
  `n` comes from the question's `config` (§6.3).
- The gateway stores the normalised `{ "order": [...] }` (extra client keys dropped), as
  hotspot stores only `{x, y}`.

### 4.3 Longest in-order run and which items are "out of place"

Given the stored `correctOrder` `c` (length n) and a valid submission `p`:

1. `rank[d]` = position of display index `d` in `c` (its correct position).
2. `r = [rank[p[0]], …, rank[p[n-1]]]`: the correct positions, in the order the player chose.
3. `L` = length of the longest strictly increasing subsequence of `r`.
4. **Deterministic tie-break for which items are in the run** (several runs can have the same
   length; the out-of-place list must not depend on implementation details):
   - `best[i]` = length of the longest increasing subsequence of `r` that **starts** at index
     `i` (computed right to left, O(n²); n ≤ 6).
   - Start at the smallest `i` with `best[i] == L`. Then repeatedly pick the smallest `j > i`
     with `r[j] > r[i]` and `best[j] == best[i] − 1`.
   - The chosen indices are "in order". `outOfPlace` = the **display indices** `p[k]` for every
     `k` not chosen, in submission order.
5. `exact` ⇔ `L == n` ⇔ `p == c`.

Example: correct A B C D, submitted B A C D → `r = [1, 0, 2, 3]`, `best = [3, 3, 2, 1]`. The
run starts at index 0 (B), so it is B C D, and **A** is out of place. Either A or B is a valid
answer; the rule just picks one predictably.

### 4.4 Score (`calculate_score` branch)

- No answer: the existing `if not answer_data` early return gives `(0, False)`.
- `COMPLETENESS`: the existing early return gives `(points_value, True)`. Unchanged.
- `ACCURACY`, `ordering`:
  - `key = ordering_key(question.id, question.config, question.answer_data)`. `None` →
    `ScoreResult(0, False)` (§4.6).
  - `order = ordering_submission(answer_data, len(key.correct_order))`. `None` →
    `ScoreResult(0, False)` (defensive; the gateway already rejects these).
  - `res = ordering_result(key, order)`.
  - `res.exact` → `ScoreResult(points_value, True)`.
  - else if `key.partial_credit` →
    `ScoreResult(round(points_value * (res.in_order - 1) / (res.total - 1), 2), False)`.
  - else → `ScoreResult(0, False)`.
  - Points are floats (`points_awarded` is a float column since migration 003). Rounding to 2
    decimals keeps thirds (666.67) readable and reproducible in the engine mirror, which uses
    the identical expression.

### 4.5 Worked examples (points_value 1000)

| n | Correct | Submitted | L | Out of place | partialCredit=true | partialCredit=false | is_correct |
|---|---|---|---|---|---|---|---|
| 4 | A B C D | A B C D | 4 | — | 1000 | 1000 | true |
| 4 | A B C D | D A B C | 3 | D | 666.67 | 0 | false |
| 4 | A B C D | B A C D | 3 | A | 666.67 | 0 | false |
| 4 | A B C D | B A D C | 2 | A, C | 333.33 | 0 | false |
| 4 | A B C D | D C B A | 1 | C, B, A | 0 | 0 | false |
| 3 | A B C | B A C | 2 | A | 500 | 0 | false |
| 5 | A B C D E | B C D E A | 4 | A | 750 | 0 | false |
| 6 | A–F | one item moved | 5 | 1 item | 800 | 0 | false |

(The "Out of place" column lists items by letter, in submission order per §4.3. For B A D C:
`r = [1,0,3,2]`, `best = [2,2,1,1]`, start 0 (B), then the smallest j > 0 with r[j] > 1 and best 1
is j = 2 (D), so the run is B D and A, C are out of place.)

`points_value = 0`: every answer scores 0, but `is_correct` and `yourOrdering` still reflect the
order (O10).

### 4.6 Bad stored data: miss-and-log, never crash

`ordering_key(question_id, config, answer_data) -> OrderingKey | None` returns `None` when
`ordering_answer_error(config, answer_data)` is not `None`. It logs
`logger.warning("ordering_key_invalid", question_id=...)` (structlog, as hotspot §13.1 a) and
never raises, whatever the JSON (`None`, a list, strings, a bool index, a wrong-length
`correctOrder`). Call it **only under ACCURACY**: COMPLETENESS rows have no key, and calling it
there would log a false warning (same note as hotspot).

For an ACCURACY ordering question whose key is `None`:
- **Score:** `ScoreResult(0, False)`. **Distribution:** no key recorded.
- **Reveal** (every builder): `{type: "ordering"}` with **no** `correctOrder`.
- **Per-player `yourOrdering`:** `null`. The player label is "Not scored" (§6.7).
- **Host:** `meanPositions` still computed from submissions (it needs only `config`). The view
  shows no correct order and the note "Answer key invalid".
- **Report:** room order only, plus the note "Answer key invalid".

A bad **config** (for example 7 items stored directly in MySQL) also breaks the submission check.
`ordering_item_count(config)` returns `None` (and logs `ordering_config_invalid`), and the gateway
rejects the submission with the error "This ordering question is misconfigured" (§6.3). The player
UI could not have rendered the question properly anyway. This is accepted as an edge (§11).

## 5. Export / import

Ordering adds no image fields and no bundle keys, so `content_service.export_game` /
`import_game` need **no code change**:
- `_exported_question` copies `config` and `answer_data` verbatim, so the shuffled `items`,
  `correctOrder` and `partialCredit` survive unchanged and the display order is the same on the
  importing server (one reason for O3).
- A game whose questions use no images exports as **version 1**. A game where any question
  (ordering or not) has a T8 prompt image, option image or hotspot exports as **version 2**, and
  an ordering question's prompt image becomes `prompt_image_ref` through the existing generic
  code.
- Import validates each question with `QuestionCreate`, so the §4.1 rules apply to bundles with
  the existing message format (`Question N invalid: …`, 1-based).
- There is no v1-only restriction (unlike hotspot): an ordering question in a v1 bundle carries no
  instance-specific IDs.

The integration tests (§9.2 tests 12–14) prove v1 and v2 round trips and the import errors.

## 6. Detailed implementation

### 6.1 `backend/app/schemas/admin.py`

- Add `ordering` to the `type` regex in **both** `QuestionCreate` and `QuestionUpdate`.
- Module-level constants `ORDERING_MIN_ITEMS`, `ORDERING_MAX_ITEMS`, `ORDERING_ITEM_MAX_LEN`, and
  the checker functions `ordering_config_error(config: object) -> str | None` and
  `ordering_answer_error(config: object, answer_data: object) -> str | None`, implementing §4.1
  with the exact messages. Pure, never raise, placed after the hotspot checker under an
  `# Ordering rules (docs/plans/t7-ordering.md §4.1)` banner.
- `QuestionCreate.validate_structure`: an `ordering` branch:
  `error = ordering_config_error(self.config)`; if `None` and ACCURACY,
  `error = ordering_answer_error(self.config, self.answer_data)`; raise `ValueError(error)` if set.

### 6.2 `backend/app/services/game_service.py`

Imports `ordering_config_error`, `ordering_answer_error` from `..schemas.admin` (the existing
dependency direction). New module-level pure helpers under an `# Ordering` banner after the
hotspot helpers:

- `@dataclass(frozen=True) class OrderingKey: correct_order: tuple[int, ...]; partial_credit: bool`.
- `@dataclass(frozen=True) class OrderingResult: in_order: int; total: int;
  out_of_place: tuple[int, ...]`, plus the property `exact -> bool` (`in_order == total`).
- `ordering_item_count(question_id, config) -> int | None`: `len(config["items"])` if
  `ordering_config_error(config)` is `None`; otherwise logs `ordering_config_invalid` and returns
  `None`.
- `ordering_key(question_id, config, answer_data) -> OrderingKey | None`: §4.6.
- `ordering_submission(answer_data: object, n: int) -> tuple[int, ...] | None`: §4.2. The one
  submission parser.
- `ordering_result(key: OrderingKey, order: tuple[int, ...]) -> OrderingResult`: §4.3, including
  the tie-break.
- `ordering_points(key, result, points_value) -> ScoreResult`: §4.4 (keeps `calculate_score`'s
  branch short and gives the unit tests one target).
- `ordering_reveal(key: OrderingKey | None) -> dict`: `{"type": "ordering", "correctOrder":
  list(key.correct_order)}`, or `{"type": "ordering"}` when `key` is `None`. `partialCredit` is
  not revealed (the player sees their points). **Every** reveal builder calls this (gateway,
  report, both summaries), as hotspot §13.1 b.
- `ordering_outcome(result: OrderingResult | None) -> dict | None`:
  `{"inOrder": L, "total": n, "outOfPlace": [...]}` or `None`.
- `ordering_dist_key(result) -> str`: `str(result.total - result.in_order)` ("0" = perfect).
- `ordering_mean_positions(n: int, orders: list[tuple[int, ...]]) -> list[float | None]`: for
  each display index `d`, `round(mean(1 + order.index(d) for order in orders), 2)`, or `None`
  for every entry when `orders` is empty.

Callers:
- `calculate_score`: an `ordering` branch after `hotspot`, per §4.4.
- `record_answer`: `elif question.type == "ordering" and question.grading_type == "ACCURACY":`
  get the key, parse the order, and set `dist_key = ordering_dist_key(result)`. No key under
  COMPLETENESS or when the key is `None`. No new Redis keys.
- `get_player_question_summary`: `elif q_type == "ordering": reveal =
  ordering_reveal(ordering_key(r.question_id, r.config, q_ans))` (this sits after the existing
  COMPLETENESS branch, so it runs only under ACCURACY). It already returns `config` and
  `playerAnswer`.
- `get_host_question_summary`: compute `ord_key` once per question (ACCURACY only), the reveal via
  `ordering_reveal`, distribution keys via `ordering_dist_key` over **all** rows (ACCURACY with a
  valid key), and add `meanPositions` (from every valid submission, both gradings) to ordering
  items only. If `ordering_item_count` is `None`, `meanPositions` is `[]`.

### 6.3 `backend/app/websocket/gateway.py`

- `_question_payload`: **no change** (`config.items` is safe; `answer_data` is never sent).
- `_answer_reveal`: `if q.type == "ordering": return game_service.ordering_reveal(
  game_service.ordering_key(q.id, q.config, q.answer_data))` (after the COMPLETENESS early
  return, so ACCURACY only).
- `on_submit_answer`, next to the hotspot check:
  - `n = game_service.ordering_item_count(question.id, question.config)`; `None` → emit error
    "This ordering question is misconfigured" and return.
  - `order = game_service.ordering_submission(answer_data, n)`; `None` → emit error
    "ordering answer must list every item exactly once" and return without recording.
  - `answer_data = {"order": list(order)}`, then `record_answer` as usual.
- `_on_host_advance_impl`, `QUESTION → RESULTS`: `q_score_rows` already selects
  `_Score.answer_data`. For an ordering question, parse every row with `ordering_submission`
  (skip invalid ones). Then:
  - **Host emit:** add `"meanPositions": ordering_mean_positions(n, orders)` (`[]` if
    `n is None`). `answerDistribution` comes from Redis as today.
  - **Per-player emit:** add `"yourOrdering"`: under ACCURACY with a valid key and that player's
    valid row, `ordering_outcome(ordering_result(key, order))`; otherwise `None` (unanswered,
    COMPLETENESS, invalid key). Players never receive `meanPositions` or other players' orders.

### 6.4 `backend/app/services/report_service.py`

- Badge: `"ordering": ("Ordering", "badge-ordering")` in the `type_badge` map, plus a CSS rule
  `.badge-ordering{background:#1e3b3b;color:#5eead4}` next to `.badge-hotspot` (T9 retokenises
  the report palette along with everything else).
- `_answer_reveal`: `if q.type == "ordering": return ordering_reveal(ordering_key(...))`
  (imported from `game_service`; no copy).
- `_extract_answer_key(q, answer_data, hs_target=None, ord_key=None)`: for ordering, parse with
  `ordering_submission(answer_data, len(ord_key.correct_order))` and return
  `ordering_dist_key(...)`. `None` if `ord_key` is `None` (COMPLETENESS or invalid). The caller
  computes `ord_key` once per question (ACCURACY only), as it does `hs_target`.
- New `_render_ordering(q, dist, ord_key, mean_positions) -> str`:
  - ACCURACY with key: an ordered list "Correct order" (item text via `_esc`), then bar rows
    "Perfect", "1 out of place", … "n−1 out of place" from `dist` (reusing the `.bar-row` CSS).
  - Always: "Room's order": items sorted by mean position (ties broken by display index), each
    with "avg 1.40". "No answers" if empty.
  - Invalid key: the note "Answer key invalid" in a new `.ordering-note` class (same rules as
    `.hotspot-note`; hotspot is left untouched).
  - The caller collects `mean_positions` from `q_scores` with
    `ordering_mean_positions(ordering_item_count(q.id, q.config), orders)` — `n` comes from the
    config, so it works under COMPLETENESS too (`[]` when the count is `None`).
- The stats line needs no change: "% correct" counts `is_correct`, which is "perfect order" (O6).

### 6.5 Other backend files (checked; no change)

- `services/content_service.py`: none (§5). Create and update already validate through
  `QuestionCreate`; `_check_images` only sees the prompt image.
- `services/image_service.py`: `question_image_fields` returns only the prompt image for
  ordering (it branches on MC/MS and hotspot). No change.
- `services/export_service.py`: does not branch on type. No change.
- No migration.

### 6.6 Frontend types (both `host/src/types/game.ts` and `player/src/types/game.ts`)

Hand-written in both apps (`frontend/README.md` gotcha):
- `OrderingConfig { items: string[] }`.
- `AnswerReveal` union gains `{ type: 'ordering'; correctOrder?: number[] }` (optional: §4.6).
- Host: optional `meanPositions?: (number | null)[]` on the host results payload type and on the
  game-over per-question item type.
- Player: `OrderingOutcome { inOrder: number; total: number; outOfPlace: number[] }` and
  `yourOrdering?: OrderingOutcome | null` on the player results type.
- The `question.type` string unions gain `'ordering'` wherever they are enumerated.

### 6.7 Player app (`frontend/player/src/`)

- **New `components/OrderingPicker.tsx`**, presentational only (state is in the page):
  - `OrderingPicker({ items, sequence, onTap, disabled })`: renders `items` in display order as
    full-width `<button type="button">`s, `min-h-14` (56 px), `text-base`, 8 px gap. `sequence`
    is the list of display indices tapped so far. An item at position `k` in `sequence` shows a
    round badge with `k + 1` and a selected style. Untapped items show an empty badge outline.
    `aria-pressed` reflects tapped, and `aria-label` = `"{item}, position {k+1}"` or
    `"{item}, not placed"`. `data-testid="ordering-item-{d}"`, badge
    `data-testid="ordering-badge-{d}"`.
  - `OrderingList({ items, order, marked?, title, testId })`: a read-only numbered list of
    `order.map(d => items[d])`. Items whose display index is in `marked` get a warning style and
    the text "out of place". Used by the results and recap screens.
  - Colours via CSS variables `--ordering-selected`, `--ordering-misplaced`, with fallbacks until
    T9 (the hotspot §13.1 j pattern).
- **`pages/game/QuestionPage.tsx`**, `ordering` branch:
  - Shows the **prompt** (as hotspot does; the player needs "earliest first" etc. on the phone).
  - `const [sequence, setSequence] = useState<number[]>([])`, reset when `questionId` changes.
  - Tapping an untapped item appends it. Tapping a tapped item does nothing (O2).
  - **Undo** (`data-testid="ordering-undo"`, disabled when empty) and **Reset**
    (`data-testid="ordering-reset"`) as `Button variant="outline"` in a row. The hint "Tap the
    items in order. Use Undo to change." sits above the list.
  - **Submit order** (`data-testid="ordering-submit"`, `size="lg"`, full width), disabled until
    `sequence.length === items.length` and while `!canAnswer`. The ordering branch defines its
    own `canAnswer = !submitted && !questionLocked` (the page has no shared one; hotspot's also
    waits for its image).
    Before emitting it re-checks that `sequence` is a permutation of `0..n-1` (any server `error`
    event replaces the whole UI, per the `pages/README.md` gotcha). Then
    `submit({ order: sequence })`.
  - Layout: all items visible without scrolling at 375 × 667 for n = 6 with a one-line prompt,
    five short items and one 80-character item wrapping to up to three lines (tested in §9.3).
- **`pages/game/ResultsPage.tsx`**, ordering label (decided like hotspot §13.1 c):
  - reveal type `completeness` → "Answer recorded!".
  - `lastAnswerData` null → "No answer".
  - reveal without `correctOrder` → "Not scored".
  - reveal with `correctOrder` but `yourOrdering` null → "Answer recorded" (a row missing at
    results time; hotspot's fallback).
  - `yourOrdering.outOfPlace.length === 0` → "Perfect order!" (success style).
  - otherwise → "{k} item(s) out of place" (warning style). Never derived from points.
  - Below the label: `OrderingList` "Your order" (from `lastAnswerData.order`, `marked =
    yourOrdering?.outOfPlace`) and, when the reveal has `correctOrder`, `OrderingList` "Correct
    order". Points, total and rank as today. Test IDs: `ordering-result-label`,
    `ordering-your-order`, `ordering-correct-order`.
- **`pages/game/GameOverPage.tsx`**: `describeAnswer` gains an `ordering` case
  (`order.map(d => items[d]).join(' → ')`), plus a "Correct:" line from `answerReveal.correctOrder`
  when present. No out-of-place marking in the recap (the per-player outcome is not in the
  game-over payload, and recomputing it client-side is what O10 avoids).

### 6.8 Host app (`frontend/host/src/`)

- **New `components/OrderingView.tsx`** (display only):
  `OrderingView({ items, correctOrder?, distribution?, meanPositions?, accuracy, invalidKey?,
  compact? })`:
  - ACCURACY with `correctOrder`: a large numbered "Correct order" list (readable from the back
    of a room: `text-2xl` and up unless `compact`), and a bar row per bucket "Perfect" / "1 out of
    place" / … / "{n−1} out of place" from `distribution` (keys "0".."n−1").
  - Always, when `meanPositions` has values: "Room's order", items sorted by mean (ties by
    display index), each with "avg 1.40" (two decimals, as the report).
  - `invalidKey` → the note "Answer key invalid" instead of the correct order.
  - Test IDs: `ordering-host-correct-order`, `ordering-host-room-order`.
- **`pages/game/QuestionPage.tsx`**: the ordering branch shows the items in display order as a
  plain large list under the prompt. No statistics (O11).
- **`pages/game/ResultsPage.tsx`**: `OrderingView` with the reveal, `answerDistribution` and
  `meanPositions`. `accuracy` = `gradingType === 'ACCURACY'`. `invalidKey` = ACCURACY and the
  reveal has no `correctOrder`.
- **`pages/game/GameOverPage.tsx`**: the per-question card uses `OrderingView compact` with the
  summary's `answerReveal`, `answerDistribution` and `meanPositions`, and `invalidKey` by the
  same rule as `ResultsPage` (ACCURACY and no `correctOrder`).

### 6.9 Authoring — `frontend/host/src/components/OrderingEditor.tsx`, copied to admin

Self-contained: imports only `lib/utils.ts` (`cn`) and `components/ui/*`, so the admin copy
`frontend/admin/src/components/OrderingEditor.tsx` differs only in import paths (hotspot H9
pattern; each copy's header comment names the other).

- **Editor state** (exported type): `OrderingEditorState { items: string[]; display: number[];
  partialCredit: boolean }`. `items` is in **correct order** (ACCURACY) or **shown order**
  (COMPLETENESS). `display` is a permutation: `display[k]` = index into `items` of the item shown
  k-th.
- **Exported pure helpers** (the page uses them, and they keep the mapping in one place):
  - `orderingFromQuestion(config, answerData, grading) -> OrderingEditorState`. ACCURACY with a
    valid `correctOrder` `c`: `items = c.map(d => config.items[d])`,
    `display[k] = c.indexOf(k)`, `partialCredit = answerData.partialCredit` (a bool, else
    `true`). COMPLETENESS: `items = config.items ?? []`, `display` = identity,
    `partialCredit = true`. **ACCURACY with an invalid key** (bad stored data): load as
    COMPLETENESS would, set `keyInvalid: true` on the state, and the editor shows the warning
    "The stored answer key is invalid. Re-enter the items in the correct order." and makes a new
    display shuffle, so a re-save is valid instead of failing on the identity rule.
  - `orderingToPayload(state, grading) -> { config, answer_data }`. ACCURACY:
    `config.items = state.display.map(i => trimmed[i])`,
    `answer_data = { correctOrder: [0..n-1].map(k => state.display.indexOf(k)), partialCredit }`.
    COMPLETENESS: `config.items = trimmed`, `answer_data = {}`. `trimmed` =
    `items.map(s => s.split(/\s+/).filter(Boolean).join(' '))`.
  - `orderingProblems(state, grading) -> string[]`: the client-side copy of the §4.1 count,
    length, empty and duplicate checks, used to disable Save and list reasons. The server stays
    the authority, and its 422 shows via the existing `errorMessage()`.
  - `shuffleDisplay(n, rng = Math.random) -> number[]`: O3's advisory rule, using a local
    O(n²) `longestRunLength(seq)` (length only; it affects no scores).
- **UI:**
  - Item rows (3–6) with a text input (`maxLength=80`), up/down move buttons and remove (disabled
    at 3). "Add item" is disabled at 6. The heading reads "Items in the correct order
    (first → last)" under ACCURACY and "Items (players see them in this order)" under COMPLETENESS.
  - Under ACCURACY, the checkbox "Partial credit for nearly-right orders" (default on), with the
    helper text "Each item out of place costs 1/(n−1) of the points."
  - Under ACCURACY, the preview "Players see:" with the shuffled list, and a **Shuffle again**
    button.
  - **When the shuffle is regenerated:** on add or remove, on **Shuffle again**, and when
    switching to ACCURACY with an identity `display`. **Not** on text edits or moves. A move
    swaps two items in the correct order and each item **keeps its display slot**; only if the
    result breaks O3's rule (identity, or "submit as shown" worth more than half) is a new
    shuffle made. Hence a stored question re-saved after text edits or moves keeps its display
    order wherever O3 allows, which matters because stored submissions are display indices
    (§11).
  - The hint "Say which end comes first in the prompt, e.g. 'earliest first'."
- **Integration into both `pages/QuestionEditorPage.tsx` (host and admin):**
  - `QuestionType` union and type dropdown: `<option value="ordering">Ordering (put items in
    order)</option>`. Type label map: `ordering: 'Ordering'`.
  - `FormState` gains `ordState: OrderingEditorState`. The default for a new question is
    `{ items: ['', '', '', ''], display: shuffleDisplay(4), partialCredit: true }`.
  - `questionToForm` / `formToPayload`: ordering branches via the helpers.
  - The **points field shows under both gradings** for ordering (like hotspot §13.2 G3: no
    per-option points to derive it from).
  - Save is disabled while `orderingProblems(...)` is non-empty, and the problems are listed.
  - Under COMPLETENESS the note "Completeness: any complete order earns full points. There is no
    correct order, which suits opinion rankings."
  - A soft hint (not a block) when `time_limit_seconds < 5 × n`: "Ordering questions usually
    need about 5 seconds per item."
  - The question-list summary line: `Prophase → Metaphase → Anaphase → Telophase · partial
    credit` (correct order under ACCURACY, shown order under COMPLETENESS), item text truncated
    to 24 characters.
  - Test IDs for e2e: `question-type-select`, `ordering-editor-item-{i}`, `ordering-editor-add`,
    `ordering-editor-partial`, `ordering-editor-preview`, `question-save`. Neither editor page
    has any `data-testid` yet: `question-type-select` and `question-save` are **new**, added to
    both pages.

### 6.10 Tooling

- **`scripts/simulate_players.py`**: `_make_answer` ordering branch. With `--game-json`,
  `random() < accuracy`, an ACCURACY question and a `correctOrder` that is a valid permutation
  of `n`, submit `answer_data.correctOrder` from the JSON question (the JSON stores
  the same display-order `items` the live payload carries, so the indices match). Otherwise
  submit `random.sample(range(n), n)`, with `n = len(q["config"]["items"])`. `_answer_str`:
  `"order [2, 0, 3, 1]"`. Update the module docstring's type list.
- **`tests/integration/engine/scoring.py`**: an `ordering` branch in `compute_question_score`
  (after the COMPLETENESS early return) and in `_build_reveal`. It is written **independently** of
  the backend: the longest run is found by **brute force** over index subsets
  (`itertools.combinations`, largest first; n ≤ 6 means at most 63 subsets), not the DP. The two
  implementations therefore cross-check each other. Points use the identical
  `round(points_value * (L - 1) / (n - 1), 2)`. Update the `QuestionSpec.type` comment.
- **`tests/integration/scenarios/all_question_types.py`**: add `ORDERING_PARTIAL`,
  `ORDERING_EXACT_ONLY` and `ORDERING_COMPLETENESS` specs, and extend `_correct`, `_wrong` (one
  item moved, for partial credit) and `_any` for ordering.

### 6.11 READMEs (`.claude/rules/context-sync.md`)

Edit only what is stale in: `backend/app/README.md` (type list; "Adding a question type touches"
unchanged; its "Validation is asymmetric" gotcha is already stale since T4 D8 and is corrected),
`backend/app/schemas/README.md` (ordering rules and checker; its "Updates bypass validation"
line is corrected the same way),
`backend/app/services/README.md` (ordering helpers, scoring, summaries, report),
`backend/app/websocket/README.md` (ordering reveal, submission check, `meanPositions`,
`yourOrdering`), `frontend/README.md` (new components; "`OrderingEditor` has an admin copy"
gotcha), `frontend/{host,player,admin}/src/{pages,components}/README.md`. Add a new
`tests/e2e/README.md` (how to run and what it needs; §9.3). No `lib/` change is expected
(ordering adds no lib code).

## 7. Sample games (T6)

**Not part of this branch.** T6 is its own branch (`feat/t6-games`); Vincent's two T6 games
(filenames chosen there, distinct from the starter files) each get ordering questions once this
type is on `main`. Both stay **version 1** unless they also use T8 images. Stored JSON (display
order shown; checked against O3's rule):

| Game | Question | Stored `config.items` (display order) | `answer_data` | Check |
|---|---|---|---|---|
| Classroom | "Put the phases of mitosis in order, first to last." ACCURACY, 25 s, 1000 pts | `["Anaphase", "Prophase", "Telophase", "Metaphase"]` | `{"correctOrder": [1, 3, 0, 2], "partialCredit": true}` | Display-as-submitted: r = [2,0,3,1], L = 2 → 1/3 ≤ 0.5 ✓ |
| Party | "Order these films by US release year, oldest first." ACCURACY, 30 s, 1000 pts | `["E.T. the Extra-Terrestrial", "Titanic", "Jaws", "Jurassic Park", "Star Wars"]` | `{"correctOrder": [2, 4, 0, 3, 1], "partialCredit": true}` (Jaws 1975, Star Wars 1977, E.T. 1982, Jurassic Park 1993, Titanic 1997) | r = [2,4,0,3,1], L = 2 → 1/4 ✓ |
| Party | "Rank these pizza toppings, favourite first." COMPLETENESS, 20 s, 500 pts | `["Pepperoni", "Mushrooms", "Pineapple", "Olives", "Extra cheese"]` | `{}` | No correct order. The host shows the room's ranking. |

All facts are public knowledge; there are no images and no licensing concerns. Each game still
needs every other type and both grading modes (T6). Every ordering question imports through the
existing sample-import tests (T4 §6.4 test 1 via the admin endpoint, hotspot test 14 via the host
endpoint).

## 8. Phases and commits (test-first)

Each phase starts with failing tests. One commit per row, imperative message, files staged
explicitly (never `git add -A`). Run `git branch --show-current` (must be `feat/t7-ordering`)
before each commit. The stack must be up (`docker compose up --build`) for integration and e2e
tests. If Docker Desktop is not running, stop and say so.

| # | Tests first (red) | Then implement | Commit message |
|---|---|---|---|
| 0 | — | This spec | `Add ordering question type design` |
| 1 | `tests/unit/test_ordering_schema.py` checker cases; `tests/integration/test_ordering.py` tests 1–4 | §6.1 | `Validate ordering questions on create and update` |
| 2 | unit (`tests/unit/test_ordering.py`): `ordering_key` never-raise, `ordering_result` run/tie-break table, `calculate_score` §4.5 table, `ordering_mean_positions` | §6.2 helpers, `calculate_score`, `record_answer` | `Score ordering answers by longest in-order run` |
| 3 | integration tests 5–11 (sockets, summaries, bad data) | §6.2 summaries, §6.3 gateway | `Send ordering reveals and results over the socket` |
| 4 | integration test 16 (engine scenario) | §6.10 engine mirror, scenarios, simulator | `Mirror ordering scoring in the test engine and simulator` |
| 5 | integration tests 12–14 (expected green: proves §5 needs no code) | none | `Test ordering export and import round trips` |
| 6 | integration test 15 (report) | §6.4 | `Render ordering questions in the session report` |
| 7 | — | `tests/e2e/` harness (`pytest.ini`, `requirements.txt`, `conftest.py`, README), plus a smoke test that loads `/player/join` | `Add Playwright e2e test harness` |
| 8 | e2e test 2 (player on phone) | §6.6 player types, §6.7 | `Add ordering answer UI to the player app` |
| 9 | e2e test 3 (host reveal) | §6.6 host types, §6.8 | `Show ordering questions and results on the host screen` |
| 10 | e2e test 1 in its host variant (author in host editor) | §6.9 host `OrderingEditor` + host editor page | `Add ordering editor to the host app` |
| 11 | e2e test 1 (author in admin editor) | §6.9 admin copy + admin editor page | `Copy ordering editor into the admin app` |
| 13 | — | §6.11 READMEs | `Update context READMEs for ordering` |

Then the closing steps from `CLAUDE.md`: a goldfish test of this spec in a **fresh subagent**
(before phase 1; record revisions as a new §13), `mean-review` after phase 13, a full run of
unit, integration and e2e tests green, `tsc --noEmit` for all three apps and `ruff check` /
`ruff format --check`, then update `docs/vzhou2.md` and push.

## 9. Tests

### 9.1 Unit — `tests/unit/test_ordering_schema.py` (phase 1, imports only `app.schemas.admin`: cases 1–2) and `tests/unit/test_ordering.py` (phase 2, `app.services.game_service`: cases 3–7)

1. `ordering_config_error`: valid 3- and 6-item lists → `None`. Each §4.1 config violation gives
   its exact message: not a dict; extra key; 2 items; 7 items; a non-string; `""`; 81 characters;
   `" Prophase"`; `"Pro  phase"`; `"a\nb"`; `"Mitosis"` / `"mitosis"` duplicates.
2. `ordering_answer_error`: missing key; extra key; wrong length; duplicate index; out-of-range
   index; `True` as an index; identity; `partialCredit` `1` / `"yes"`; an invalid config returns
   the config message.
3. `ordering_key` returns `None` without raising for `answer_data` `None`, `[]`, `"x"`,
   `{"correctOrder": "0123"}`, and for config `None`. It logs `ordering_key_invalid` once per call.
4. `ordering_result`: for **all 24 permutations of n = 4** (and all 120 of n = 5), `in_order`
   equals a brute-force longest-increasing-subsequence length, and `out_of_place` has
   `total − in_order` entries. The tie-break examples from §4.3 / §4.5 give exactly the listed
   items.
5. `calculate_score`: every row of §4.5 (both `partialCredit` values); COMPLETENESS → full points;
   empty answer → 0; invalid key → `(0, False)`; `points_value = 0` → `(0, True)` for exact.
6. `ordering_submission`: rejects a non-list, a short list, a duplicate, an out-of-range index, a
   bool, a string, a float `1.0`.
7. `ordering_mean_positions`: two orders → the expected means; empty → all `None`.

### 9.2 Integration — `tests/integration/test_ordering.py` (live stack)

Helpers: the `hapi` fixture and the `mysql()` function come from
`tests/integration/host_helpers.py`; `create_room()` and `create_guest_tokens()` are helper
functions in `conftest.py` (with the `game_setup` / `admin_token` fixtures); `TestSocketClient`
is in `tests/integration/engine/socket_client.py`.

| # | Test | Endpoint |
|---|---|---|
| 1 | Create: each §4.1 violation → 422 with its message (sample of config and ACCURACY answer cases; extra `optionImageIds` key). | `POST /api/admin/games/{g}/questions` **and** `POST /api/host/games/{g}/questions` |
| 2 | Create valid ACCURACY (both `partialCredit`) and COMPLETENESS (`answer_data` `{}`) → 201; GET returns exact `config` / `answer_data`. COMPLETENESS with 2 items → 422 (config always checked). | both routes, then `GET …/questions` |
| 3 | **Update symmetry:** for a stored valid question, each PUT patch → 422 `VALIDATION_ERROR` and the stored row unchanged: `config` with 7 items; `answer_data` with identity `correctOrder`; `config` with 5 items while `correctOrder` has 4 (cross-field after merge); `partialCredit: "yes"`. The merge is per field, so an `answer_data` patch replaces it whole: the `partialCredit` patch resends a valid `correctOrder`. | `PUT /api/admin/…/questions/{q}` **and** `PUT /api/host/…/questions/{q}` |
| 4 | Type change: PUT `{type: "ordering"}` on a `multiple_choice` question (keeps the MC config) → 422; PUT `{type: "multiple_choice"}` on an ordering question → 422. | both routes |
| 5 | `new_question` payload: `config.items` in stored display order; the key `correctOrder` and `partialCredit` appear **nowhere** in the payload (recursive key search). | Socket.io |
| 6 | Scoring over sockets, one player each, n = 4, 1000 pts, `partialCredit` true: exact → 1000; one moved → 666.67; two swaps → 333.33; reversed → 0. Same orders with `partialCredit` false → 1000, 0, 0, 0. `correctCount` in the host game-over summary = number of exact orders. | Socket.io |
| 7 | COMPLETENESS: any valid order → full points; reveal `{type: "completeness"}`; `yourOrdering` null; host still gets `meanPositions`. | Socket.io |
| 8 | Malformed submissions → socket `error` "ordering answer must list every item exactly once", no `session_scores` row; the player can still submit a valid order afterwards: missing `order`; not a list; n−1 entries; duplicate; index n; `[true, …]`; strings. | Socket.io |
| 9 | Results payloads: the host gets `answerReveal.correctOrder`, `answerDistribution` keyed `"0".."n-1"` with the right counts, and `meanPositions` (checked by hand calculation). Each player gets `yourOrdering` with `outOfPlace` per §4.3, and **no** `meanPositions`. | Socket.io |
| 10 | Game-over: the host summary item has `answerDistribution` over all rows and `meanPositions`. The player recap has `playerAnswer.order` and `answerReveal.correctOrder`. | Socket.io |
| 11 | **Bad stored data** (planted through `mysql` after create, as `test_hotspot.py` does): identity `correctOrder`, wrong-length `correctOrder`, `partialCredit` missing. The game runs to game over without a server error; scores are 0; the reveal is `{type: "ordering"}` without `correctOrder`; `yourOrdering` null; the report contains "Answer key invalid". | Socket.io + report |
| 12 | Export of an ordering-only game → **version 1**; the question's `config` / `answer_data` match the stored ones byte for byte; import into another course → identical question; play it → same scores. | `GET /api/host/games/{g}/export`, `POST /api/host/games/import` |
| 13 | Export of a game with an ordering question carrying a T8 prompt image (plus a hotspot question) → **version 2**, the ordering question has `prompt_image_ref`; round trip → new image IDs, ordering `config` / `answer_data` unchanged. Also through the admin routes. | host and admin export/import |
| 14 | Import errors: an ordering question with identity `correctOrder` in a bundle → 422 "Question N invalid: … shuffled order …", and no game is created. | `POST /api/host/games/import` |
| 15 | Report for a completed session: contains the "Ordering" badge, the correct order in order, "Room's order", and an item `<b>x</b>` rendered as `&lt;b&gt;x&lt;/b&gt;` (escaped). | `GET /api/game/sessions/{id}/report` |
| 16 | Engine scenario (`all_question_types` with the three ordering specs): expected totals = server totals for a multi-player run. | Socket.io (engine) |

Every test deletes what it created (games, courses, sessions) through the existing deletion
paths, which also clear Redis (T5 resource-limit note). Existing tests are not modified or
weakened.

### 9.3 Browser e2e — `tests/e2e/` (Python Playwright)

**Harness:** `tests/e2e/pytest.ini` (`asyncio_mode` not needed; sync Playwright API),
`requirements.txt` (`pytest>=7.4`, `pytest-playwright>=0.5`, `httpx>=0.26`, `python-dotenv>=1.0`),
and `conftest.py`:
- `E2E_BASE_URL` (default `http://localhost:8080`, the nginx port in `docker-compose.yml`; see
  §12 Q1) for the browser, and the API at `{E2E_BASE_URL}/api`.
- Requires the built apps (`npm run build`) served by nginx, so the test runs the production
  paths (`/admin/`, `/host/`, `/player/`) and one shared origin.
- Fixtures over HTTP (not the UI): an admin token from `ADMIN_USERNAME` / `ADMIN_PASSWORD`
  (`.env`), a fresh course and game per test, and teardown deleting them.
- `signed_in(page, token)`: sets `localStorage.token` with `page.add_init_script` before
  navigation, so only the UI under test is driven.
- Viewports: the player context uses `viewport={"width": 375, "height": 667}`, `has_touch=True`,
  `is_mobile=True`. Host and admin use 1280 × 800.
- Selectors use only the `data-testid`s named in §6.7–6.9 plus visible text.
- Run: `pip install -r tests/e2e/requirements.txt && playwright install chromium && pytest
  tests/e2e`. Not in CI (it needs the live stack), the same as `tests/integration/`.

**Tests (`tests/e2e/test_ordering_e2e.py`):**
1. **Admin authors an ordering question.** Open `/admin/` on the fixture game's editor, choose
   "Ordering", type 4 mitosis phases in correct order, keep ACCURACY + partial credit, check that
   the "Players see" preview is not in the typed order, then Save. Through the API: the stored
   `config.items` is a permutation of the typed items that is not in typed order, and mapping
   `correctOrder` back gives the typed order. Re-open the question and confirm the editor shows the
   typed correct order. (Phase 10 runs the same flow against `/host/`.)
2. **Player plays on a phone.** Create the question through the API (known display order), open
   a room through the API, and open the host lobby in a host context. The player context joins at
   `/player/join?code=…` as a guest. The host clicks Start. On the phone: every
   `ordering-item-*` is inside the viewport without scrolling and at least 44 px tall (6 items,
   one 80-character item). Submit is disabled. Tap a wrong item first, press Undo, then tap
   all items in the correct order. The badges show 1..n. Submit is enabled; tap it and see
   "Answer locked in!".
3. **Host reveal.** Continuing 2 with a second phone context that submits one item moved: the host
   clicks Show Results. `ordering-host-correct-order` lists the items in correct order, the
   distribution shows "Perfect 1" and "1 out of place 1", and "Room's order" is present. Phone 1's
   `ordering-result-label` reads "Perfect order!" and its points show 1000. Phone 2 reads "1 item
   out of place", shows 666.67, and its `ordering-your-order` marks the moved item.

## 10. Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Drag-and-drop reordering | Riskiest phone UI: scroll vs drag conflicts, targets under the thumb, poor accessibility (O2). |
| Per-player shuffle | The host screen and room discussion need one shared order; the e2e test needs a predictable one (O3, user decision). |
| Server-side shuffle seeded by question ID | `config` is sent unchanged on several paths, so every one would need a transform. IDs change on import; seeded shuffles are not version-stable and can produce the identity (O3). |
| Store the correct order in `config` and the shuffle in `answer_data` | Inverts the secrecy rule: `config` would leak the answer on every path. |
| Kendall-tau pair fraction | Grades well but cannot be explained on a results screen (O4). |
| Exact-position matching | One moved item can score 0 (O4). |
| Adjacent-pair matching | The same one-step mistake scores differently depending on where it is (O4). |
| `L / n` normalisation | Gives a reversed answer 1/n credit for nothing (O4). |
| Partial credit under COMPLETENESS (the original brief) | COMPLETENESS is participation credit across the app and hotspot; redefining it for one type changes a mode hosts already use (O5). |
| A `partialFraction`-style multiplier | The O4 scale already grades by severity; a boolean covers "exact only" vs "partial" (O5). |
| Reveal a correct order under COMPLETENESS | Mixed message with full points everywhere; opinion rankings have none (O5). |
| Per-item images (T8 option images) | Five T8 code paths for a need the prompt image already covers (O7). |
| Auto-fill the last item | Makes Undo ambiguous; saves one tap (O2). |
| Tap a numbered item to remove it and renumber | Confusing mid-sequence renumbering (O2). |
| Compute the out-of-place items in the browser | A second scorer that can drift; the server already computes it (O10). |
| Optional end labels in `config` ("Earliest" / "Latest") | More schema for what the prompt already says; the editor hints at it instead. |
| Live statistics on the host during the question | Lets slow players copy the crowd (O11). |
| Playwright for Node / Cypress | A second language and test runner; the team's tests are pytest (O13). |

## 11. Known risks and open edges

- **The out-of-place marking is one valid choice, not the only one.** For B A C D, the marking
  says A moved, but B moving is equally valid. The tie-break is deterministic and tested, but a
  student may argue "I only swapped two". The label counts items, and the count is always right.
  Accepted.
- **The partial-credit scale is coarse for n = 3.** The only possible scores are 0, 0.5 and 1. A
  single swap of a 3-item list earns half the points. Authors who want more resolution use 4–6
  items.
- **"Submit as shown" can still earn credit.** O3's ≤ 50 % rule is advisory and enforced only by
  the editor. A hand-written bundle or API call can store a display order worth 80 % if submitted
  unchanged (n = 6, one item moved). The server enforces only "not the identity". Making the
  threshold a server rule is cheap if this proves to matter, but it would also reject existing
  hand-made bundles. Left as an editor rule.
- **Mean positions can mislead.** Two items with avg 2.5 can come from a split room (half put it
  first, half fourth). The host view shows means only, not a full position matrix (scope).
- **Ordering takes longer than other types.** Six items plus reading the prompt can take more
  than 20 s. The editor only hints (5 s per item); a short timer just leaves players unanswered
  (0 points; partial sequences are never submitted). Late joiners get the existing shortened timer
  (minimum 5 s), which is effectively unanswerable for ordering. This is existing behaviour and is
  not changed.
- **Taps are lost on reload.** `sequence` is page state. The player socket reconnects on every
  page change (`pages/README.md` gotcha), but tapping does not navigate, so taps survive
  reconnects but not a reload. Existing reconnect gaps apply.
- **A misconfigured stored `config` produces a socket `error`,** which replaces the player's whole
  game UI (existing gotcha). Only direct DB edits can cause it, because both write paths validate.
  Accepted, and logged as `ordering_config_invalid`.
- **Editor copies drift** (host and admin `OrderingEditor` and editor-page branches), the same
  accepted risk as `HotspotEditor`. Each copy's header comment and README gotcha names the other.
- **Item text is shown as typed.** Players see what the author typed, including Unicode lookalikes
  that defeat the duplicate check (`"Ana phase"` vs `"Anaphase"`). Authors are trusted.
- **The report reflects current questions** (T4 D9): editing items or `correctOrder` after a game
  changes how old answers are shown in the report. Stored submissions are display indices, so
  any reshuffle of a played question (add/remove/Shuffle again) re-maps old answers to other
  items in the report; moves and text edits keep display slots to limit this (§6.9). Stored `points_awarded` do not change.
- **The e2e tests need a built, running stack** and are not in CI, so they can rot unnoticed. This
  is mitigated by running them in each phase's red/green loop and before every push in phases 8–13.
- **The e2e tests touch shared state:** they create courses, games and rooms in the dev database.
  Teardown deletes them, but a crashed run can leave rooms that count toward `MAX_ROOMS` (the
  existing Redis-leak gotcha).
- **Text-only:** subjects that order images (for example "order these skulls by age") are out of
  scope (O7).

## 12. Open questions (resolved 2026-10-05)

- **Q1. e2e base URL.** Resolved: `E2E_BASE_URL`, default `http://localhost:8080`. Checked
  against the running stack (nginx answers on 8080; nothing listens on port 80).
- **Q2. Partial credit in ACCURACY.** Resolved by the coordinator under the user's "complete it
  end to end" instruction: keep the `partialCredit` flag, default on. It strictly contains the
  user's original all-or-nothing ACCURACY idea (flag off), so nothing the user asked for is lost;
  the user is told in the hand-off and can flip the editor default.

## 13. Revision after goldfish test (2026-10-05)

A fresh-context goldfish test of `ecc9efe` found one blocking item (open Q2) and these
non-blocking ones, all applied above:

a. O4 table: the "Adjacent pairs" column is recomputed under one stated definition (correct
   successor pairs); the rejection reason now matches the numbers.
b. §9.2: helper locations corrected (`hapi`/`mysql` in `host_helpers.py`, `create_room` /
   `create_guest_tokens` are functions, `TestSocketClient` in `engine/socket_client.py`).
c. §9.2 test 3: per-field merge, so an `answer_data` patch resends a valid `correctOrder`.
d. §4.1: explicit check order; tests assert containment because of Pydantic's
   "Value error, " prefix; `optionImageIds` gets the T8 message.
e. §6.9: moves no longer reshuffle (items keep display slots unless O3 breaks); §11 notes that a
   reshuffle re-maps a played question's stored answers in the report.
f. §6.9: `orderingFromQuestion` reads `partialCredit` under ACCURACY and warns on an invalid
   stored key instead of silently treating the display order as correct.
g. §6.7: the ordering branch's own `canAnswer`; an "Answer recorded" rung when the reveal has a
   correct order but `yourOrdering` is null.
h. §6.9: `question-type-select` / `question-save` test IDs are new in both editors.
i. §6.10: the simulator uses `correctOrder` only under ACCURACY when it is a valid permutation.
j. §6.4: the report's `n` comes from `ordering_item_count`; the note class is `.ordering-note`;
   "avg 1.40" format shared with the host.
k. §6.8: host `GameOverPage` passes `invalidKey` like `ResultsPage`.
l. O7 / §6.7 / §9.3: 80-character items take up to three lines; the layout check uses a one-line
   prompt.
m. §8 / §9.1: unit tests split so phase 1 imports only `app.schemas.admin`.
n. §6.11: the stale "validation is asymmetric" / "updates bypass validation" README lines are
   corrected.
o. §7 / §8: sample games (old phase 12) move to the T6 branch.
p. §2: the helper list names every §6.2 helper.

### 13.1 Implementation refinements (2026-10-05)

Found while building and in the closing `mean-review`; the sections above still describe the
design, these are the deltas:

a. **e2e harness uses plain Playwright, not `pytest-playwright`** (§9.3): the plugin's
   `pytest-base-url` dependency registers `--base-url`, which clashes with
   `tests/integration/conftest.py` in a shared virtualenv. `tests/e2e/conftest.py` provides its
   own `browser`, `api` and `new_context` fixtures; `requirements.txt` lists `playwright`.
b. **e2e teardown leaves courses** (§9.3 said it deletes them): courses have no delete endpoint,
   the same accepted leftover as `tests/integration/`. Sessions (and their Redis state) and games
   are deleted.
c. **Test 11's report check is its own test** (`test_report_flags_invalid_key`, phase 6), so the
   phase 3 commit was green on its own.
d. **Editor key check mirrors the server** (§6.9): `orderingFromQuestion` flags `keyInvalid`
   unless `answer_data` has exactly `correctOrder` and `partialCredit` with a real bool and a
   non-identity permutation; the warning clears on any edit. The reshuffle effect never runs for
   fewer than two items (it looped on corrupt rows with 0–1 items).
e. **Player results after a reload** (§6.7): the label treats `yourOrdering` as proof of an
   answer, so a reload no longer shows "No answer" next to earned points.
f. **Recap wraps ordering answers** instead of truncating them; only the exact order shows ✓
   (O6). Item buttons are 56 px (`min-h-14`) as specified; the 375 × 667 no-scroll check passes.
g. **Test 12 also plays the imported game** and checks the same scores; report and e2e
   distribution assertions check counts, not just labels.
