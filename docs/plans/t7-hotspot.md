# T7 — Hotspot question type (canvas, tap-a-point, banded distance)

Status: **agreed design, pre-implementation; goldfish-tested 2026-10-01 and revised** (§13 lists
what the revision changed). Owner: Arjun Kaneriya.
This is the team's canvas-based T7 type; the second T7 type is designed separately by Vincent
Zhou. Depends on T4 (`docs/plans/t4-ui-restructuring.md`, not yet implemented) and on T8 image
storage (owned by Vincent, not yet designed). §4 is the contract this design needs from T8.

Read with the context hierarchy: `backend/app/README.md` (its "Adding a question type touches"
list is the backbone of §7), `frontend/README.md`, and the per-directory READMEs they link.

## 1. Problem

T7 requires two new question types, one of which uses an HTML canvas as the player's interaction
surface. **Hotspot**: the author picks an image and marks a target point with two radii; each
player taps one point on the image on their phone; the server scores the tap by its distance from
the target — full points inside the inner radius, partial credit inside the outer radius, zero
beyond. Classroom use: "tap Cairo on this map". Party use: "tap the penalty spot".

The type is a full vertical slice: validation, scoring, live game payloads, player canvas, host
live and results views, authoring UI, export/import, HTML report, simulator, integration tests,
and sample games.

## 2. Technical plan (summary)

1. **No migration for hotspot itself.** `questions.type` is a free string and `config` /
   `answer_data` are schemaless JSON (`models/README.md`). New type string: `hotspot`.
2. `config` (sent to clients) holds `imageId` and `aspectRatio`; `answer_data` (server-only)
   holds the target `x`, `y`, `innerRadius`, `outerRadius`, `partialFraction`.
3. Coordinates are normalized to [0, 1] per axis; **distance is aspect-corrected** and radii are
   fractions of the image's **longer side**, so the target is a true circle on screen (§5.2).
4. Scoring is a **flat band** (§5.2). `is_correct` means "inside the inner radius".
5. Two shared helpers in `game_service`: `hotspot_target` parses and validates the stored target
   (returns `None` on bad data, never raises), and `hotspot_band` computes the band. Scoring,
   `record_answer`, the summaries, the gateway's results emit and `report_service` all call them
   (no further copy of question-type logic). Bad stored data scores as a miss and is logged (§5.4).
6. Images are referenced by T8 image ID and fetched by the client with `fetch` + bearer token
   into a blob (§4).
7. Export/import gains a **version 2** bundle that embeds image bytes; version 1 still imports
   unchanged (§6).
8. Authoring is a self-contained `HotspotEditor` component in the host editor (T4 phase 2);
   Vincent copies it into the admin editor in T4 phase 3.

## 3. Decisions (with rationale)

### H1. Target region is a circle (center + two radii)
Banded distance needs a reference point; a polygon or rectangle has no natural "distance from the
answer". One center plus inner/outer radii is also the easiest region to author on a phone-sized
preview.

### H2. Flat band, not linear falloff
Inside inner → `points_value`; inside outer → `points_value × partialFraction`; else 0.
`partialFraction` is per question, default 0.5. Players can predict their score from the reveal
rings, and boundary behaviour is testable. Modelled on Guess the Correlation (full within 0.05,
partial within 0.10).

### H3. Aspect-corrected distance, radii as fractions of the longer side
Per-axis normalized distance would turn a radius into an ellipse on any non-square image (a 0.05
radius on a 2:1 map would be twice as wide in pixels as tall). Correcting by aspect ratio makes
"radius 0.05" mean "5 % of the image's longer side" in every direction, which is what an author
sees when the editor draws the ring.

### H4. `aspectRatio` is snapshotted into `config`
Scoring needs the aspect ratio. Storing it in `config` (set by the editor from the loaded image)
keeps scoring a pure function of the question row — no T8 read per answer, and `calculate_score`
stays synchronous. It is correct for the question's lifetime because of contract invariant **C1**
(§4): bytes under an image ID never change.

### H5. Host shows no taps while the question is open
Live taps on a projector let slow players copy the crowd. During `QUESTION` the host shows the
image and the answered count only; taps and rings appear at `RESULTS`.

### H6. Player taps to place, then confirms
A tap places a marker, a later tap moves it, a Submit button sends it. One-tap-submit punishes
fat fingers on small targets.

### H7. Minimum inner radius 0.02
About 7 px on a 360 px-wide phone showing a landscape image full-width. Smaller targets are
effectively random without pinch-zoom (out of scope). The editor shows the radius live so authors
see how small it is.

### H8. Export uses a version 2 bundle with embedded images
Image IDs are instance-specific, exactly the reason T4 D10 keeps `course_id` out of bundles. A
bundle that carries only `imageId` would not import anywhere else, including into a fresh clone
for grading. T6 explicitly allows this: *"If your image work (T8) extends the format, you may bump
the version — but importing unmodified version-1 files must keep working, and your game files must
import cleanly into your own application either way"* (`instructions.md`, T6, "Format version"
row). See §6.

### H9. HotspotEditor ownership
Arjun writes `HotspotEditor` as a self-contained component in the host app (T4 phase 2 host
editor). Vincent copies it into the admin editor in T4 phase 3, changing only import paths. This
continues T4's accepted "port and keep copies" approach (T4 §5) and keeps admin directories with
their owner.

### H10. Sample content is public domain, openly licensed, or self-made
No copyrighted characters or images in sample questions. Every sample image's source and licence
is recorded (§8).

