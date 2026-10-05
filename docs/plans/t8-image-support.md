# T8 — Image support in questions

Status: **agreed design, pre-Goldfish** (all decisions in §12 settled 2026-10-04). Owners: **Vincent Zhou** (image storage, upload, management,
export/import) and **Arjun Kaneriya** (canvas and putting images into questions) — §3 draws the
line and the contract between the two halves.

Builds on T4 phase 3 (admin game/question routes delegate to `content_service`) and fulfils the
image contract Arjun's hotspot design needs: `docs/plans/t7-hotspot.md` §4, requirements C1–C8.
Read with the context hierarchy: `backend/app/README.md`, `backend/app/models/README.md`,
`backend/app/services/README.md`, `backend/app/routers/README.md`, `frontend/README.md`.

## 1. Problem

T8 asks for images inside questions, stored entirely in the database:

| Requirement (`instructions.md` T8) | What it means here |
|---|---|
| Upload | Upload through the admin **or** host app; bytes stored in MySQL, not on disk |
| Question prompt | An image shown with a question's text |
| Question options | Image answer choices (e.g. "which of these is a mitochondrion?") |
| Canvas integration | Hotspot questions (Arjun's T7 canvas type) draw on a T8 image |
| Management | Images can be viewed, **replaced** and deleted in the UI |

The rubric (R8) also grades "sensible handling of invalid input and repeated use", so error cases
and duplicate handling are part of the design, not polish.

**Hard constraints from the hotspot contract** (`t7-hotspot.md` §4):

- **C1** — the bytes stored under an image ID never change (hotspot targets are stored relative to
  the image, and `config.aspectRatio` is snapshotted when the question is authored).
- **C2** — images are rows with a positive integer ID.
- **C3** — `GET /api/images/{id}` returns the bytes to any logged-in token, **guests included**,
  with `Cache-Control: private, max-age=31536000, immutable` on 200s and not on 404s.
- **C4 / C5 / C6** — Python calls to check an image exists, to read its bytes and type, and to
  create one inside the caller's transaction (flush, no commit).
- **C7** — deleting an image any question uses is a 409.
- **C8** — raise nginx's default 1 MB request cap so a game file carrying images can be imported.

**Out of scope:** cropping or editing images, animated images, server-side thumbnails (§8), and
the second T7 question type (designed separately; it plugs into D5's lookup function).

## 2. Plan in one page

1. Migration 005 adds an `images` table, each image **belonging to a course**, and a nullable
   `questions.prompt_image_id` column (D1, D3, D5).
2. A new `services/image_service.py` validates uploads with Pillow, stores them, finds what
   references an image, and implements C4–C6 (D2, D5).
3. A new `routers/images.py` at `/api/images`: fetch, list, upload, replace, delete (D4).
4. Questions reference images three ways — prompt (`prompt_image_id`), options
   (`config.optionImageIds`), hotspot (`config.imageId`) — and **one function** lists the image IDs
   a question uses; validation, delete protection and export/import all call it (D5). A question
   may only use images of its game's course.
5. "Replace" never changes bytes under an ID: it uploads a new image and repoints the questions
   (D6).
6. Export/import gains Arjun's version 2 bundle (embedded base64 images), covering all three
   reference kinds (D7).
7. Admin and host get an image library page and an `ImagePicker` (Vincent); the question editors,
   player and host game screens and the HTML report show the images (Arjun) (§3, §6).

## 3. Who builds what

**Vincent — image upload and management:** everything that stores, validates, lists, replaces,
deletes, checks and transports images. **Arjun — canvas and image integration:** everything that
puts images into questions and onto screens.

| Area | Vincent | Arjun |
|---|---|---|
| Database | Migration 005: `images` table **and** `questions.prompt_image_id` (one migration, so the chain stays linear) | — |
| Backend services | `image_service` (D2, C4–C6, `question_image_ids`, `find_references`, list, replace, delete, course copy on game move); `content_service`: real existence check (replaces `_image_exists`), course match, v2 export/import, game-move image copy | `report_service`: hotspot image (`_hotspot_image_data_uri`) and prompt/option images as data URIs |
| Schemas | `schemas/image.py`; question fields and rules in `schemas/admin.py` (§5) | — |
| Routers / gateway | `routers/images.py`, mount in `main.py` | `websocket/gateway.py`: `promptImageId` in the question payload |
| Infrastructure | `requirements.txt` (Pillow), `nginx/nginx.dev.conf` (C8) | Remove the dev-image stand-ins: Vite `devImages` plugins, `docker-compose.yml` mount, `frontend/dev-images/` (his checklist in `frontend/dev-images/README.md`) |
| Admin + host UI | `lib/api.ts` image calls; `ImagePicker`; `ImagesPage` (library: upload, view, replace, delete, unused filter) + route + nav | `QuestionEditorPage`: prompt image and per-option images (using Vincent's `ImagePicker`); `HotspotEditor`: pass the picker into `renderImagePicker` |
| Player + host game UI | — | `QuestionImage` component; prompt image and image options on `QuestionPage` / host question screen; thumbnails in results and game over; `types/game.ts` |
| Tests (§7) | Tests 1–15, 19 | Tests 16–18, plus the hotspot tests marked **T8** in `t7-hotspot.md` §10 |
| T6 games | Own two games (may use images) | Stage E: hotspot questions in his two games, converted to v2 |

**The contract between the halves** (what Arjun can build against before Vincent's half merges):

- `GET /api/images/{id}` as in C3; `lib/images.ts` `loadImageUrl` is already written against it.
- `ImagePicker` props: `courseId: number`, `value: number | null`,
  `onChange(imageId: number | null)`. It lists only that course's images and can upload into it.
- Stored question shape (§5): `prompt_image_id` (column, API field), `config.optionImageIds`,
  `config.imageId` (hotspot, unchanged).
- Live payload: `promptImageId` (Arjun adds it in the gateway) and `config.optionImageIds` (already
  inside `config`).
- `image_service.get_image(db, image_id) -> (content_type, bytes) | None` (C5) for the report.

**Order:** Vincent's backend lands first (migration, service, router, existence check); Arjun's
display work can start in parallel against the contract, using an image uploaded through the new
route once it is on his branch. v2 export/import and the library UI follow; stage E (sample games)
comes last.

## 4. Decisions

Each decision states what was chosen, the options weighed, and why.

### D1. Storage: one `images` table in MySQL

T8 requires database storage, so the choices are the column type and what to record beside the
bytes.

| Column | Type | Why it is there |
|---|---|---|
| `id` | integer, auto-increment | C2: questions store it in JSON |
| `course_id` | FK → `courses.id`, NOT NULL, `ON DELETE RESTRICT`, indexed | Ownership (D3) |
| `content_type` | `image/png`, `image/jpeg` or `image/webp` | Sent back as `Content-Type` (C3) |
| `data` | MEDIUMBLOB (≤ 16 MB) | The bytes. BLOB caps at 64 KB, too small; LONGBLOB (4 GB) is far beyond the 2 MB limit |
| `byte_size` | integer | The library shows sizes without loading bytes |
| `width`, `height` | integer pixels | Aspect-ratio check on replace (D6); tiles reserve their space before the image loads |
| `sha256` | 64-char hex, unique with `course_id` | Finds a duplicate within the course (D2) |
| `uploaded_by` | user ID, nullable, `ON DELETE SET NULL` | Shown in the library ("uploaded by"); not used for permissions |
| `created_at` | timestamp | Library sort order |

**Why the database is a good fit here:** C6 comes for free — an image created during an import
is in the same MySQL transaction, so a failed import rolls the images back with everything else.
Files on disk could not do that. A fresh clone and the grading environment need nothing beyond
the existing MySQL volume.

**The cost:** MySQL is a poor file server; every image read goes through the backend and the
database. Mitigations: the immutable cache header (C3) means each browser fetches an image once,
and list queries select metadata columns only, never `data`.

### D2. Upload validation: check the real bytes; re-save only when needed; reuse duplicates

**Decided (2026-10-04).** The server decides what an upload is **from its bytes**, using Pillow
(new dependency in `backend/requirements.txt`). The file name and the browser's claimed type are
ignored.

**Allowed types: PNG, JPEG, WebP.** These cover screenshots, photos and diagrams, and every
browser draws them.

- *SVG is rejected.* It is a text format that can carry scripts; serving a user's SVG from our
  origin is a script-injection risk, and making it safe needs an SVG sanitizer.
- *GIF is rejected.* An animated GIF has many frames; hotspot coordinates and the re-save step
  assume one.

**Limits:**

| Limit | Value | Why |
|---|---|---|
| File size | 2 MB | Arjun's H11 assumes one image loads in well under a second on a classroom connection |
| Pixel size | ≤ 4096 px per side | Larger only adds load time on a phone or projector |
| Decompression bomb | Pillow's guard on (`MAX_IMAGE_PIXELS`) | A small file can claim 50,000 × 50,000 px and use gigabytes when decoded |
| nginx `client_max_body_size` | 25 MB | C8: a v2 game file carries images as base64 (× 1.37), so 25 MB fits about 8 full-size images |

Every failure is a 422 `VALIDATION_ERROR` with a message the editor shows as is, e.g. "File is not
a PNG, JPEG or WebP image" or "Image is 3.4 MB; the limit is 2 MB".

**Re-save only when the image carries metadata.** If the decoded image has EXIF or other
metadata, Pillow applies its rotation tag, drops the metadata and saves it again in the same
format; otherwise the bytes are stored exactly as uploaded.

| Option | Hotspot on phone photos | GPS / metadata | Quality over export → import round trips |
|---|---|---|---|
| Store bytes exactly as uploaded | **Breaks** (below) | Kept: a photo can reveal where it was taken | Unchanged |
| Re-save every upload | Correct | Removed | **JPEG loses quality on every round trip** (re-encoded each import) |
| **Re-save only when metadata is present (chosen)** | Correct | Removed | Unchanged: stored images have no metadata, so a re-import stores the same bytes |

*Why rotation matters:* a portrait phone photo is usually stored sideways with an EXIF tag saying
"rotate 90°". Browsers obey the tag, so `HotspotEditor` measures the image as tall; Pillow does
not, so the server would record it as wide, and `aspectRatio`, the replace check (D6) and what
players see would disagree. Applying the rotation makes the stored pixels match what everyone
sees. All of this happens **before** the row exists, so C1 still holds. The chosen option also
keeps Arjun's test 12 ("round trip creates an image with identical bytes") true.

**Duplicates: reuse the course's identical image.** If bytes already stored in the same course
are uploaded or imported again (same `sha256` of the stored bytes), the existing row is returned
(200 instead of 201) and nothing new is written. Without this, importing a sample game three times
into one course stores its images three times. The same bytes in **another** course are a separate
row, because each course owns its images (D3).

### D3. Ownership: images belong to a course

**Decided (2026-10-04).** Every image belongs to exactly one course, like a game. Admins and the
course's HOSTs manage it; a question may only use images from its game's course.

| Option | How it works | Pros | Cons |
|---|---|---|---|
| **Course-owned (chosen)** | `images.course_id`; admins and HOSTs of the course list, upload, replace and delete | Matches T4: games, rosters and images all belong to a course, enforced with the existing HOST role; co-instructors share one library | A host teaching two courses uploads an image twice; an admin moving a game between courses must bring its images along (below) |
| Uploader-owned | `uploaded_by`; host sees own images, admin all | Simplest rules; game moves need nothing | Co-hosts can't browse each other's uploads; doesn't follow T4's course model |
| One global library | Every host sees every image | One upload serves every course | Any host can replace or delete images other courses rely on; no isolation |

**Rules that follow:**

- **Permissions** reuse T4's course check (`game_service.assert_host_can_use_course`): admin, or
  `HOST` in `user_course_access` for the image's course. Anyone else gets 403.
- **Course match:** saving or importing a question whose image belongs to another course is a 422
  ("Image 12 belongs to a different course"). Without this, a host could put course B's images
  into course A's games, and course B could no longer delete them.
- **Unassigned legacy games** (`course_id` NULL, admin-only since T4) can't use images: 422
  "Assign the game to a course before adding images".
- **Game move** (admin `PUT /api/admin/games/{id}` with a new `course_id`, T4 phase 1): the move
  **copies** every image the game uses into the new course (reusing an identical image already
  there, D2) and repoints the game's questions, all in the move's transaction. The originals stay
  in the old course. The move is already refused while the game is live (T4 D7), so no player is
  mid-question. **Decided (§12 Q5).** Rejected alternative: refuse the move while the game uses
  images — simpler, but it takes away an admin feature T4 just shipped.
- **Reading bytes** stays open to every logged-in token (C3); course ownership controls only
  management and which questions may use an image.

### D4. API: one shared `/api/images` router over `image_service`

| Route | Who | Result |
|---|---|---|
| `GET /api/images/{id}` | any logged-in token, guests included | Raw bytes. 200 sends the C3 cache header and `X-Content-Type-Options: nosniff`; 404 sends neither |
| `GET /api/images?course_id=N&page=P&unused=bool` | admin, or HOST of course N | Metadata only, 24 per page, newest first, each with `reference_count` and `uploaded_by`; 404 unknown course |
| `POST /api/images` | admin, or HOST of the course | Multipart `file` + `course_id` form field (as game import does) → 201 `{id, course_id, content_type, width, height, byte_size, created_at}`; 200 with the existing row for a duplicate (D2) |
| `POST /api/images/{id}/replace` | admin, or HOST of the image's course | Multipart `file` → see D6 |
| `DELETE /api/images/{id}` | admin, or HOST of the image's course | 204; 409 "Image is used by N questions" (C7); 403 otherwise; 404 unknown |

**Why one router rather than copies under `/api/admin` and `/api/host`:** T4 split games and
questions by audience because hosts and admins see different games. Images have one rule for
everyone (admin or HOST of the course), and the fetch route must also serve players and guests.
Two copies would duplicate the same checks.

**Why 403, not 404, for another course's image:** the image isn't secret (any token can GET it),
so hiding its existence protects nothing, and a 403 tells the UI why the delete failed.

**`nosniff`** stops the browser guessing another type from the bytes; with D2's type check, an
upload can never be served and run as HTML or script.

`image_service` provides the contract calls: `image_exists(db, image_id) -> bool` (C4),
`get_image(db, image_id) -> (content_type, bytes) | None` (C5), and
`create_image(db, course_id, data, uploaded_by) -> Image` (C6: validates per D2, raises the 422
error type, flushes, never commits).

### D5. How questions reference images

Three reference kinds, each stored where it fits best:

| Reference | Stored in | Types | Why there |
|---|---|---|---|
| Prompt image | new column `questions.prompt_image_id`, nullable FK → `images.id`, `ON DELETE RESTRICT` | every type | It is type-independent. A column means no per-type `config` rule changes (hotspot's checker requires `config` to be *exactly* `{imageId, aspectRatio}`), and the database itself refuses to delete a referenced prompt image |
| Option images | `config.optionImageIds`: list, same length as `config.options`, each entry an image ID or `null` | `multiple_choice`, `multi_select` | Options stay plain strings, so every existing consumer (player, host, report, CSV export, sample games) keeps working; the new list is optional |
| Hotspot image | `config.imageId` (Arjun's, unchanged) | `hotspot` | Already specified in `t7-hotspot.md` §5.1 |

`true_false` and `fill_in_the_blank` get only prompt images: their answers are fixed words or
typed text.

**Alternative rejected — options as objects** (`options: [{text, imageId}]`): cleaner shape, but
it changes the meaning of `config.options` for every existing consumer and every sample game.

**Option text rules:** with `optionImageIds`, an option's text may be empty only when that option
has an image (an image-only choice). The prompt text is still required (`min_length=1`), because
players need to know what is being asked.

**One function lists a question's images:** `image_service.question_image_ids(type, config,
prompt_image_id) -> set[int]`. Every image-aware path calls it:

- the existence and course-match check on question create, update and import (C4) — replacing
  Arjun's `content_service._image_exists` dev stand-in;
- the reference count and the delete 409 (C7);
- the ID → ref rewrite on export and ref → ID on import (D7);
- the image copy on game move (D3).

The second T7 type registers its image fields there and nowhere else.

**Finding references in SQL.** The delete check needs the reverse direction ("which questions use
image 7?"), which must be a query. `image_service.find_references(db, image_id)` matches:
`prompt_image_id = :id`, **or** `type = 'hotspot'` and `JSON_EXTRACT(config, '$.imageId') = :id`,
**or** `type IN ('multiple_choice', 'multi_select')` and `optionImageIds` contains `:id`. The type
filters matter: other types' `config` may hold integers that are not image IDs. The function and
the query sit side by side, and a test checks they agree.

**Alternative considered — a `question_images` link table** kept in sync by `content_service` on
every write. The database would then enforce C7 completely through foreign keys. Rejected for now
because it is a second copy of what `config` already says, and the two can drift; every question
write already goes through `content_service` (admin, host, import), so the query approach has one
source of truth. Revisit if a fourth reference kind appears.

**Validation stays symmetric.** T4's D8 re-validates the whole merged question on every update, so
the new rules apply to create and update alike (the T7 warning in `instructions.md`).

### D6. Replace without breaking C1

**Decided (2026-10-04): option A.** C1 forbids changing the bytes under an existing ID, so
"replace" is built around it. T8's Management row names replace explicitly ("viewed, replaced,
and deleted through the interface"), which is why it lives in the library.

| Option | How it works | Pros | Cons |
|---|---|---|---|
| **A. Upload-and-repoint (chosen)** | `POST /api/images/{id}/replace` stores the new file as a **new** row in the same course, repoints every question the caller may edit from the old ID to the new one, then deletes the old row if nothing still uses it | A visible "Replace" in the library, clearly meeting T8; fixes every question at once | The most logic in T8: permission filter, live-game check, hotspot check, partial repoint |
| B. Swap in the editor | No replace route. The author picks a different image in each question, then deletes the old one | Almost no new logic | Tedious when an image is in several questions; a grader may not count it as "replace" |
| C. Refuse while used | Replace only allowed for unused images | Simple and safe | Replacing an unused image is just delete + upload, so it adds nothing |

**Option A in detail:**

1. Validate the new file (D2) and store it as a new row in the old image's course.
2. Find the old image's references (D5). They are all in that course's games (D3). Keep only
   questions in games the caller may edit (admin: all; host: the T4 rule — game grant **and** HOST
   of the course).
3. **409, nothing changed,** if any of those games has a live session (T4 D7), or if any is a
   hotspot question and the new image's aspect ratio differs from the old one by more than 1%.
   Hotspot targets are stored as fractions of the image, so they stay in the right place only if
   the shape matches; the question's `config.aspectRatio` is updated to the new value.
4. Repoint: `prompt_image_id`, `optionImageIds` entries and `config.imageId`, writing new `config`
   dicts (never mutating the loaded JSON in place).
5. Delete the old row if no references remain; otherwise keep it (a game the caller can't edit
   still uses it).
6. Respond `{new_id, repointed_questions, old_deleted}`.

**Known consequence:** completed sessions' HTML reports render a question's *current* image, so a
replaced image also changes old reports. Accepted: reports read questions live today anyway.

### D7. Export/import: version 2 bundle

**Decided (2026-10-04): built by Vincent as part of T8**, together with the real existence check,
instead of in Arjun's stage C. Both have to cover prompt and option images as well as hotspot;
one owner avoids two people editing `content_service.import_game` / `export_game` at once.

T8 implements the bundle format Arjun specified in `t7-hotspot.md` §6 — a top-level `images` array
of `{ref, content_type, data_base64}`, and refs instead of IDs — extended to T8's own fields:

| Reference | In the stored question | In a v2 bundle |
|---|---|---|
| Hotspot | `config.imageId` | `config.imageRef` (Arjun's) |
| Prompt | `prompt_image_id` column | question-level `prompt_image_ref` (snake_case, like `time_limit_seconds`) |
| Options | `config.optionImageIds` | `config.optionImageRefs` (same length, `null` entries kept) |

- **Export:** a game using no images exports as **version 1, byte for byte as today**. Otherwise
  version 2, refs `img1`, `img2`, … in first-use order, bytes from C5.
- **Import:** version 1 unchanged; version 2 follows `t7-hotspot.md` §6.3 — check every image entry
  and every ref, validate every question with placeholder IDs, **then** create the referenced
  images **in the target course** (C6; D2 duplicate reuse applies) and the questions, all in one
  transaction. Any error → 422 naming the 1-based question or image, and nothing is created.
- Unmodified version-1 files in `sample_games/` keep importing (T6 requirement).

**All image support is specified here (§12 Q6).** This doc supersedes the image parts of
`t7-hotspot.md` §9 stage C: the existence check and v2 are Vincent's; the report image, removing
the dev-image stand-ins and the hotspot tests that need real images are Arjun's, under T8 (§3).
`t7-hotspot.md` §9 stage C should be updated to point here.

## 5. Data shapes and validation

**Question fields** (`schemas/admin.py`, `QuestionCreate`; `QuestionUpdate` via the D8 merge):

- `prompt_image_id`: optional positive integer or `null`. Accepted for every type.
- `config.optionImageIds` (`multiple_choice`, `multi_select` only): optional; if present, a list
  of the same length as `config.options`, each entry a positive integer or `null`; booleans
  rejected (as in the hotspot checker). Any other type carrying it → 422.
- With `optionImageIds`, `options[i]` may be `""` only when `optionImageIds[i]` is an integer.
  Without it, today's option rules are unchanged.
- After schema validation, `content_service` checks every ID from `question_image_ids` exists
  (C4) and belongs to the game's course (D3): unknown or other-course ID → 422 naming the field
  (`prompt_image_id`, `config.optionImageIds[2]`, `config.imageId`).

**Live game payload** (`websocket/gateway.py`, `_question_payload`): adds `promptImageId`
(`null` when absent). `config` already carries `optionImageIds` and hotspot's `imageId`. No
scoring change: images never affect points, so `calculate_score`, the simulator and the scoring
engine are untouched.

**API response** (`QuestionResponse`): adds `prompt_image_id`.

## 6. Implementation outline (files touched)

Preliminary — the spec will order these into atomic, test-first steps.

**Vincent**

| File | Change |
|---|---|
| `backend/app/migrations/versions/005_images.py` | `images` table; `questions.prompt_image_id` + FK + index |
| `backend/app/models/image.py`, `models/__init__.py`, `models/game.py` | `Image` model; `Question.prompt_image_id` |
| `backend/app/services/image_service.py` | D2 validation, create/get/exists (C4–C6), `question_image_ids`, `find_references`, list, delete, replace, copy-to-course |
| `backend/app/services/content_service.py` | Real existence + course check (replaces `_image_exists`); v2 export/import (D7); image copy on game move (D3) |
| `backend/app/schemas/image.py`, `schemas/admin.py` | Image responses; question fields and rules (§5) |
| `backend/app/routers/images.py`, `backend/app/main.py` | Router (D4), mounted at `/api` |
| `backend/requirements.txt` | Pillow |
| `nginx/nginx.dev.conf` | `client_max_body_size 25m` (C8) |
| `admin/` and `host/` `src/lib/api.ts` | `listImages`, `uploadImage`, `replaceImage`, `deleteImage` |
| `admin/` and `host/` `src/components/ImagePicker.tsx` | Modal: paged grid of the course's images, upload button, returns the chosen ID (contract in §3) |
| `admin/` and `host/` `src/pages/ImagesPage.tsx` + route + nav | Library per course: grid with size, dimensions, uploader, "used by N", Replace, Delete (disabled while used), "unused" filter |

**Arjun**

| File | Change |
|---|---|
| `backend/app/websocket/gateway.py` | `promptImageId` in the question payload |
| `backend/app/services/report_service.py` | Hotspot, prompt and option images as data URIs (C5) |
| `admin/` and `host/` `src/pages/QuestionEditorPage.tsx` | Prompt image (choose / remove / preview) and per-option images for multiple choice and multi-select, via `ImagePicker` |
| `admin/` and `host/` `src/components/HotspotEditor.tsx` (caller) | Pass `ImagePicker` into `renderImagePicker` |
| `player/src/components/QuestionImage.tsx` (+ host copy) | Loads through the existing `lib/images.ts`; placeholder, then the image or "Image unavailable" |
| `player/src/pages/game/QuestionPage.tsx`, `ResultsPage.tsx`, `GameOverPage.tsx` | Prompt image above the text; image options as large tap tiles; thumbnails in results |
| Host game screens | Prompt image on the big screen; image options; thumbnails on result bars |
| `player/` and `host/` `src/types/game.ts` | `promptImageId`, `optionImageIds` |
| Vite `devImages` plugins, `docker-compose.yml` mount, `frontend/dev-images/` | Removed (stage C) |

The player starts loading the prompt and option images as soon as `new_question` arrives, as H11
does for hotspot, so loading overlaps reading the prompt.

Each owner updates the READMEs of the directories they touch in the same branch
(`.claude/rules/context-sync.md`).

## 7. Integration tests (T5)

New files under `tests/integration/`, run against the live stack.

**Vincent**

| # | Behaviour | Expected |
|---|---|---|
| 1 | Upload PNG, JPEG, WebP into a course | 201; metadata matches; GET returns identical bytes and the right type |
| 2 | Upload rejections: text file named `.png`, SVG, GIF, 2 MB + 1 byte, 5000 px wide, truncated/corrupt PNG, empty file | 422 each, with the expected message; no row created |
| 3 | JPEG with EXIF rotation and GPS | Stored width/height match the rotation; no EXIF in the stored bytes |
| 4 | Identical bytes uploaded twice to one course; then to a second course | Second call 200 with the same `id`; the other course gets its own row |
| 5 | GET by a guest token; GET unknown ID; GET without a token | 200 with the C3 header and `nosniff`; 404 without the cache header; 401 |
| 6 | Upload, list, replace, delete by a PLAYER, a guest, and a HOST of a different course | 403 each |
| 7 | List per course: `reference_count`, `unused` filter, paging; unknown course | Correct values; 404 |
| 8 | Delete while used — once per reference kind (prompt, option, hotspot) | 409 naming the count; image still readable |
| 9 | Question create/update with prompt and option images; unknown ID; other course's image; unassigned game; list length mismatch; `""` option without image; `optionImageIds` on a `true_false` question | Success, or 422 naming the field |
| 10 | Replace: repoints the caller's questions; old row deleted when unused; kept when a game the caller can't edit still uses it | `{new_id, repointed_questions, old_deleted}` as expected |
| 11 | Replace refused: live game; hotspot aspect-ratio mismatch | 409; nothing changed |
| 12 | Admin moves a game with images to another course | Images copied into the new course, questions repointed, originals untouched |
| 13 | v2 export → import into another course, all three reference kinds | New image rows in the target course with identical bytes; IDs remapped; no new rows on a second import into the same course |
| 14 | Broken v2 bundles: unknown ref, duplicate ref, bad base64, invalid image bytes | 422; no game, question or image created |
| 15 | Every `sample_games/*.json` (v1) still imports; image-free game still exports as v1 | — |
| 19 | `question_image_ids` and `find_references` agree for every question type | — |

**Arjun**

| # | Behaviour | Expected |
|---|---|---|
| 16 | `new_question` socket payload carries `promptImageId` and `optionImageIds` | — |
| 17 | HTML report of a session with prompt and option images embeds them as data URIs | — |
| 18 | Hotspot tests marked **T8** in `t7-hotspot.md` §10 (real images replace the dev image) | As specified there |

## 8. Risks and self-critique

1. **Any logged-in token can read any image.** A guest could step through `/api/images/1, 2, 3…`
   and preview the image of a question not yet shown. C3 requires guest access; the alternatives
   (random IDs, breaking C2; checking the image belongs to the caller's current room, fragile on
   reconnects and costly per request) don't pay for themselves. Accepted, because prompt images
   are not answers — but an author can still make the image itself the giveaway.
2. **Delete vs. save race.** Without care, a host could save a question using image 7 while
   another host deletes image 7: the save's existence check and the delete's reference check both
   pass, and the JSON reference dangles. Prevention: both paths lock the image row
   (`SELECT … FOR UPDATE` on delete and replace, `FOR SHARE` in the existence check), so one waits
   for the other. Prompt images are also protected by the FK.
3. **References live in two places** (a column and JSON). The delete check is a union of a column
   match and two JSON searches; test 19 guards against drift. See the link-table alternative in D5.
4. **Course ownership duplicates images.** The same picture used in two courses is stored twice,
   and every admin game move copies its images. Acceptable at classroom scale (2 MB cap); the
   per-course duplicate check keeps repeated imports from multiplying.
5. **Unused images pile up.** Deleting a question or game never deletes its images, and a game
   move leaves the originals behind. The library's "unused" filter makes cleanup manual; deleting
   automatically would surprise someone who uploaded an image for later.
6. **Replace (D6) is the most complex piece.** Its refusal cases need tests (10, 11) so "holds up
   under realistic use" (R8) is shown, not assumed.
7. **No thumbnails.** A library page of 24 images at up to 2 MB each can be up to 48 MB; lazy
   loading and the browser cache reduce it. Stored thumbnails would be another column and a second
   C3-style route.
8. **Uploads are not rate-limited.** A host account could fill the database with 2 MB images.
   Accepted for a classroom deployment; `common/rate_limit` could add a per-user limit.
9. **Split ownership across two branches.** Arjun's display work depends on Vincent's migration
   and `ImagePicker`. The §3 contract lets him start early, but a contract change after he starts
   costs both of us; any change goes into this doc first.

## 9. Alternatives rejected (summary)

| Alternative | Why rejected | Where |
|---|---|---|
| Files on disk or object storage | T8 requires the database; loses C6's transactional rollback | D1 |
| Accept SVG / GIF | Script-injection risk; multi-frame breaks hotspot | D2 |
| Store bytes as uploaded | Sideways phone photos break hotspot; GPS leaks | D2 |
| Re-save every upload | JPEG degrades on each export → import | D2 |
| Uploader-owned or global library | Doesn't follow T4's course model / no isolation | D3 |
| Separate admin and host image routers | Same rules twice; fetch must serve players too | D4 |
| Options as `{text, imageId}` objects | Breaks every existing consumer of `options` | D5 |
| `question_images` link table | Second copy of the truth in `config` | D5 |
| Overwrite bytes on replace | Violates C1; breaks hotspot targets and cached copies | D6 |
| Replace by swapping images in the editor | Weak match for T8's "replaced through the interface" | D6 |

## 10. Dependencies and order

- **Needs:** T4 phase 3 (merged into this branch; must merge to `main` before T8's MR).
- **Unblocks:** hotspot stages C and E (`t7-hotspot.md` §9); both members' T6 games that use
  images.
- **T9:** the library page, picker and image tiles must use T9's theme tokens once they exist.

## 11. Process

1. Settle §12 → mark this doc "agreed" (done 2026-10-04).
2. Turn it into the precise spec (`write-spec`): ordered, test-first steps per owner.
3. Goldfish test in a fresh session; revise; record what changed in a "Goldfish revisions" section.
4. Commit the doc, then implement against it; update the doc first if implementation diverges.

## 12. Decisions

**Decided (2026-10-04):**

| # | Question | Decision |
|---|---|---|
| Q1 | Who owns images? | The course (D3) |
| Q2 | Who builds v2 export/import and the real existence check? | Vincent, in T8 (D7) |
| Q3 | How does "replace" work? | Upload-and-repoint (D6 option A) |
| Q4 | Re-save uploads that carry metadata? | Yes (D2) |
| — | Who builds what? | Vincent: image upload and management; Arjun: canvas and image integration (§3) |
| Q5 | What happens to a game's images when an admin moves it to another course? | Copy them into the new course and repoint (D3) |
| Q6 | Where is image work specified? | All image support is handled by T8 (this doc), including the image parts of hotspot stage C (D7, §3) |
