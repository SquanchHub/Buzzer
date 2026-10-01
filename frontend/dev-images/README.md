# frontend/dev-images/ — DEV ONLY, remove in T7 stage C

Test images for playing hotspot questions under `vite` dev before T8's image API exists
(`docs/plans/t7-hotspot.md` §13.1 e). The dev-only `devImages` plugin in
`frontend/host/vite.config.ts` and `frontend/player/vite.config.ts` answers
`GET /api/images/{id}` with `{id}.png` from this folder. It runs only under `vite` (dev server,
`apply: 'serve'`); production builds and nginx never see these files.

| File | Size | Aspect ratio | Source and licence |
|---|---|---|---|
| `1.png` | 800 × 400, 32-colour palette PNG (~5 KB) | 2.0 | **Self-made** test pattern, released **CC0**: a coordinate grid every 0.1 with axis labels, plus landmarks to aim at — red dot at (0.25, 0.5), green square at (0.75, 0.3), blue triangle near (0.5, 0.75). Drawn with Pillow (`ImageDraw` lines, shapes and default font). |

## Playing a hotspot question in dev

1. Stack up (`docker compose up`), then `npm run dev:host` and `npm run dev:player` (the route only
   exists on the Vite dev servers, not on nginx at :8080).
2. Create a hotspot question with `imageId: 1` and `aspectRatio: 2.0` through
   `POST /api/admin/games/{id}/questions` (the admin app has no hotspot editor yet), e.g. target
   `{"x": 0.25, "y": 0.5, "innerRadius": 0.05, "outerRadius": 0.12, "partialFraction": 0.5}`.
3. Run the game from the host app and join from the player app.

An unknown ID falls through to Vite's HTML fallback, which the apps reject, so the canvas shows
"Image unavailable" — handy for testing that path (e.g. `imageId: 99`).

## Removal (stage C)

Delete this folder, the `devImages` plugin and the `server.fs.allow` line from both
`vite.config.ts` files, and the gotcha in `frontend/README.md`.