### H11. Image loading time counts against the question timer (accepted)
The authoritative timer is server-side (the gateway's timer task locks the question); the client
cannot move it, and a client-reported "image ready" time would be trivially gameable. So time spent
loading the image is part of the answer window. This is acceptable because:
- T8's per-image size cap (C8) keeps a single image small enough to load in well under a second on
  a classroom connection (sample images are ≤ 150 KB, §8);
- the player app starts fetching the image **the moment `new_question` arrives** (in
  `GameLayout`, §7.7), so loading overlaps with the player reading the prompt;
- images are served with immutable cache headers (C3), so repeat plays of a game and reconnects
  mid-question load from the browser cache.

### H12. The player's result label comes from a server-computed band
The player results screen labels a hotspot answer from `yourBand` (`"inner" | "outer" | "miss"`,
or `null` under COMPLETENESS), sent in the per-player results emit (§7.4). Labelling from points
is wrong whenever points don't identify the band: `points_value = 0` makes every tap equal full
points, `partialFraction = 1` makes an outer tap equal full points, and `partialFraction = 0`
makes an outer tap equal a miss. Computing the band in the browser would need a TypeScript copy of
§5.2 that can drift from the Python one; the server already computes it with `hotspot_band`. The
band is the player's own data, so sending it leaks nothing.

## 4. T8 image contract (addressed to Vincent)

Vincent — this is everything hotspot needs from T8, and nothing more. Upload API shape, size
and type limits, thumbnails, the management UI, and how "replace" works are all yours to design,
as long as these hold. If any of them is a problem, let's change this section before either of us
implements against it.

| # | Requirement | Why hotspot needs it |
|---|---|---|
| **C1** | **Immutability invariant: the bytes, and therefore the aspect ratio, stored under a given image ID never change.** How T8 implements "replace" around that is your design (e.g. replace = upload a new image and repoint questions; or replace refused while referenced). | Hotspot targets are stored in coordinates relative to the image, and `config.aspectRatio` is snapshotted at authoring time (H4). If the pixels under an ID changed, every saved target would silently point at the wrong place and scoring would use a wrong aspect ratio. It is also what makes C3's immutable cache headers safe: a cached response can never be stale. |
| **C2** | **Reference by integer ID.** Images are rows with a positive integer primary key. Hotspot stores it as `config.imageId`. | `config` is plain JSON; an integer is the simplest validated reference. The image itself is not secret (the target is in server-only `answer_data`), so the ID can travel to clients. |
| **C3** | **Fetch endpoint:** `GET /api/images/{id}` returns the raw bytes with the correct `Content-Type`; 404 if unknown. At minimum it must be readable by **any authenticated token, including GUEST tokens** (players are often guests). Tightening beyond `require_user` is fine only if a player in a live room can still read the image of the current question. **Every 200 response sends `Cache-Control: private, max-age=31536000, immutable`** (`private`, because the request carries a bearer token and shared caches such as nginx must not store it; `immutable`, because of C1). 404s must not carry it. | Player and host apps fetch with `fetch` + bearer header into a blob URL and draw it on a canvas. A plain `<img src>` cannot send the token (same reason T4's downloads use `fetch` + blob). The blob is same-origin, so the canvas is not tainted. `fetch` uses the browser HTTP cache by default, so with these headers a repeat play of the game, a reconnect mid-question, the results screen and the game-over recap re-read the image locally instead of hitting the backend (H11). |
| **C4** | **Existence check callable from Python:** e.g. `image_service.image_exists(db, image_id) -> bool`. | Pydantic can't query the DB, so `content_service` checks `imageId` on hotspot create, update and import (§7.3). |
| **C5** | **Bytes and type callable from Python:** e.g. `image_service.get_image(db, image_id) -> (content_type, bytes)` or `None`. | The standalone HTML report embeds the image as a data URI; export embeds it in the v2 bundle. |
| **C6** | **Create callable from Python, flush-only:** e.g. `image_service.create_image(db, content_type, data: bytes) -> int`, which validates type/size by T8's own rules, raises a 422-type error on bad input, and **flushes but does not commit**. | v2 import creates images inside the import transaction. Because T8 stores images in MySQL, a later failure in the same import rolls the images back with everything else (`get_db` rolls back on error). |
| **C7** | **Refuse deleting a referenced image:** deleting an image that any question references is a 409. For hotspot, "references" means a `questions` row with `type = 'hotspot'` and `config.imageId` equal to the image's ID (a MySQL JSON lookup, e.g. `JSON_EXTRACT(config, '$.imageId') = :id`). Filter on `type`: other types' `config` may contain integers that are not image IDs. T8 adds its own image fields to the same check. | Otherwise a hotspot question breaks mid-game or in a later session, the same class of problem as T4 D6. |
| **C8** | **Request size:** nginx (`nginx/nginx.dev.conf`) sets no `client_max_body_size`, so `/api/` uploads are capped at nginx's 1 MB default. T8 picks the limit; please set it so a v2 bundle containing images up to your max size (× ~1.37 for base64) still passes, or tell me the cap and I'll document it. | v2 bundles are uploaded through the same proxy. T8's per-image size cap is also what H11 relies on to keep a single image load sub-second; tell me the number so H11 can cite it. |

Names in C4–C6 are suggestions; the spec only depends on the behaviour. When T8's design is
written, link it here and replace "e.g." names with the real ones.

**Not required from T8:** an image picker UI is welcome (HotspotEditor will accept one, §7.9),
but HotspotEditor ships with a fallback numeric "Image ID" field so hotspot doesn't block on it.

## 5. Data shape, validation, scoring

### 5.1 Stored question

- `type`: `"hotspot"`.
- `config` (sent to clients): exactly `{ imageId, aspectRatio }`.
  - `imageId`: positive integer (not bool). Must exist (C4) — checked in `content_service`, not
    Pydantic.
  - `aspectRatio`: finite number, image width ÷ height, in **[0.2, 5]**.
  - Any other key → 422 (in particular `imageRef`, which exists only inside bundles, §6).
- `answer_data` (server-only), required when `grading_type == "ACCURACY"`: exactly
  `{ x, y, innerRadius, outerRadius, partialFraction }`.
  - `x`, `y`: finite numbers in [0, 1]; target center as fractions of width and height
    (origin top-left, y downward).
  - `innerRadius`: finite, **0.02 ≤ innerRadius ≤ 0.5** and **innerRadius ≤ outerRadius**. The
    0.5 cap matches the editor slider (§7.9), so every stored question can be shown and edited.
  - `outerRadius`: finite, **innerRadius ≤ outerRadius ≤ 1**. Equal radii are allowed (no
    partial band).
  - `partialFraction`: finite, in [0, 1].
  - Any other key → 422.
  - Numbers may be int or float; **bool is rejected** (Python `True` is an `int`).
- Under `COMPLETENESS`, `answer_data` is not checked (matches FITB/MC behaviour). `config` is
  always checked.
- Key naming is camelCase, matching client payloads and FITB (`schemas/README.md` asks new types
  to choose deliberately).

### 5.2 Distance and bands

Let the tap be `(px, py)`, the target `(x, y)`, and `A = aspectRatio`. Distance is measured in
units of the image's longer side:

- If `A ≥ 1` (landscape or square): `dx = (px − x)`, `dy = (py − y) / A`.
- If `A < 1` (portrait): `dx = (px − x) × A`, `dy = (py − y)`.
- `d = √(dx² + dy²)`.

(Derivation: normalized x is a fraction of width W, y of height H = W / A; dividing pixel
offsets by the longer side gives the above.)

Band:
- `d ≤ innerRadius` → `"inner"`
- `innerRadius < d ≤ outerRadius` → `"outer"`
- otherwise → `"miss"`

Both boundaries inclusive. Implemented once, as two module-level pure functions in
`game_service`:

- `hotspot_target(question_id, config, answer_data) -> HotspotTarget | None` — reads
  `aspectRatio` from `config` and `x`, `y`, `innerRadius`, `outerRadius`, `partialFraction` from
  `answer_data`, and returns them as a small frozen dataclass if they satisfy §5.1's rules
  (`aspectRatio` in [0.2, 5]; the others as listed; bool rejected; finite). Otherwise it returns
  `None` and logs (§5.4). It never raises, whatever the stored JSON contains (including `None`,
  a non-dict, or strings).
- `hotspot_band(target: HotspotTarget, px, py) -> "inner" | "outer" | "miss"` — the formula above.

### 5.3 Score (`calculate_score` branch)

- `COMPLETENESS`: existing early return (full points for any answer) — unchanged; it fires
  before the type branch.
- `ACCURACY`, `hotspot`:
  - Read `x`, `y` from the submission (already shape-checked by the gateway, §7.4). If missing or
    malformed → `ScoreResult(0, False)` (defensive, matches other branches).
  - `hotspot_target(...)` is `None` → `ScoreResult(0, False)` (§5.4).
  - `"inner"` → `points_value`, `is_correct = True`.
  - `"outer"` → `points_value × partialFraction`, `is_correct = False`.
  - `"miss"` → `0`, `is_correct = False`.
  - Points are floats (`points_awarded` is float since migration 003); no rounding.

### 5.4 Bad stored target data: miss-and-log, never crash

Until T4 phase 3, the admin update path stores `config` / `answer_data` without validation
(§7.1), so a hotspot row can hold a target that §5.1 would reject. No caller may crash mid-game on
such a row. Rule, for a hotspot question under ACCURACY where `hotspot_target` returns `None`:

- **Log:** `logger.warning("hotspot question %s has invalid target data; scoring as miss",
  question_id)` with the module's existing logger. One line per call; volume is bounded by one
  question's answers.
- **Score:** `ScoreResult(0, False)`; distribution key `"miss"`; `yourBand` `"miss"`.
- **Reveal** (gateway and report): `{type: "hotspot"}` with **no** target fields. Clients draw
  the image and taps without rings; the player's label is "Miss".
- **Summaries / host `taps`:** every tap gets band `"miss"`.
- **Report:** renders taps without rings, plus the note "Target data invalid".

Under COMPLETENESS the target is never read, so bad data there is harmless. A bad
`config.imageId` (unknown image) is already handled by the clients' "Image unavailable" path.

## 6. Bundle format version 2

### 6.1 Format

Version 2 = version 1 plus a top-level `images` array; hotspot questions reference images by a
bundle-local `imageRef` string instead of an `imageId`.

```json
{
  "format": "buzzer/game",
  "version": 2,
  "game": { "title": "…", "description": "…", "max_players": 150 },
  "images": [
    { "ref": "img1", "content_type": "image/png", "data_base64": "iVBORw0KGgo…" }
  ],
  "questions": [
    {
      "type": "hotspot",
      "grading_type": "ACCURACY",
      "prompt": "Tap Cairo.",
      "config": { "imageRef": "img1", "aspectRatio": 2.0 },
      "answer_data": { "x": 0.5868, "y": 0.3331, "innerRadius": 0.02,
                       "outerRadius": 0.05, "partialFraction": 0.5 },
      "time_limit_seconds": 20,
      "points_value": 1000
    }
  ]
}
```

Bundle-level keys are snake_case (as in v1: `time_limit_seconds`); keys inside `config` /
`answer_data` follow the stored question shape (camelCase).

### 6.2 Export (`content_service.export_game`)

- Collect the distinct `config.imageId` values of the game's hotspot questions, in question order.
- **None** → write exactly today's version 1 bundle (image-free games export byte-for-byte as
  before).
- **Some** → write version 2: assign refs `img1`, `img2`, … in first-use order; fetch each via C5
  and base64-encode it into `images`; in each hotspot question's **exported copy** of `config`,
  replace `imageId` with `imageRef`. Never mutate the ORM row's `config` (JSON column mutation
  would be persisted on flush).
