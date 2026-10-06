# frontend/admin/src/pages/

One React component per Admin app screen. `frontend/admin/src/App.tsx` wraps every route except
`/login` in `RequireAdmin` (token present **and** its `role` claim is ADMIN) and `AdminLayout`
(admin-first sidebar: **Administration** — Users, Courses, Guests; then a smaller **Content &
hosting** group — Games, Sessions; footer links to the Host app's `/host/home` — its root always shows the login form — and
the Player app, then Logout). Pages fetch on mount with `api` from `lib/api.ts`, keep everything in
local `useState`, and re-fetch after each mutation. There is no shared store, no socket, and no
pagination.

## Files

| File | Route | Purpose |
|---|---|---|
| `LoginPage.tsx` | `/login` | Username/password form → `POST /auth/login`; stores `token` and goes to `/users` only for an ADMIN token (a non-admin login is refused without storing it, so the shared token isn't replaced). Shows `RequireAdmin`'s redirect message. |
| `CoursesPage.tsx` | `/courses` | List, create and rename courses; each name links to its detail page; link to each course's roster. |
| `CourseDetailPage.tsx` | `/courses/:courseId` | Rename; HOST/PLAYER members from `GET /admin/courses/:id/access` with role change, removal (confirms when a HOST loses the role, since their game grants stop working) and an add-user form (USER accounts only); roster link; the course's games (`/admin/games` filtered by `course_id` in the browser). |
| `RosterPage.tsx` | `/courses/:courseId/roster` | Roster table with inline edit (name, netid, email, active), plus a client-side CSV column-mapping import wizard. |
| `ImagesPage.tsx` | `/courses/:courseId/images` | The course's image library (T8 D4, D6), opened by the **Images** button on the course detail page: grid of images with size, dimensions, uploader and "Used by N questions"; Upload, Replace (reports how many questions were repointed and whether the old image was kept), Delete (disabled while used); "Unused only" filter; 24 per page. Host copy differs only in its header. |
| `UsersPage.tsx` | `/users` | List non-guest users; create local accounts. Row click → user detail. |
| `UserDetailPage.tsx` | `/users/:userId` | Edit a user (username, display name, email, password, role USER/ADMIN), delete, grant/revoke course access (HOST or PLAYER) and game access. The game picker groups games by course and disables courses the user doesn't HOST (and unassigned games), since a grant there would be refused (409) or dead (D1); granted games whose course they no longer host are marked inactive. Game grants are posted one at a time and failures are listed per game. |
| `GuestsPage.tsx` | `/guests` | List guest accounts, merge a guest into a netid, delete guests. |
| `GamesPage.tsx` | `/games` | List, create, edit and delete games; import a game JSON file. Create requires a course; Import needs a target course picked first (sent as the `course_id` form field). A filter shows all games, one course's, or Unassigned ones; each row links its course (unassigned games are highlighted). The edit form has a course picker (sends `course_id` only when it changes; the live-session 409 shows inside the form). |
| `QuestionEditorPage.tsx` | `/games/:gameId/questions` | Add, edit, delete and reorder a game's questions, including hotspot questions via `components/HotspotEditor` (T7 stage D, ported from the host editor's stage B branches); export the game as JSON. |
| `SessionsPage.tsx` | `/sessions` | All sessions with a status filter; per-session HTML report, CSV export (Canvas or raw options), delete. |

Unknown routes redirect to `/users`.

## Key entry points

- **`QuestionEditorPage`** — the only place questions are authored. Internally:
  `FormState` holds fields for every type at once; `questionToForm(q)` loads a saved question;
  `formToPayload(form)` builds `{type, grading_type, prompt, config, answer_data,
  time_limit_seconds, points_value}` via per-type `build*Payload` helpers. For ACCURACY it
  **derives `points_value`** (MC/FITB: max option points; TF: max of true/false; multi-select: sum of
  positive points); for COMPLETENESS the user types it. Reorder swaps neighbours and posts the full
  ID list to `/questions/reorder`.
- **`RosterPage` import wizard** — parses CSV in the browser (`parseCSV`), auto-detects Canvas
  gradebook columns, previews the mapping, then posts JSON rows to
  `POST /admin/courses/:id/roster/import`. The backend upserts the rows and **deactivates everyone not
  in the upload**. The older multipart endpoint `POST /admin/courses/:id/roster` is not used by the UI.
- **`SessionsPage` export** — builds query params for `GET /admin/sessions/:id/export`
  (`format=canvas|raw`, `title`, `sis_domain`, `roster_only`, `per_question`) and downloads via
  `api.download`; the report button downloads `GET /admin/sessions/:id/report`.

## Depends on

- `frontend/admin/src/lib/api.ts` (`api.*`, `api.postForm`, `api.download`) and
  `frontend/admin/src/components/ui/` (`Button`, `Card`, `Input`).
- `react-router-dom` (`useNavigate`, `useParams`), `lucide-react` icons.
- Backend: every `/api/admin/*` route in `backend/app/routers/admin.py`, plus `POST /api/auth/login`
  and `DELETE /api/game/sessions/{id}` (`routers/game.py`).

## Depended on by

- `frontend/admin/src/App.tsx` — the only importer; maps each page to its route.

## Gotchas found while reading

- **`RequireAdmin`'s role check is UX only.** It decodes the JWT's `role` claim without verifying
  it (`lib/utils.ts` `tokenRole`), so a role changed after login shows up only at the next login;
  the server's `require_admin` is what enforces access.
- **"Open Player app" can sign the admin out.** All apps share `localStorage.token` under nginx;
  the player app's "Play Again" removes it. In `npm run dev` the footer links don't resolve (each
  app has its own port).
- **Literal `…` / `·` on screen.** JSX text and string attributes don't process JS
  escapes, so `Loading…` (UsersPage, GuestsPage, QuestionEditorPage),
  `placeholder="Question text…"`, and `{…}s · {…}pts` / `(±{…} edit distance)` in
  the question list render the backslash sequence literally. Escapes inside `{'…'}` expressions are fine.
- **Question editor quirks:** blank multiple-choice options are sent as-is (the backend accepts empty
  strings), while blank multi-select options are filtered — but multi-select `points_value` is still
  summed over the unfiltered list. Switching `type` while editing keeps the other types' hidden state.
  Each new question type (T7) needs a form branch, a `build*Payload`, `questionToForm` and
  `formToPayload` cases, a `typeLabel` entry, and a list-view preview.
- **Delete paths:** deleting a played question is refused (409 "Question has recorded answers");
  deleting a game is refused while it has a live session (409), and otherwise wipes all its
  sessions and scores after a single `confirm()`. Question edits are also 409 while the game is live.
- **Raw CSV export ignores `per_question`** — the page sends it, but the backend's raw format always
  emits per-question columns.
- **T4 overlap:** roster, game and question management and session downloads are exactly the host
  capabilities T4 asks for; today they exist only here behind `require_admin`.
- **Hardcoded palette everywhere** — status badges (`STATUS_COLORS`), selects, textareas, toggles and
  tables use raw `slate`/`indigo`/`green`/`red` utilities (T9).
