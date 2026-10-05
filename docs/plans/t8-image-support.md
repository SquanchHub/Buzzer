# T8 — Image support in questions

Status: **agreed design; goldfish-tested 2026-10-04 and revised** (§13 lists what the Goldfish
found and what changed). Owners: **Vincent Zhou** (image storage, upload, management,
export/import) and **Arjun Kaneriya** (canvas and putting images into questions) — §3 draws the
line and the contract between the two halves. **All image support is specified here**, including
the image parts of `t7-hotspot.md` §9 stage C (§12 Q6).

Builds on T4 phase 3 (admin game/question routes delegate to `content_service`) and fulfils the
image contract Arjun's hotspot design needs: `docs/plans/t7-hotspot.md` §4, requirements C1–C8.
Read with the context hierarchy: `backend/app/README.md`, `backend/app/models/README.md`,
`backend/app/services/README.md`, `backend/app/routers/README.md`, `frontend/README.md`.

## 1. Problem

T8 asks for images inside questions, stored entirely in the database:

| Requirement (`instructions.md` T8) | What it means here |
|---|---|
| Upload | Upload through the admin **or** host app; bytes stored in MySQL, not on disk |
| Question prompt | An image shown with a question's prompt |
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

**Out of scope:** cropping or editing images, animated images, server-side thumbnails (§8),
deleting courses (no endpoint exists; `images.course_id` is RESTRICT like `games.course_id`), and
the second T7 question type (designed separately; it plugs into D5's lookup function).

## 2. Plan in one page

1. Migration 005 adds an `images` table, each image **belonging to a course**, and a nullable
   `questions.prompt_image_id` column (D1, D3, D5).
2. A new `services/image_service.py` validates uploads with Pillow, stores them, finds what
   references an image, and implements C4–C6 (D2, D5).
3. A new `routers/images.py` at `/api/images`: fetch, list, upload, replace, delete (D4).
4. Questions reference images three ways — prompt (`prompt_image_id`), options
   (`config.optionImageIds`), hotspot (`config.imageId`) — and **one function** lists the image IDs
   a question uses; validation, reference counts, export/import and game moves all call it (D5).
   A question may only use images of its game's course.
5. "Replace" never changes bytes under an ID: it stores the new file and repoints the questions
   (D6).
6. Export/import gains Arjun's version 2 bundle (embedded base64 images), covering all three
   reference kinds; raw image IDs never travel in a bundle (D7).
7. Prompt images show on the host's big screen; option images show on both the phone and the big
   screen (D8). Admin and host get a per-course image library and an `ImagePicker` (Vincent); the
   question editors, game screens and HTML report show the images (Arjun) (§3, §6).

## 3. Who builds what

**Vincent — image upload and management:** everything that stores, validates, lists, replaces,
deletes, checks and transports images. **Arjun — canvas and image integration:** everything that
puts images into questions and onto screens.

| Area | Vincent | Arjun |
|---|---|---|
| Database | Migration 005: `images` table **and** `questions.prompt_image_id` (one migration, so the chain stays linear) | — |
| Backend services | `image_service` (D2, C4–C6, `question_image_ids`, `find_references`, list, replace, delete, copy-to-course); `content_service`: real existence + course check (replaces `_image_exists` and its use in `_check_hotspot_image`), v2 export/import, game-move image copy | `report_service`: hotspot image (`_hotspot_image_data_uri`), prompt and option images as data URIs, image-only option labels (D8) |
| Schemas | `schemas/image.py`; question fields and rules in `schemas/admin.py` (§5) | — |
| Routers / gateway | `routers/images.py`, mount in `main.py` | `websocket/gateway.py`: `promptImageId` in the question payload |
| Infrastructure | `requirements.txt` (Pillow), `nginx/nginx.dev.conf` (C8), the backend half of the dev-image stand-in: the `docker-compose.yml` `/dev-images` mount and the `_image_exists` unit test (removed in the same commit that replaces `_image_exists`) | The frontend half: Vite `devImages` plugins and `frontend/dev-images/` — removed **after** Vincent's existence check is on his branch (see Order) |
| Admin + host UI | `lib/api.ts` image calls; `ImagePicker`; `ImagesPage` (per-course library: upload, view, replace, delete, unused filter) + route + button (D4 UI) | `QuestionEditorPage`: prompt image and per-option images via `ImagePicker`; passing the picker into `HotspotEditor`'s `renderImagePicker` (adapter in §3 contract); admin editor's `Game` type gains `course_id` |
| Player + host game UI | — | `QuestionImage` component; prompt image on the host question screen; image options on phone and host; thumbnails in results and game over; `types/game.ts` (D8) |
| Tests (§7) | Tests 1–15, 19–22 | Tests 16–18, plus the hotspot tests marked **T8** in `t7-hotspot.md` §10 |
| T6 games | Own two games (may use images) | Stage E: hotspot questions in his two games, converted to v2 |
| Docs | Updates `t7-hotspot.md` §4 (real function names, link here) and §9 stage C (pointer here) in the first T8 implementation commit; Arjun reviews in the MR | — |

**The contract between the halves** (what Arjun can build against before Vincent's half merges):

- `GET /api/images/{id}` as in C3; `lib/images.ts` `loadImageUrl` is already written against it.
- `ImagePicker` props: `courseId: number`, `value: number | null`,
  `onChange(imageId: number | null)`. It lists only that course's images, can upload into it, and
  returns only the ID (hotspot measures `aspectRatio` from the loaded image itself, G4 in
  `t7-hotspot.md` §13.2).
- **Hotspot adapter** (the existing slot uses `undefined`, not `null`):
  `renderImagePicker={(id, setId) => <ImagePicker courseId={courseId} value={id ?? null}
  onChange={v => setId(v ?? undefined)} />}`.
- **Where `courseId` comes from:** both question editors load the game (`GET` game →
  `course_id`). The host editor's `Game` type already has it; the admin editor's `Game` type adds
  it. If `course_id` is `null` (an unassigned legacy game, admin only), every image picker is
  disabled with the note "Assign this game to a course to add images", matching the server's 422
  (D3).
- Stored question shape (§5): `prompt_image_id` (column, API field), `config.optionImageIds`,
  `config.imageId` (hotspot, unchanged).
- Live payload: `promptImageId` (Arjun adds it in the gateway) and `config.optionImageIds`
  (already inside `config`).
- `image_service.get_image(db, image_id) -> (content_type, bytes) | None` (C5) for the report.

**Order:**

1. Vincent: migration, `image_service`, router, existence/course check (removing the backend
   dev-image stand-in in the same commit). Arjun's display work proceeds in parallel against the
   contract.
2. Arjun removes the Vite `devImages` plugins and `frontend/dev-images/` only once step 1 is
   merged into his branch; from then on, hotspot authoring in dev uses uploaded images. Doing it
   earlier breaks hotspot authoring in dev; doing step 1 without the mount removal leaves a dead
   mount.
3. Vincent: v2 export/import, library UI, `ImagePicker`. Arjun: editor pickers.
4. Stage E (sample games) last.

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
| `sha256` | 64-char hex; **unique** together with `course_id` | Finds a duplicate within the course (D2) |
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

The server decides what an upload is **from its bytes**, using Pillow (new dependency in
`backend/requirements.txt`). The file name and the browser's claimed type are ignored.

**Allowed types: PNG, JPEG, WebP.** These cover screenshots, photos and diagrams, and every
browser draws them.

- *SVG is rejected.* It is a text format that can carry scripts; serving a user's SVG from our
  origin is a script-injection risk, and making it safe needs an SVG sanitizer.
- *GIF is rejected.* An animated GIF has many frames; hotspot coordinates and the re-save step
  assume one.

**Limits:**

| Limit | Value | Why |
|---|---|---|
| File size | 2 MB (2,097,152 bytes) | Arjun's H11 assumes one image loads in well under a second on a classroom connection |
| Pixel size | ≤ 4096 px per side | Larger only adds load time on a phone or projector |
| Decompression bomb | Pillow's guard on (`MAX_IMAGE_PIXELS`) | A small file can claim 50,000 × 50,000 px and use gigabytes when decoded |
| nginx `client_max_body_size` | 25 MB | C8: a v2 game file carries images as base64 (× 1.37), so 25 MB fits about 8 full-size images |

The upload route reads **at most 2 MB + 1 byte** from the request file and rejects it if that
last byte arrives, so an oversized upload is never held in memory whole.

Every failure is a 422 `VALIDATION_ERROR` on `body.file` with a message the editor shows as is,
e.g. "File is not a PNG, JPEG or WebP image", "Image is 3.4 MB; the limit is 2 MB", "Image is
5000 × 3000 px; the limit is 4096 px per side", "File is empty".

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
are uploaded or imported again (same `sha256` of the **stored** bytes, i.e. after any re-save),
the existing row is returned (200 instead of 201) and nothing new is written. Without this,
importing a sample game three times into one course stores its images three times. The same bytes
in **another** course are a separate row, because each course owns its images (D3).

**Two uploads of the same bytes at the same moment** both miss the lookup and the second insert
hits the unique `(course_id, sha256)` key. `create_image` inserts inside a savepoint
(`db.begin_nested()`); on that `IntegrityError` it rolls back the savepoint, re-selects the
existing row and returns it as a duplicate. The caller's transaction is unaffected and no 500 is
possible.

### D3. Ownership: images belong to a course

Every image belongs to exactly one course, like a game. Admins and the course's HOSTs manage it;
a question may only use images from its game's course.

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
  "Assign the game to a course before adding images". The editors disable their pickers to match
  (§3 contract).
- **Game move** (admin `PUT /api/admin/games/{id}` with a new `course_id`, T4 phase 1): the move
  copies every image the game uses into the new course and repoints the game's questions, all in
  the move's transaction. The copy reuses the **stored bytes and metadata as they are** (no Pillow
  pass; they were validated on upload) and reuses an identical image already in the new course
  (D2's duplicate rule). The originals stay in the old course. The move is already refused while
  the game is live (T4 D7), so no player is mid-question. A move to the **same** course changes
  nothing. Rejected alternative: refuse the move while the game uses images — simpler, but it
  takes away an admin feature T4 just shipped.
- **Reading bytes** stays open to every logged-in token (C3); course ownership controls only
  management and which questions may use an image.

### D4. API: one shared `/api/images` router over `image_service`

| Route | Who | Result |
|---|---|---|
| `GET /api/images/{id}` | any logged-in token, guests included | Raw bytes. 200 sends the C3 cache header and `X-Content-Type-Options: nosniff`; 404 sends neither |
| `GET /api/images?course_id=N&page=P&unused=bool` | admin, or HOST of course N | `ImagePage` (below), 24 per page, newest first; 404 unknown course; `page` starts at 1 |
| `POST /api/images` | admin, or HOST of the course | Multipart `file` + `course_id` form field (as game import does) → 201 `ImageItem`; 200 with the existing row for a duplicate (D2); 404 unknown course |
| `POST /api/images/{id}/replace` | admin, or HOST of the image's course | Multipart `file` → 200 `ReplaceResult` (D6) |
| `DELETE /api/images/{id}` | admin, or HOST of the image's course | 204; 409 "Image is used by N questions" (C7); 403; 404 unknown |

**Response schemas** (`schemas/image.py`):

- `ImageItem`: `id, course_id, content_type, width, height, byte_size, created_at,
  uploaded_by_name` (the uploader's display name — username, netid or email, the same fallback
  the admin users list uses — or `null` if the user was deleted), `reference_count`.
- `ImagePage`: `items: list[ImageItem], total, page, page_size`.
- `ReplaceResult`: `id` (the image the questions now use), `replaced_id`, `repointed_questions`,
  `old_deleted`.

**Reference counts for a list page** come from one query loading `(type, config,
prompt_image_id)` for the questions of the course's games, run through `question_image_ids` in
Python — not one SQL query per image. Valid because a question may only reference its own course's
images (D3).

**UI placement:** the library is a page at `/courses/:courseId/images` in both the admin and the
host app, opened by an **Images** button next to the existing **Roster** button on the admin
`CourseDetailPage` and the host `CoursePage`. No new sidebar entry: the course is chosen by being
on its page, the same pattern as the roster.

**Why one router rather than copies under `/api/admin` and `/api/host`:** T4 split games and
questions by audience because hosts and admins see different games. Images have one rule for
everyone (admin or HOST of the course), and the fetch route must also serve players and guests.
Two copies would duplicate the same checks.

**Why 403, not 404, for another course's image:** the image isn't secret (any token can GET it),
so hiding its existence protects nothing, and a 403 tells the UI why the action failed.

**`nosniff`** stops the browser guessing another type from the bytes; with D2's type check, an
upload can never be served and run as HTML or script.

**Contract calls.** `image_service` provides `image_exists(db, image_id) -> bool` (C4),
`get_image(db, image_id) -> (content_type, bytes) | None` (C5), and
`create_image(db, course_id, data, uploaded_by) -> (Image, created: bool)` (C6: validates per D2,
raises the 422 error type, flushes, never commits). The C6 signature deliberately differs from the
`t7-hotspot.md` §4 example: it takes no `content_type` (the bytes decide, D2) and needs the course
(D3); §4 explicitly allows different names.

### D5. How questions reference images

Three reference kinds, each stored where it fits best:

| Reference | Stored in | Types | Why there |
|---|---|---|---|
| Prompt image | new column `questions.prompt_image_id`, nullable FK → `images.id`, `ON DELETE RESTRICT` | every type | It is type-independent. A column means no per-type `config` rule changes (hotspot's checker requires `config` to be *exactly* `{imageId, aspectRatio}`), and the database itself refuses to delete a referenced prompt image |
| Option images | `config.optionImageIds`: list, same length as `config.options`, each entry an image ID or `null` | `multiple_choice`, `multi_select` | Options stay plain strings, so every existing consumer (player, host, report, sample games) keeps working; the new list is optional |
| Hotspot image | `config.imageId` (Arjun's, unchanged) | `hotspot` | Already specified in `t7-hotspot.md` §5.1 |

`true_false` and `fill_in_the_blank` get only prompt images: their answers are fixed words or
typed text.

**Alternative rejected — options as objects** (`options: [{text, imageId}]`): cleaner shape, but
it changes the meaning of `config.options` for every existing consumer and every sample game.

**Option text rules:** with `optionImageIds`, an option's text may be empty — `""` or
whitespace only, i.e. empty after `strip()` — only when that option has an image (an image-only
choice). The prompt text is still required (`min_length=1`).

**One function lists a question's images:** `image_service.question_image_ids(type, config,
prompt_image_id) -> set[int]`. It never raises: malformed `config` contributes nothing. Every
image-aware path calls it:

- the existence and course-match check on question create, update and import (C4) — replacing
  `content_service._image_exists` and its use in `_check_hotspot_image`;
- the reference counts on the library list (D4);
- the ID → ref rewrite on export (D7);
- the image copy on game move (D3).

The second T7 type registers its image fields there and nowhere else.

**Finding references in SQL.** The delete and replace checks need the reverse direction ("which
questions use image 7?") across **all** questions, as a safety net independent of D3's course
rule. `image_service.find_references(db, image_id)`:

```sql
SELECT id, game_id FROM questions
WHERE prompt_image_id = :id
   OR (type = 'hotspot'
       AND JSON_EXTRACT(config, '$.imageId') = :id)
   OR (type IN ('multiple_choice', 'multi_select')
       AND JSON_CONTAINS(JSON_EXTRACT(config, '$.optionImageIds'), CAST(:id AS JSON)))
```

`JSON_CONTAINS` on a list with `null` entries matches the integer entries only; a missing
`optionImageIds` makes `JSON_EXTRACT` return SQL `NULL`, so that branch is false. The type filters
matter: other types' `config` may hold integers that are not image IDs. Test 19 checks this query
and `question_image_ids` agree for every question type.

**Alternative considered — a `question_images` link table** kept in sync by `content_service` on
every write. The database would then enforce C7 completely through foreign keys. Rejected because
it is a second copy of what `config` already says, and the two can drift; every question write
already goes through `content_service` (admin, host, import, game move), so the query approach has
one source of truth. Revisit if a fourth reference kind appears.

**Validation stays symmetric.** T4's D8 re-validates the whole merged question on every update, so
the new rules apply to create and update alike (the T7 warning in `instructions.md`).

**Locking.** Every path that checks or changes image rows locks them **in ascending ID order**:
the existence check takes `SELECT … FOR SHARE` on the question's image rows; delete, replace and
game-move copy take `FOR UPDATE` on the rows they touch. Ascending order means two transactions
can't each hold a lock the other waits for. This closes the save-vs-delete race (§8 risk 2).

### D6. Replace without breaking C1

C1 forbids changing the bytes under an existing ID, so "replace" is built around it. T8's
Management row names replace explicitly ("viewed, replaced, and deleted through the interface"),
which is why it lives in the library.

| Option | How it works | Pros | Cons |
|---|---|---|---|
| **A. Upload-and-repoint (chosen)** | Store the new file in the same course, repoint every question the caller may edit from the old ID to the new one, then delete the old row if nothing still uses it | A visible "Replace" in the library, clearly meeting T8; fixes every question at once | The most logic in T8: permission filter, live-game check, hotspot check, partial repoint |
| B. Swap in the editor | No replace route. The author picks a different image in each question, then deletes the old one | Almost no new logic | Tedious when an image is in several questions; a grader may not count it as "replace" |
| C. Refuse while used | Replace only allowed for unused images | Simple and safe | Replacing an unused image is just delete + upload, so it adds nothing |

**`POST /api/images/{id}/replace` in detail** — one transaction; any refusal changes nothing:

1. 404 unknown image; 403 unless admin or HOST of its course. Validate the new file (D2).
2. **Same bytes as the old image** (same `sha256`) → 422 "The new file is identical to the
   current image".
3. Find the old image's references (D5) and keep the questions in games the caller may edit
   (admin: all; host: the T4 rule — game grant **and** HOST of the course).
4. **409** "You can't edit any of the N questions that use this image" if there are references
   but none the caller may edit.
5. **409** if any of the editable games has a live session (T4 D7), or if any editable question
   is hotspot and the new image's aspect ratio (`width / height`) differs from the old one by more
   than 1% relative. Hotspot targets are stored as fractions of the image, so they only stay in
   the right place if the shape matches.
6. Store the new file with `create_image` — or reuse an identical image already in the course
   (D2's duplicate rule). Either way that row is the **target**.
7. Repoint the editable questions to the target: `prompt_image_id`, `optionImageIds` entries and
   `config.imageId`, plus hotspot `config.aspectRatio` set to the target's ratio. Write new
   `config` dicts, never mutating the loaded JSON in place.
8. Delete the old row if no references remain; otherwise keep it (a game the caller can't edit
   still uses it).
9. Respond 200 `ReplaceResult`: `{id: target, replaced_id: old, repointed_questions,
   old_deleted}`.

An **unused** image (no references) skips steps 3–5 and 7: the new file is stored and the old row
deleted — the library's Replace still works on it.

**Known consequence:** completed sessions' HTML reports render a question's *current* image, so a
replaced image also changes old reports. Accepted: reports read questions live today anyway.

### D7. Export/import: version 2 bundle

Built by Vincent as part of T8, together with the real existence check, instead of in Arjun's
stage C. Both have to cover prompt and option images as well as hotspot; one owner avoids two
people editing `content_service.import_game` / `export_game` at once. This supersedes the image
parts of `t7-hotspot.md` §9 stage C (§3 Docs row).

T8 implements the bundle format Arjun specified in `t7-hotspot.md` §6 — a top-level `images` array
of `{ref, content_type, data_base64}`, and refs instead of IDs — extended to T8's own fields:

| Reference | In the stored question | In a v2 bundle |
|---|---|---|
| Hotspot | `config.imageId` | `config.imageRef` (Arjun's) |
| Prompt | `prompt_image_id` column | question-level `prompt_image_ref` (snake_case, like `time_limit_seconds`); key present only when the question has a prompt image |
| Options | `config.optionImageIds` | `config.optionImageRefs` (same length, `null` entries kept) |

**Export:** a game using no images exports as **version 1, byte for byte as today**. Otherwise
version 2: refs `img1`, `img2`, … in first-use order (prompt, then options, then hotspot, question
by question), each image once, bytes and `content_type` from C5.

**Import — raw image IDs never travel.** An ID only means something in the database that wrote
it, so (extending `t7-hotspot.md` §6.3.3 from hotspot to all three kinds):

| Bundle content | Version 1 | Version 2 |
|---|---|---|
| `prompt_image_id`, `config.optionImageIds` or hotspot `config.imageId` | 422 "Question N: image IDs can't be imported; export the game again to get a version 2 file" (hotspot keeps its existing §6.3.3 message) | 422, same message |
| `prompt_image_ref`, `config.optionImageRefs`, `config.imageRef` | 422 "Question N: image references require a version 2 bundle" | Must name an `images[].ref`; `optionImageRefs` must match `options` in length, entries a ref string or `null` |
| Both an ID and a ref for the same field | 422 | 422 |

**Version 2 import steps** (one transaction; any error → 422 naming the 1-based question or image,
and nothing is created):

1. Check `images` (§6.3.4.1 of `t7-hotspot.md`): a list; each entry a unique non-empty string
   `ref`, a string `content_type`, and strictly decodable `data_base64`. **`content_type` is not
   trusted:** it must be a string, but the stored type comes from the bytes (D2). A mismatch is
   not an error — the bytes win.
2. Check every question's refs (table above).
3. **Structural pre-validation:** build a copy of each question with every ref replaced by the
   placeholder ID `1` and run `QuestionCreate` on it. This step is **schema-only**: no existence
   or course check runs on placeholders.
4. Create each **referenced** image in the target course with `create_image` (D2 rules, duplicate
   reuse included; unreferenced entries are ignored). Invalid bytes → 422 "Image K: …". Map
   `ref → id`.
5. Create the game and questions with the real IDs, `order_index` 0..n-1, prompts sanitized, then
   the T4 auto-grant rule. The created images are in the target course by construction, so no
   separate existence or course check is needed for them.

Unmodified version-1 files in `sample_games/` keep importing (T6 requirement); none of them carry
image fields.

### D8. Where images appear

**Prompt images show on the host's big screen, not on phones.** Today players never see the
prompt on their phone (`frontend/player/src/README.md`): the room reads it from the big screen,
Jackbox-style. Prompt images follow the prompt. Exception: hotspot already shows its prompt and
image on the phone, because the image is the answer surface (unchanged).

**Option images show on both** — the phone needs them to answer, the big screen shows the same
choices.

| Surface | Prompt image | Option images |
|---|---|---|
| Host question screen | Large, above the prompt text | Tiles with letter and text (if any) |
| Player question screen | — | Large tap tiles with letter; text under the image if present |
| Host results / game over | Small, beside the prompt | Thumbnails on the result bars |
| Player results / game over | — | Thumbnail of the player's choice and of the correct choice |
| HTML report | Data URI above the prompt | Thumbnails beside the bars |
| Question editors (admin, host) | Preview beside the picker | Preview per option |

**Image-only options** (text empty) are labelled by letter plus "(image)" wherever text is
shown: host result bars, player result lines, the report's bar labels (e.g. "B (image)"). The
score CSV export has no option text (one points column per question), so it is unchanged.

The player starts loading option images as soon as `new_question` arrives, as H11 does for hotspot,
and the host loads the prompt image the same way, so loading overlaps reading.

## 5. Data shapes and validation

**Question fields** (`schemas/admin.py`, `QuestionCreate`; `QuestionUpdate` via the D8 merge):

- `prompt_image_id`: optional positive integer or `null`. Accepted for every type.
- `config.optionImageIds` (`multiple_choice`, `multi_select` only): optional; if present, a list
  of the same length as `config.options`, each entry a positive integer or `null`; booleans
  rejected (as in the hotspot checker). Any other type carrying it → 422.
- With `optionImageIds`, `options[i]` may be empty after `strip()` only when `optionImageIds[i]`
  is an integer. Without it, today's option rules are unchanged.
- After schema validation, `content_service` checks every ID from `question_image_ids` exists
  (C4) and belongs to the game's course (D3), and that the game has a course: failure → 422
  naming the field (`prompt_image_id`, `config.optionImageIds[2]`, `config.imageId`).

**Live game payload** (`websocket/gateway.py`, `_question_payload`): adds `promptImageId`
(`null` when absent). `config` already carries `optionImageIds` and hotspot's `imageId`. No
scoring change: images never affect points, so `calculate_score`, the simulator and the scoring
engine are untouched.

**API response** (`QuestionResponse`): adds `prompt_image_id`.

## 6. Implementation outline (files touched)

The tables below list every file each owner touches; §6.1 orders the work into atomic,
test-first steps.

**Vincent**

| File | Change |
|---|---|
| `backend/app/migrations/versions/005_images.py` | `images` table with unique `(course_id, sha256)`; `questions.prompt_image_id` + FK + index |
| `backend/app/models/image.py`, `models/__init__.py`, `models/game.py` | `Image` model; `Question.prompt_image_id` |
| `backend/app/services/image_service.py` | D2 validation, `create_image` (savepoint), `get_image`, `image_exists`, `question_image_ids`, `find_references`, list with counts, delete, replace, copy-to-course, ascending-ID locking |
| `backend/app/services/content_service.py` | Existence + course check (replaces `_image_exists`); v2 export/import (D7); image copy on game move (D3) |
| `backend/app/schemas/image.py`, `schemas/admin.py` | `ImageItem`, `ImagePage`, `ReplaceResult`; question fields and rules (§5) |
| `backend/app/routers/images.py`, `backend/app/main.py` | Router (D4), mounted at `/api` |
| `backend/requirements.txt` | Pillow |
| `nginx/nginx.dev.conf` | `client_max_body_size 25m` (C8) |
| `docker-compose.yml`, the `_image_exists` unit test | Backend dev-image stand-in removed (same commit as the real check) |
| `admin/` and `host/` `src/lib/api.ts` | `listImages`, `uploadImage`, `replaceImage`, `deleteImage` |
| `admin/` and `host/` `src/components/ImagePicker.tsx` | Modal: paged grid of the course's images, upload button, returns the chosen ID (contract in §3) |
| `admin/` and `host/` `src/pages/ImagesPage.tsx`, `App.tsx` route, **Images** button on `CourseDetailPage` / `CoursePage` | Library: grid with size, dimensions, uploader, "used by N", Replace, Delete (disabled while used), "unused" filter |
| `docs/plans/t7-hotspot.md` | §4 real names + link here; §9 stage C pointer here |

**Arjun**

| File | Change |
|---|---|
| `backend/app/websocket/gateway.py` | `promptImageId` in the question payload |
| `backend/app/services/report_service.py` | Hotspot, prompt and option images as data URIs; "(image)" labels (D8) |
| `admin/` and `host/` `src/pages/QuestionEditorPage.tsx` | Prompt image and per-option images via `ImagePicker`; hotspot adapter; disabled pickers for unassigned games; admin `Game` type gains `course_id` |
| `player/src/components/QuestionImage.tsx` (+ host copy) | Loads through the existing `lib/images.ts`; placeholder, then the image or "Image unavailable" |
| `player/src/pages/game/QuestionPage.tsx`, `ResultsPage.tsx`, `GameOverPage.tsx` | Image option tiles; thumbnails in results (D8) |
| Host game screens (`QuestionPage`, `ResultsPage`, `GameOverPage`) | Prompt image; option tiles; thumbnails on result bars (D8) |
| `player/` and `host/` `src/types/game.ts` | `promptImageId`, `optionImageIds` |
| Vite `devImages` plugins, `frontend/dev-images/` | Removed after Vincent's existence check is merged into his branch (§3 Order) |

Each owner updates the READMEs of the directories they touch in the same branch
(`.claude/rules/context-sync.md`).

### 6.1 Ordered steps

**Rules for every step**

- One step = one atomic commit (or a short run of them) with an imperative message, authored as
  `<netid>@wisc.edu` (T1).
- **Backend steps are test-first:** write the step's integration tests (§7 numbers), run them
  against the live stack and see them fail for the right reason, implement, then run the **full**
  integration suite. Existing tests are never deleted or weakened (T5).
- Before each commit: `ruff check backend/ scripts/` and `ruff format --check backend/ scripts/`.
  Frontend steps: `npx tsc --noEmit` in every touched app, then a manual check on the nginx build
  (`npm run build`, `localhost:8080`), where auth and the shared origin match production.
- Every step updates the READMEs of the directories it touches.
- If a step shows this doc is wrong, update the doc first, in its own commit, then the code (T3
  step 6).

**Branches.** Vincent works on `feat/t8-image-support`. Arjun branches `feat/t8-image-display`
from it once V3 is pushed, and merges `main` into his branch after Vincent's MR lands, so his MR
shows only his own commits. Each MR is approved by the other member (T2).

**Vincent — `feat/t8-image-support`**

| Step | What | Tests first | Done when |
|---|---|---|---|
| V0 | Update `t7-hotspot.md` §4 (real function names, link to this doc) and §9 stage C (pointer to this doc's §3). Docs only | — | Arjun has seen it in the MR |
| V1 | Migration 005 and models: `images` (D1, unique `(course_id, sha256)`), `questions.prompt_image_id` (FK RESTRICT, index); `Image` model; `Question.prompt_image_id` | — (no route yet) | `alembic upgrade head` then `downgrade -1` then `upgrade head` all succeed on the live stack; full suite still passes |
| V2 | Pillow in `requirements.txt` (rebuild the backend image); nginx `client_max_body_size 25m`; `image_service.create_image` (D2: sniff, limits, capped read, re-save-on-metadata, savepoint duplicate handling), `get_image`, `image_exists`; `routers/images.py` with `POST /api/images` and `GET /api/images/{id}`; `schemas/image.py` `ImageItem` | 1, 2, 3, 4, 5, 22, and the upload/fetch rows of 6 | Tests pass through nginx (`localhost:8080`), not only on port 8000, so the 25 MB limit is exercised |
| V3 | Question fields (§5) in `schemas/admin.py`; `question_image_ids`; `content_service` existence + course check replacing `_image_exists` / its use in `_check_hotspot_image`, with `FOR SHARE` ascending-ID locks; `QuestionResponse.prompt_image_id`. **Same commit:** remove the backend dev-image stand-in (`docker-compose.yml` `/dev-images` mount, `tests/unit/test_hotspot_image_check.py`), and switch the stage-B tests in `tests/integration/test_hotspot.py` that use dev image `1` to an image uploaded in their setup — every assertion kept | 9; the switched hotspot tests | Full suite passes with no dev-image folder mounted |
| V4 | `find_references` (D5 SQL); `GET /api/images` list with batched `reference_count`, `unused` filter, paging, `uploaded_by_name` (`ImagePage`); `DELETE /api/images/{id}` with `FOR UPDATE` locks and the C7 409 | 7, 8, 19, and the list/delete rows of 6 | — |
| V5 | `POST /api/images/{id}/replace` exactly as D6 steps 1–9 (`ReplaceResult`) | 10, 11, 12, and the replace row of 6 | — |
| V6 | Game-move image copy in `content_service.update_game` (D3) | 20 | — |
| V7 | v2 export/import in `content_service` (D7) | 13, 14, 15, 21 | Every `sample_games/*.json` still imports through both the admin and host import routes |
| V8 | Admin and host `lib/api.ts` image calls; `ImagePicker` (§3 contract) in both apps | — | `tsc` clean; picker lists, uploads and returns an ID on the nginx build |
| V9 | `ImagesPage` at `/courses/:courseId/images` in both apps; **Images** buttons on admin `CourseDetailPage` and host `CoursePage` | — | Manual check: upload, replace (including a refused case), delete (refused while used), unused filter, as admin and as a course HOST |
| V10 | Session-log entry, pre-push checks, push, open the MR | — | MR description links this doc and lists §7 test numbers |

**Arjun — `feat/t8-image-display`** (starts after V3 is pushed; A5 needs V8)

| Step | What | Tests first | Done when |
|---|---|---|---|
| A1 | `promptImageId` in `_question_payload`; `promptImageId` / `optionImageIds` in both `types/game.ts` | 16 | — |
| A2 | `QuestionImage` component (player + host copy); host question screen shows the prompt image; option tiles with images on player and host (D8) | — | Manual round on the nginx build with an image prompt and image options, one player and one guest |
| A3 | Results and game-over thumbnails; "(image)" labels for image-only options (D8) | — | Manual check incl. an image-only option |
| A4 | `report_service`: hotspot image via C5 (replacing the `_hotspot_image_data_uri` stub), prompt and option images as data URIs, "(image)" labels | 17 | — |
| A5 | Question editors (admin + host): prompt-image and per-option pickers via `ImagePicker`; hotspot adapter; disabled pickers for unassigned games; admin `Game` type gains `course_id` | — | Manual: author each kind in both apps, then play it |
| A6 | Remove the Vite `devImages` plugins and `frontend/dev-images/` (checklist in its README) | — | Hotspot authoring and play work in `npm run dev` with uploaded images |
| A7 | Hotspot tests marked **T8** in `t7-hotspot.md` §10 | 18 | — |
| A8 | Stage E: hotspot questions in his two T6 games as v2 bundles (after V7) | 15's second half | Both files import through the admin and host routes |

## 7. Integration tests (T5)

New files under `tests/integration/`, run against the live stack. **Cleanup** (T5's warning that
deletion paths must undo creation paths): each test deletes what it created in reverse order —
sessions and games first (existing helpers, which already clear Redis), then its images through
`DELETE /api/images/{id}`, which succeeds once nothing references them. Courses are never deleted
(no endpoint), as in the existing suite.

**Vincent**

| # | Behaviour | Expected |
|---|---|---|
| 1 | Upload PNG, JPEG, WebP into a course | 201; metadata matches; GET returns identical bytes and the right type |
| 2 | Upload rejections: text file named `.png`, SVG, GIF, 2 MB + 1 byte, 5000 px wide, truncated/corrupt PNG, empty file | 422 each, with the expected message; no row created |
| 3 | JPEG with EXIF rotation and GPS | Stored width/height match the rotation; no EXIF in the stored bytes |
| 4 | Identical bytes uploaded twice to one course; then to a second course | Second call 200 with the same `id`; the other course gets its own row |
| 5 | GET by a guest token; GET unknown ID; GET without a token | 200 with the C3 header and `nosniff`; 404 without the cache header; 401 |
| 6 | Upload, list, replace, delete by a PLAYER, a guest, and a HOST of a different course | 403 each |
| 7 | List per course: `reference_count`, `unused` filter, paging, `uploaded_by_name`; unknown course | Correct values; 404 |
| 8 | Delete while used — once per reference kind (prompt, option, hotspot) | 409 naming the count; image still readable |
| 9 | Question create/update with prompt and option images; unknown ID; other course's image; unassigned game; list length mismatch; whitespace-only option without image; `optionImageIds` on a `true_false` question | Success, or 422 naming the field |
| 10 | Replace: repoints the caller's questions; old row deleted when unused; kept when a game the caller can't edit still uses it; unused image replaced | `ReplaceResult` as expected |
| 11 | Replace refused: live game; hotspot aspect-ratio mismatch; identical bytes; no editable referencing question | 409 / 422 as in D6; nothing changed |
| 12 | Replace with bytes identical to another image in the course | That image becomes the target; no new row |
| 13 | v2 export → import into another course, all three reference kinds | New image rows in the target course with identical bytes; IDs remapped; no new rows on a second import into the same course |
| 14 | Broken bundles: unknown ref, duplicate ref, bad base64, invalid image bytes, raw `prompt_image_id` / `optionImageIds` in v1 and v2, refs in a v1 bundle, ID and ref on one field | 422; no game, question or image created |
| 15 | Every `sample_games/*.json` (v1) still imports; image-free game still exports as v1 | — |
| 19 | `question_image_ids` and `find_references` agree for every question type, including `null` option entries and missing fields | — |
| 20 | Admin moves a game with images to another course; again to a course that already has one of the images; to the same course | Copies made and questions repointed; existing duplicate reused; same-course move changes nothing |
| 21 | Bundle `content_type` that disagrees with the bytes | Imports; stored type follows the bytes |
| 22 | Two concurrent uploads of identical bytes | One row; both responses carry its `id`; no 500 |

**Arjun**

| # | Behaviour | Expected |
|---|---|---|
| 16 | `new_question` socket payload carries `promptImageId` and `optionImageIds` | — |
| 17 | HTML report of a session with prompt images, option images and an image-only option | Data URIs embedded; "(image)" label |
| 18 | Hotspot tests marked **T8** in `t7-hotspot.md` §10 (real images replace the dev image) | As specified there |

## 8. Risks and self-critique

1. **Any logged-in token can read any image.** A guest could step through `/api/images/1, 2, 3…`
   and preview the image of a question not yet shown. C3 requires guest access; the alternatives
   (random IDs, breaking C2; checking the image belongs to the caller's current room, fragile on
   reconnects and costly per request) don't pay for themselves. Accepted, because prompt images
   are not answers — but an author can still make the image itself the giveaway.
2. **Delete vs. save race.** Without locking, a save's existence check and a delete's reference
   check could both pass and leave a dangling JSON reference. D5's ascending-ID row locks
   serialize them; prompt images are also protected by the FK.
3. **References live in two places** (a column and JSON). Test 19 guards against drift. See the
   link-table alternative in D5.
4. **Course ownership duplicates images.** The same picture used in two courses is stored twice,
   and every admin game move copies its images. Acceptable at classroom scale (2 MB cap); the
   per-course duplicate rule keeps repeated imports from multiplying.
5. **Unused images pile up.** Deleting a question or game never deletes its images, and a game
   move leaves the originals behind. The library's "unused" filter makes cleanup manual; deleting
   automatically would surprise someone who uploaded an image for later.
6. **Replace (D6) is the most complex piece.** Every refusal case has a test (10–12) so "holds up
   under realistic use" (R8) is shown, not assumed.
7. **No thumbnails.** A library page of 24 images at up to 2 MB each can be up to 48 MB; lazy
   loading and the browser cache reduce it. Stored thumbnails would be another column and a second
   C3-style route.
8. **Uploads are not rate-limited.** A host account could fill the database with 2 MB images.
   Accepted for a classroom deployment; `common/rate_limit` could add a per-user limit.
9. **Split ownership across two branches.** Arjun's display work depends on Vincent's migration
   and `ImagePicker`. The §3 contract and Order let him start early, but a contract change after
   he starts costs both of us; any change goes into this doc first.
10. **Prompt images are big-screen only (D8).** A player sitting where they can't see the screen
    misses the image, exactly as they miss the prompt today. Showing prompts on phones would be a
    separate, larger UX change.

## 9. Alternatives rejected (summary)

| Alternative | Why rejected | Where |
|---|---|---|
| Files on disk or object storage | T8 requires the database; loses C6's transactional rollback | D1 |
| Accept SVG / GIF | Script-injection risk; multi-frame breaks hotspot | D2 |
| Store bytes as uploaded | Sideways phone photos break hotspot; GPS leaks | D2 |
| Re-save every upload | JPEG degrades on each export → import | D2 |
| Uploader-owned or global library | Doesn't follow T4's course model / no isolation | D3 |
| Refuse game moves while images are used | Takes away T4's admin move | D3 |
| Separate admin and host image routers | Same rules twice; fetch must serve players too | D4 |
| Options as `{text, imageId}` objects | Breaks every existing consumer of `options` | D5 |
| `question_images` link table | Second copy of the truth in `config` | D5 |
| Overwrite bytes on replace | Violates C1; breaks hotspot targets and cached copies | D6 |
| Replace by swapping images in the editor | Weak match for T8's "replaced through the interface" | D6 |
| Raw image IDs in bundles | Point at arbitrary images in another database | D7 |
| Prompt images on phones | Players don't see prompts on phones today; a separate UX change | D8 |

## 10. Dependencies and order

- **Needs:** T4 phase 3 (merged into this branch; must merge to `main` before T8's MR).
- **Unblocks:** hotspot stage E (`t7-hotspot.md` §9); both members' T6 games that use images.
- **T9:** the library page, picker and image tiles must use T9's theme tokens once they exist.

## 11. Process

1. Settle §12 → agreed (done 2026-10-04).
2. Goldfish test in a fresh session → revised (§13, done 2026-10-04).
3. Turn it into the precise spec (`write-spec`): ordered, test-first steps per owner (§6.1, done 2026-10-04).
4. Implement against it; update the doc first if implementation diverges.

## 12. Decisions (all settled 2026-10-04)

| # | Question | Decision |
|---|---|---|
| Q1 | Who owns images? | The course (D3) |
| Q2 | Who builds v2 export/import and the real existence check? | Vincent, in T8 (D7) |
| Q3 | How does "replace" work? | Upload-and-repoint (D6 option A) |
| Q4 | Re-save uploads that carry metadata? | Yes (D2) |
| Q5 | What happens to a game's images when an admin moves it to another course? | Copy them into the new course and repoint (D3) |
| Q6 | Where is image work specified? | All image support is handled by T8 (this doc), including the image parts of hotspot stage C |
| — | Who builds what? | Vincent: image upload and management; Arjun: canvas and image integration (§3) |

## 13. Goldfish revisions (2026-10-04)

A fresh session given only this doc and the repo's standing documentation (context READMEs,
`instructions.md`, `rubric.md`, the T4 and T7 plans) explained the feature back correctly, then
found the gaps below and judged that neither owner could start without follow-up questions. Each
gap was fixed here.

| # | Severity | Gap the Goldfish found | Change |
|---|---|---|---|
| 1 | Blocking | No rule for raw `prompt_image_id` / `optionImageIds` in bundles (they would bind to arbitrary local images); placeholder handling for the new refs undefined | D7: raw IDs rejected in v1 and v2, refs only in v2, ID + ref on one field rejected; placeholder pre-validation is schema-only; test 14 extended |
| 2 | Blocking | `ImagePicker` used `null`, `HotspotEditor`'s slot uses `undefined`; no source for `courseId`; unassigned games; whether the picker returns dimensions | §3 contract: adapter, `courseId` from the loaded game, disabled pickers for unassigned games, picker returns the ID only |
| 3 | Blocking | Players never see the prompt on their phone today, yet the draft put the prompt image on the player screen | New D8: prompt images on the big screen; option images on both; surface table |
| 4 | Important | Replace edge cases: identical bytes, duplicate of another image, nothing editable, status code and field names | D6 rewritten as numbered steps with each case; `ReplaceResult` schema; tests 10–12 |
| 5 | Important | Concurrent identical uploads → `IntegrityError` → 500 | D2: savepoint + re-select; test 22 |
| 6 | Important | Bundle `content_type` trust undefined | D7: required string, not trusted, bytes win; test 21 |
| 7 | Important | Test cleanup and course deletion unaddressed | §7 cleanup paragraph; course deletion listed out of scope |
| 8 | Important | Library route, nav, course choice and list schema unspecified | D4: `/courses/:courseId/images` via an Images button, `ImageItem` / `ImagePage` schemas, batched reference counts |
| 9 | Important | Game-move copy details and lock ordering (deadlock risk) | D3: copy stored bytes without a Pillow pass, same-course move no-op; D5: ascending-ID locking; test 20 |
| 10 | Important | `find_references` SQL only described | D5: exact SQL with `null`/missing-field behaviour |
| 11 | Important | Dev-image stand-in removal order could break dev hotspot authoring | §3: backend half removed with the real check (Vincent); frontend half after it is merged (Arjun); Order section |
| 12 | Minor | Image-only option labels unspecified | D8: "B (image)" label; CSV unaffected (no option text) |
| 13 | Minor | Oversized upload read whole into memory | D2: read at most 2 MB + 1 byte |
| 14 | Minor | `t7-hotspot.md` §4 / §9 update only "should" | §3 Docs row: Vincent updates both in the first implementation commit; C6 signature difference explained in D4 |
| 15 | Minor | Whitespace-only option text | D5/§5: empty after `strip()` |
| 16 | Minor | Status line inconsistent; no revisions section | Status updated; this section |