- If C5 returns `None` for a referenced image (should be impossible under C7) → 409
  `ConflictError("Question N references missing image {id}")`.
- T8's own image fields (prompt images, option images) extend the same mechanism: T8 adds its
  fields to the ref-rewrite list. Hotspot defines only `config.imageId`.

### 6.3 Import (`content_service.import_game`)

Errors keep today's import style: `HTTPException(422, detail="…")`-equivalent messages naming the
question or image (T4 moves this into `content_service`; it raises the project's 422 error type
there with the same messages). **N and K are 1-based**, matching today's import message
(`f"Question {i + 1} invalid: …"` in `routers/admin.py`).

1. Parse, check `format` (unchanged). `version` must be **1 or 2**; anything else → 422
   "Unsupported version …; server supports versions 1 and 2".
2. Validate the `game` block with `GameMeta` (T4 §6.1.3), as for v1.
3. **Version 1:** unchanged path, except a `hotspot` question in a v1 bundle → 422
   "Question N: hotspot questions require a version 2 bundle". (A v1 `imageId` would point at an
   arbitrary local image.)
4. **Version 2:**
   1. `images` must be a list (may be empty). Each entry has a non-empty string `ref` (unique in
      the bundle), a string `content_type`, and a `data_base64` that decodes strictly
      (`base64.b64decode(..., validate=True)`). Violations → 422 "Image K: …".
   2. Every hotspot question's `config` must have `imageRef` matching an `images[].ref` and must
      **not** have `imageId`. Non-hotspot questions are untouched. Violations → 422
      "Question N: …".
   3. Validate every question with `QuestionCreate`, substituting a placeholder `imageId` of `1`
      for each `imageRef` (so structural errors are reported before any image is created).
   4. Create each **referenced** image via C6 (unreferenced entries are ignored, not created);
      map `ref → new id`.
   5. Create the game and questions with the real `imageId`s, `order_index` 0..n-1, prompts
      sanitised (existing bleach rules), then the T4 auto-grant rule.
   6. All of this is one transaction; any failure rolls back images too (C6).
