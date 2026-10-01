# frontend/admin/src/pages/

One React component per Admin app screen. `frontend/admin/src/App.tsx` wraps every route except
`/login` in `RequireAdmin` (token present) and `AdminLayout` (left sidebar: Courses, Users, Games,
Guests, Sessions, Logout). Pages fetch on mount with `api` from `lib/api.ts`, keep everything in
local `useState`, and re-fetch after each mutation. There is no shared store, no socket, and no
pagination.

## Files

| File | Route | Purpose |
|---|---|---|
| `LoginPage.tsx` | `/login` | Username/password form → `POST /auth/login`, stores `token`, goes to `/courses`. |
| `CoursesPage.tsx` | `/courses` | List, create and rename courses; link to each course's roster. |
| `RosterPage.tsx` | `/courses/:courseId/roster` | Roster table with inline edit (name, netid, email, active), plus a client-side CSV column-mapping import wizard. |
| `UsersPage.tsx` | `/users` | List non-guest users; create local accounts. Row click → user detail. |
| `UserDetailPage.tsx` | `/users/:userId` | Edit a user (username, display name, email, password, role USER/ADMIN), delete, grant/revoke course access (HOST or PLAYER) and game access. |
| `GuestsPage.tsx` | `/guests` | List guest accounts, merge a guest into a netid, delete guests. |
| `GamesPage.tsx` | `/games` | List, create, edit and delete games; import a game JSON file. |
| `QuestionEditorPage.tsx` | `/games/:gameId/questions` | Add, edit, delete and reorder a game's questions; export the game as JSON. |
| `SessionsPage.tsx` | `/sessions` | All sessions with a status filter; per-session HTML report, CSV export (Canvas or raw options), delete. |

Unknown routes redirect to `/courses`.

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

- **`RequireAdmin` doesn't check the role.** It only checks that a token exists, so a USER-role
  account can log in and see the full sidebar; every request then fails with 403.
- **Literal `…` / `·` on screen.** JSX text and string attributes don't process JS
  escapes, so `Loading…` (UsersPage, GuestsPage, GamesPage, QuestionEditorPage),
  `placeholder="Question text…"`, and `{…}s · {…}pts` / `(±{…} edit distance)` in
  the question list render the backslash sequence literally. Escapes inside `{'…'}` expressions are fine.
- **Question editor quirks:** blank multiple-choice options are sent as-is (the backend accepts empty
  strings), while blank multi-select options are filtered — but multi-select `points_value` is still
  summed over the unfiltered list. Switching `type` while editing keeps the other types' hidden state.
  Each new question type (T7) needs a form branch, a `build*Payload`, `questionToForm` and
  `formToPayload` cases, a `typeLabel` entry, and a list-view preview.
- **Delete paths that can fail:** deleting a question that has already been played errors at the DB
  (see `backend/app/models/README.md`); deleting a game wipes all its sessions and scores after a
  single `confirm()`.
- **Raw CSV export ignores `per_question`** — the page sends it, but the backend's raw format always
  emits per-question columns.
- **T4 overlap:** roster, game and question management and session downloads are exactly the host
  capabilities T4 asks for; today they exist only here behind `require_admin`.
- **Hardcoded palette everywhere** — status badges (`STATUS_COLORS`), selects, textareas, toggles and
  tables use raw `slate`/`indigo`/`green`/`red` utilities (T9).