5. Every existing `sample_games/*.json` (version 1) must keep importing — covered by an existing
   T4 phase 1 test and re-asserted in §10. That T4 test imports through the **admin** endpoint,
   which only accepts version 2 once T4 phase 3 delegates it to `content_service`; §8 / §9 stage E
   sequence the sample-game upgrade accordingly.

## 7. Detailed implementation

### 7.1 `backend/app/schemas/admin.py`

- Add `hotspot` to the `type` regex in **both** `QuestionCreate` and `QuestionUpdate`.
- `QuestionCreate.validate_structure`: `hotspot` branch implementing §5.1 exactly (config always;
  answer_data when ACCURACY; reject extra keys, bools, non-finite numbers).
- `QuestionUpdate` gets no validator of its own: T4 D8 makes `content_service.update_question`
  merge the patch and validate the merged result with `QuestionCreate`, so the hotspot rules apply
  to updates automatically. **Until T4 phase 3**, the admin router's `update_question` still writes
  unvalidated JSON (existing gap, `schemas/README.md`); not fixed separately here.

### 7.2 `backend/app/services/game_service.py`

- `HotspotTarget`, `hotspot_target(...)` and `hotspot_band(...)` per §5.2 (pure, module level).
  Every caller below gets the target with `hotspot_target` once per question and applies §5.4 when
  it is `None`.
- `calculate_score`: `hotspot` branch per §5.3.
- `record_answer` distribution key: for `hotspot` under ACCURACY, increment the band name
  (`"inner"`, `"outer"`, `"miss"`) via the existing `increment_answer_dist`. Under COMPLETENESS,
  no distribution key (there is no target). No new Redis keys.
- `get_host_question_summary` (game-over, host): for hotspot items, `answerDistribution` = band
  counts computed from each `player_answer` with `hotspot_band` (ACCURACY only), and a new field
  `taps: [{x, y, band}]` (band `null` under COMPLETENESS). Cap: the first 500 rows ordered by
  `session_scores.id` ascending (insertion order, i.e. answer order); band counts are computed over
  **all** rows, not just the capped 500.
- `get_player_question_summary` (game-over, player recap): confirm it returns `config` and the
  player's own `answer_data` (it selects `Question.config` today); the player recap draws from
  those plus the reveal. No change expected beyond the reveal (§7.4).

### 7.3 `backend/app/services/content_service.py` (T4 phase 2, new)

- `create_question`, `update_question` (after the D8 merge validates), and `import_game`: if the
  resulting question is `hotspot`, call C4 for `config.imageId`; unknown → 422 on field
  `config.imageId` using T4's `RequestBodyInvalidError` shape (`loc: ["body","config","imageId"]`,
  `msg: "Image {id} does not exist"`). For import, the C6-created IDs exist by construction.
- `export_game` / `import_game`: §6.2 / §6.3. Implement v2 **only here**, not in today's
  `routers/admin.py` handlers (which phase 3 replaces), to avoid writing it twice.

### 7.4 `backend/app/websocket/gateway.py`

- `_question_payload`: no change (`config` already carries `imageId`, `aspectRatio`).
- `_answer_reveal`: `hotspot` (ACCURACY) → `{type: "hotspot", x, y, innerRadius, outerRadius}`,
  taken from `hotspot_target`; if it is `None`, `{type: "hotspot"}` with no target fields (§5.4).
  `partialFraction` is omitted (the player sees their points directly). COMPLETENESS keeps the
  existing `{type: "completeness"}` early return.
- `on_submit_answer`, next to the `multi_select` check: for `hotspot`, `answer_data` must contain
  `x` and `y`, each int or float but not bool, finite, in [0, 1]. Otherwise emit an error
  ("hotspot answer must include x and y between 0 and 1") and return without recording. On
  success, pass a **normalized** `{x: float, y: float}` (extra client keys dropped) to
  `record_answer`, so `session_scores.answer_data` stores only the point.
- `host_advance`, `QUESTION → RESULTS` host emit: for hotspot questions add
  `taps: [{x, y, band}]`. Get them by adding `_Score.answer_data` to the existing `q_score_rows`
  column select (keep selecting columns, not ORM objects — MissingGreenlet comment there), compute
  `band` with `hotspot_band` (ACCURACY) or `null`; cap 500 in the same order as §7.2 (order the
  select by `_Score.id`). `answerDistribution` (band counts from Redis) is unchanged in mechanism.
- Same transition, **per-player emit** (to `user:{id}`): for hotspot questions add
  `yourBand: "inner" | "outer" | "miss" | null` (H12), computed with `hotspot_band` from that
  player's own row in `q_score_rows`. `null` under COMPLETENESS; `"miss"` when the target is
  invalid (§5.4); `null` when the player did not answer (the existing unanswered fields apply).
  The per-player emit still carries **no** `taps` (no other players' data).

### 7.5 `backend/app/services/report_service.py`

- Label/badge: `"hotspot": ("Hotspot", "badge-hotspot")` plus a CSS class.
- `_answer_reveal` (its own copy): add the same hotspot shape as §7.4, including the §5.4
  no-target-fields case.
- `_extract_answer_key`: hotspot → band name, using `game_service.hotspot_target` and
  `hotspot_band` (import them; do not add another copy). Invalid target → `"miss"` (§5.4).
- New renderer for hotspot questions: an inline `<svg>` with `viewBox` matching the aspect ratio,
  containing an `<image href="data:{content_type};base64,…">` from C5, the inner and outer rings
  (ACCURACY), and every tap as a small dot coloured by band; a legend with band counts. No player
  names (report stays PII-free). If C5 returns `None`, render the rings and taps on a blank
  rectangle with "image unavailable". If `hotspot_target` is `None`, omit the rings and add the
  note "Target data invalid" (§5.4).
- Known cost: each embedded image adds its base64 size to the report. Accepted (no Pillow
  dependency for downscaling).
- Not part of hotspot: `report_service`'s missing `multi_select` rendering (T4 §7) remains a
  known edge; it may be fixed in the same MR as a separate commit if time allows.

### 7.6 Frontend — shared pieces (each app gets its own copy; the apps share no code)

- `src/lib/images.ts` in host and player (and admin, copied by Vincent): `loadImageUrl(imageId)`
  does `fetch('/api/images/{id}')` with the bearer token, returns an object URL; the caller revokes
  it on unmount. 404/network failure → a typed error the caller renders as "Image unavailable".
  Use `fetch`'s default cache mode (no `cache: 'no-store'`), so C3's immutable headers let repeat
  loads come from the browser cache.
- Canvas layout rule (all hotspot canvases): the drawn image is letterboxed inside the canvas using
  `config.aspectRatio`, so layout is fixed before the image loads. Canvas backing size = CSS size ×
  `devicePixelRatio`. Ring radius in CSS px = `radius × longer side of the drawn image in CSS px`.
- Colours: read from CSS variables at draw time (`getComputedStyle`), so T9 theming applies to the
  canvas; until T9 lands, fixed fallback values. Bands: inner = success colour, outer = warning,
  miss = danger, COMPLETENESS taps = neutral.
- `src/types/game.ts` in host **and** player: `HotspotConfig { imageId; aspectRatio }`, the
  hotspot `AnswerReveal` variant, `HotspotTap { x; y; band: 'inner'|'outer'|'miss'|null }`,
  optional `taps` on the host results and game-over item types, optional
  `yourBand: 'inner'|'outer'|'miss'|null` on the player results type (player only), and target
  fields optional on the hotspot reveal (§5.4) (`frontend/README.md`: payload types are
  hand-written in both apps).

### 7.7 Player app (`frontend/player/src/`)

- `pages/game/GameLayout.tsx` — **image prefetch (H11):** in the `new_question` handler, if the
  question is `hotspot`, call `loadImageUrl(config.imageId)` immediately, before navigating, and
  expose the result through the game context as `questionImage: { imageId, status: 'loading' |
  'ready' | 'error', url? }`. Revoke the previous object URL when a new question replaces it and on
  unmount. `QuestionPage` and `ResultsPage` read this instead of fetching themselves, so one
  question costs one fetch.
- New `components/HotspotCanvas.tsx`, two modes:
  - **interactive**: pointer events on the canvas (`touch-action: none` so taps don't scroll or
    zoom). Tap → convert client coordinates through `getBoundingClientRect` and the letterbox
    offset to normalized `(x, y)`; taps in the letterbox area are ignored. Draws a marker at the
    current point; a new tap moves it.
  - **display**: draws the image, optional rings (from a reveal), and given taps.
  - `aria-label` with the prompt. A keyboard alternative is out of scope (§11).
- `pages/game/QuestionPage.tsx`, `hotspot` branch: shows the prompt (the player app normally does
  not — here the player needs it with the image), the interactive canvas sized to the viewport
  width and at most ~60 % of viewport height, and a **Submit** button disabled until a point is
  placed (H6). Before emitting, re-check `0 ≤ x, y ≤ 1` client-side: any server `error` event
  replaces the whole game UI (`pages/README.md` gotcha). While `questionImage.status` is
  `'loading'`, show the letterboxed canvas with a spinner and Submit disabled; the server timer
  keeps running (H11). If the image fails to load, show "Image unavailable" and no Submit; the
  player is simply unanswered.
- `pages/game/ResultsPage.tsx`: display canvas with the player's own tap (from `lastAnswerData`)
  and the reveal rings (none if the reveal has no target fields, §5.4). Label from **`yourBand`**
  (H12), never from points: `"inner"` → "Bullseye!", `"outer"` → "Close!", `"miss"` → "Miss",
  `null` → existing "Recorded" wording (COMPLETENESS) or the existing unanswered wording.
- `pages/game/GameOverPage.tsx` recap: small display canvas with own tap + rings, image loaded via
  `loadImageUrl` per hotspot question (served from the browser cache, C3); `describeAnswer` gets a
  hotspot case (e.g. "Tapped (0.42, 0.17)"). No band label in the recap.

### 7.8 Host app (`frontend/host/src/`)

- New `components/HotspotView.tsx` (display only): image, optional rings, optional taps, legend
  from `answerDistribution` ("Bullseye N · Close N · Miss N") under ACCURACY. Under COMPLETENESS
  there are no band counts, so the band legend is **hidden** and replaced by "N taps" (the length
  of `taps`, or "500+ taps" at the cap).
- `pages/game/QuestionPage.tsx`: hotspot shows the image (no rings, no taps — H5) beside the
  existing prompt, timer and answered count.
- `pages/game/ResultsPage.tsx`: `HotspotView` with reveal rings and `taps`; COMPLETENESS shows
  taps in neutral colour without rings.
- `pages/game/GameOverPage.tsx`: per-question card uses `HotspotView` with the summary's `taps`.

### 7.9 Authoring — `frontend/host/src/components/HotspotEditor.tsx` (T4 phase 2)

Self-contained: imports only its own app's `lib/images.ts`, `lib/utils.ts` (`cn`) and
`components/ui/*`, so Vincent can copy it into `frontend/admin/src/components/` in phase 3 with
import-path changes only.

- Props: the question's current `config` and `answerData`, an `onChange(config, answerData)`
  callback, and an optional `renderImagePicker` slot for T8's picker. Without the slot it renders
  a numeric **Image ID** input.
- On image load, sets `config.aspectRatio = naturalWidth / naturalHeight`. The host editor's Save
  is disabled while a hotspot question has no loaded image (so `aspectRatio` is never guessed).
- Click/tap on the preview sets `x`, `y`. Three sliders: inner radius (0.02–0.5), outer radius
  (inner–1.0), partial fraction (0–1, step 0.05, default 0.5). Rings are drawn live using the
  §7.6 layout rule, so what the author sees is exactly what scoring measures.
- Defaults for a new hotspot question: center (0.5, 0.5), inner 0.03, outer 0.08, partial 0.5.
- Integrated into T4's host `QuestionEditorPage.tsx` as the type-specific panel for `hotspot`;
  `hotspot` added to its type dropdown. Server 422s (§5.1, §7.3) show inline via the existing
  `errorMessage()`.

### 7.10 Tooling

- `scripts/simulate_players.py`: `_make_answer` → `{"x": random(), "y": random()}` (uniform; the
  simulator can't see the target); `_answer_str` → `"(0.42, 0.17)"`.
- `tests/integration/engine/scoring.py`: hotspot branch in `compute_question_score` mirroring §5.2
  / §5.3 exactly, and in `_build_reveal`. Scenario tap points are chosen **at least 0.005 away from
  every band boundary**, so float rounding cannot flip an expected band.

### 7.11 READMEs (`.claude/rules/context-sync.md`)

Update the READMEs of every directory touched: `backend/app/schemas/`, `services/`, `websocket/`,
`backend/app/README.md` (type list), `frontend/player/src/{pages,components,lib}/`,
`frontend/host/src/{pages,components,lib}/`, and `frontend/README.md` (new canvas components,
copied `images.ts`). Add a gotcha to host `components/README.md`: `HotspotEditor` has an admin
copy to keep in sync.

## 8. Sample games (T6) and image licensing

Each of Arjun's two T6 games gains one hotspot question; both files become **version 2** bundles
(§6) with the image embedded.

**Sequencing:** the two files stay **version 1, without the hotspot question**, until the version 2
import path exists on every endpoint that imports them — `content_service.import_game` (stage C)
**and** the admin import endpoint delegating to it (T4 phase 3, stage D), because T4 §6.4 test 1
imports every `sample_games/*.json` through the admin endpoint. The upgrade is stage E (§9). Until
then the files import everywhere exactly as today. Source images live in `sample_games/images/`, with a
`sample_games/images/README.md` recording source, licence and how each was produced. Keep each
image ≤ 150 KB (palette PNG) so a bundle stays well under the 1 MB proxy limit (C8).

| Game | Question | Image | Licence |
|---|---|---|---|
| Classroom | "Tap Cairo." ACCURACY, 20 s. Target `x = 0.5868, y = 0.3331` (Cairo 30.04° N, 31.24° E), inner 0.02, outer 0.05, partial 0.5, `aspectRatio` 2.0. | `world_map.png`, 1200 × 600, **unlabelled** country outlines rendered by Arjun from **Natural Earth** 1:110m Admin 0 data in plain equirectangular projection covering exactly −180..180° longitude and −90..90° latitude. | Natural Earth data is **public domain** (naturalearthdata.com terms of use). The rendered PNG is released CC0. |
| Party | "Tap the penalty spot in front of the left goal." ACCURACY, 15 s. Target `x = 0.1048, y = 0.5` (11 m from the goal line on a 105 × 68 m pitch), inner 0.02, outer 0.05, partial 0.5, `aspectRatio` ≈ 1.5441. | `soccer_pitch.png`, 1050 × 680, a plain pitch diagram (lines, boxes, arcs; **no penalty-spot dot**) drawn by Arjun. | **Self-made**, released CC0. |

Target derivation for the map (record it in the images README): for an equirectangular image of
the full globe, `x = (lon + 180) / 360`, `y = (90 − lat) / 180`. The image must have no margins,
or the formula is off.

## 9. Phases and dependencies

Two blockers: **T4 phase 2** (Arjun; `content_service`, host editor) and **T8** (Vincent;
undesigned). Order of work:

| Stage | Can start | Contents |
|---|---|---|
| **A — builds now** | Immediately, on a branch from `main` | §7.1 schema branch; §7.2 `hotspot_band`, scoring, distribution, summaries; §7.4 gateway reveal, answer check, results `taps`; §7.5 report renderer (image part stubbed to "image unavailable"); §7.6–7.8 player/host canvases and types; §7.10 simulator and engine scoring. Front-end canvases can be developed against any locally served test image. |
| **B — waits on T4 phase 2** | After T4 phase 2's `content_service` and host editor exist (same owner; may be done in the same branch series) | §7.3 image-existence checks in create/update; §7.9 HotspotEditor in the host editor. |
| **C — waits on T8** | After T8 merges with C1–C8 satisfied | Wire C3 into `images.ts`, C4 into §7.3, C5 into the report and export, C6 into import; §6 v2 export/import; every integration test that needs a real hotspot question (§10, marked **T8**). Sample games stay version 1 (§8). |
| **D — T4 phase 3 (Vincent)** | After stage B | Copy HotspotEditor into the admin editor; admin router delegating to `content_service` gives admins the hotspot existence check, update re-validation, and version 2 import/export. |
| **E — sample games** | After **both** C and D | §8: add the hotspot question to Arjun's two games and convert them to version 2; §10 test 14's second half. |

Gaps until stage D, both from the admin `create_question` / `update_question` handlers
(pre-phase-3) skipping hotspot checks:
- **Dangling `imageId`** (no existence check): the player sees "Image unavailable" and is scored
  unanswered.
- **Invalid target data** (update writes unvalidated JSON): scored as a miss for everyone and
  logged, never a crash (§5.4).

## 10. Tests (T5)

Integration tests live in `tests/integration/test_hotspot.py` and run against the live stack, except
test 18, a unit test in `tests/unit/test_hotspot.py` that imports `app.services.game_service`
directly (as `tests/unit/test_auth.py` imports `app.main`).

**T8** = needs a real image (T8 upload) and therefore waits for stage C. Unmarked tests run as soon
as their stage merges. **Endpoint** is the route the test calls; `{g}` is a game ID, `{q}` a question
ID. Questions for socket tests (6–10, 17) are created through `POST /api/host/games/{g}/questions`.
Endpoints under `/api/host/` exist from T4 phase 2.

| # | Test | Endpoint | Needs |
|---|---|---|---|
| 1 | Create hotspot: each §5.1 violation → 422 (missing `imageId`; bool `imageId`; `aspectRatio` 0 / 6 / NaN; extra config key `imageRef`; ACCURACY missing `answer_data` key; `x` = 1.1; `innerRadius` 0.01; `innerRadius` 0.6; `innerRadius > outerRadius`; `outerRadius` 1.5; `partialFraction` −0.1; extra answer_data key). Structural 422s come from request-body validation, before any image lookup. | `POST /api/admin/games/{g}/questions` (exists today; `QuestionCreate` validates) | — |
| 2 | Create hotspot with a nonexistent `imageId` → 422 with `loc` `config.imageId`. | `POST /api/host/games/{g}/questions` (the admin route skips the check until phase 3, §9) | T4 ph. 2 |
| 3 | Create hotspot with a real image → 201; question listed with the exact `config`/`answer_data`. | `POST`, then `GET /api/host/games/{g}/questions` | **T8** |
| 4 | Update hotspot re-validation: each of a few §5.1 violations sent as a PUT patch → 422 `VALIDATION_ERROR`; stored row unchanged. | `PUT /api/host/games/{g}/questions/{q}` | **T8** |
| 5 | Update to a nonexistent `imageId` → 422. | `PUT /api/host/games/{g}/questions/{q}` | **T8** |
| 6 | Scoring over sockets, one player each: inner tap → full points, `is_correct` true; outer tap → `points_value × partialFraction`, false; miss → 0. Uses a non-square image (e.g. 2:1) and a tap that is inside `outerRadius` **only** with aspect correction (would be a miss under per-axis distance), proving H3. | Socket.io (`submit_answer`, `host_advance`) | **T8** |
| 7 | COMPLETENESS hotspot: any valid tap → full points; reveal is `{type: "completeness"}`; player `yourBand` is `null`. | Socket.io | **T8** |
| 8 | Malformed taps (`x` missing, `x` = `true`, `y` = 1.5, `x` = "0.5") → socket `error`; no `session_scores` row; player can still submit a valid tap afterwards. | Socket.io | **T8** |
| 9 | Host `question_results` contains `taps` with correct bands and band counts in `answerDistribution`. Player `question_results` contains the hotspot reveal and `yourBand` matching that player's tap (one player per band, plus a `points_value = 0` question where an outer tap still gets `"outer"`), and **no** `taps`. | Socket.io | **T8** |
| 10 | `new_question` payload for hotspot contains `config` but no target fields (`x`, `innerRadius`, …). | Socket.io | **T8** |
| 11 | Export a game with a hotspot question → version 2, one `images` entry, `imageRef` in config, no `imageId`. Export of an image-free game → version 1, identical shape to today. | `GET /api/host/games/{g}/export` | **T8** |
| 12 | Round trip: import the exported v2 bundle into another course → new image created with identical bytes, question `imageId` remapped to it, scoring works. | `POST /api/host/games/import` (multipart `file`, `course_id`) | **T8** |
| 13a | v2 import errors → 422 and **no** game or image created (transaction): unknown `imageRef`; duplicate `ref`; invalid base64; hotspot question carrying `imageId`. Error messages name 1-based question / image numbers. | `POST /api/host/games/import` | **T8** |
| 13b | Hotspot question in a version 1 bundle → 422 "requires a version 2 bundle"; no game created. | `POST /api/host/games/import` | T4 ph. 2 |
| 14 | Every unmodified `sample_games/*.json` (v1) still imports. After stage E, Arjun's two v2 sample games import. | `POST /api/host/games/import`; T4 §6.4 test 1 covers `POST /api/admin/games/import` | — / stage E |
| 15 | HTML report for a completed session with a hotspot question contains a `data:image/` URI and an `<svg>` with ring circles; contains no player names. | `GET /api/game/sessions/{id}/report` (T4 D9) | **T8** |
| 16 | Deleting an image referenced by a hotspot question → 409 (contract C7; test may live in T8's suite). | T8's image delete route | **T8** |
| 17 | Engine scenario (`tests/integration/engine/scoring.py`) with hotspot questions: computed expected scores match server scores for a multi-player run. | Socket.io (engine) | **T8** |
| 18 | **Unit:** `hotspot_band` boundaries (exactly on inner / outer radius are inclusive; landscape, portrait and square aspect cases). `hotspot_target` returns `None` and does not raise for: `answer_data` `None`, a list, a missing key, a string radius, `innerRadius > outerRadius`, `aspectRatio` 0 or missing. `calculate_score` on such a question → `(0, False)`. | none (direct import) | — |
| 19 | `GET` a real image → 200 with `Cache-Control: private, max-age=31536000, immutable`; unknown ID → 404 without that header (C3). | `GET /api/images/{id}` | **T8** |

Existing tests are not modified or weakened.

## 11. Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| Polygon or rectangle target region | No natural distance for banded scoring; harder to author on a small preview (H1). |
| Linear falloff between the radii | Players can't predict their score; boundary tests become float-sensitive (H2). |
| Per-axis normalized distance (radii as ellipses) | A radius is a different pixel length horizontally and vertically on non-square images; unintuitive for authors (H3). |
| Pixel coordinates | Break whenever the displayed size differs from the authored size, i.e. always across phones. |
| Look up the image's dimensions from T8 at scoring time | A DB read per answer and a T8 dependency inside `calculate_score`; snapshotting `aspectRatio` is equivalent under C1 (H4). |
| Plain `<img>` with a click handler instead of a canvas | Fails T7's canvas requirement and makes drawing markers, rings and tap overlays harder. |
| `<img src="/api/images/{id}">` (unauthenticated or cookie auth) | The apps authenticate with a bearer header from `localStorage`; an `<img>` can't send it. Making images unauthenticated is T8's call, not hotspot's (C3). |
| Show taps on the host screen while the question is open | Lets slow players copy the crowd (H5). |
| One tap submits immediately | Fat-finger misses on small targets (H6). |
| New Redis list of tap points per question | The host summary already reads `session_scores` from MySQL; the results phase gets taps from one extra column there. Band counts fit the existing distribution hash. |
| Bundles carry only `imageId` | Instance-specific IDs; bundles would not import into a fresh clone (H8, same reasoning as T4 D10). |
| Image export as a separate T8 step outside the game bundle | Two files per game to keep together; T6 sample games would not import as one file. |
| Downscale embedded images in reports/exports | Needs Pillow, a new dependency; size cost accepted. |
| Waldo-style or other copyrighted sample content | Copyright; replaced by public-domain map and self-made pitch diagram (H10). |

## 12. Known risks and open edges

- **Two blockers.** Nothing is end-to-end until T8 merges; if T8's contract differs from §4,
  stage C and the sample games change. Resolve §4 with Vincent before stage A finishes.
- **Small targets on phones.** Even at 0.02, detailed images (anatomy, dense maps) may feel
  random without pinch-zoom. Authors are guided by the live ring preview only.
- **Report and bundle size.** Embedded base64 images grow the report and v2 bundles; large images
  can hit the 1 MB nginx default (C8).
- **Admin dangling `imageId` until T4 phase 3** (§9): bounded to "Image unavailable".
- **Admin invalid target data until T4 phase 3** (§9): bounded to "everyone misses, one warning
  per answer in the logs" (§5.4).
- **Image load counts against the timer** (H11). The immutable cache removes repeat fetches per
  browser, but the **first** play of a question on each phone is still one fetch per player at the
  same moment (≈ 150 × image size for a full room). Acceptable because of T8's size cap and the
  prefetch; if a classroom network proves too slow, the fallback is smaller images, not a client
  timer.
- **`aspectRatio` is trusted, not checked against the image.** The editor sets it from the loaded
  image, but a direct API call or a hand-edited bundle can store a different value. Scoring and
  drawing stay consistent with each other (both use `config.aspectRatio`); only the image appears
  stretched in the letterbox. Checking it server-side would need an image library (Pillow),
  rejected in §11.
- **HotspotEditor copies drift** between host and admin (same accepted risk as T4's editor port).
- **Accessibility.** Tapping a point on an image has no keyboard or screen-reader equivalent; the
  canvas has an `aria-label` only. Out of scope.
- **Report reflects current questions** (T4 D9): editing a hotspot target after play changes old
  reports' rings and bands.
- **Late joiners** get the existing shortened timer (min 5 s); with image loading time this can
  leave little time to tap. Existing behaviour, not changed.

## 13. Revision after goldfish test (2026-10-01)

A fresh-session goldfish test (spec + context hierarchy + cited T4 sections only) found these
gaps; each is now closed in the section named.

| # | Gap | Resolution |
|---|---|---|
| 1 | Player label from points was wrong for `points_value = 0` and for `partialFraction` 0 or 1. | Server-computed `yourBand` in the per-player results emit; label from it (H12, §7.4, §7.6, §7.7, test 9). |
| 2 | Converting the sample games to version 2 would break the T4 sample-import test, which uses the admin endpoint (v1 only until T4 phase 3). | Sample games stay v1 until both stage C and T4 phase 3 land; new stage E (§8, §9, §6.3). Every §10 test names its endpoint. |
| 3 | Invalid target data stored through the unvalidated admin update path could crash scoring, results and the report mid-game. | `hotspot_target` never raises; bad data scores as a miss and is logged (§5.2, §5.4, §7.2, §7.4, §7.5, test 18). |
| 4 | Image loading time eats into answer time; whole-class simultaneous fetch. | Accepted with justification (H11): server-side timer, T8 size cap, prefetch on `new_question` (§7.7), immutable cache headers required of T8 (C1, C3, test 19). |
| 5 | Host legend under COMPLETENESS undefined. | Band legend hidden, "N taps" shown (§7.8). |
| 6 | Editor inner-radius slider (max 0.5) narrower than server rule (max 1). | Server caps `innerRadius` at 0.5 (§5.1, test 1). |
| 7 | C7 did not say how to find references to an image. | JSON lookup on `config.imageId`, filtered by `type = 'hotspot'` (C7). |
| 8 | `aspectRatio` is client-supplied and unchecked. | Recorded as accepted risk (§12). |
| 9 | "Question N" numbering unspecified. | 1-based, matching today's import message (§6.3). |
| 10 | "First 500" taps had no order. | Ordered by `session_scores.id`; band counts over all rows (§7.2, §7.4). |
