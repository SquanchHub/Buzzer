# sample_games/images/

Source images for the hotspot questions in Arjun's two T6 sample games (`docs/plans/t7-hotspot.md`
§8, stage E). Each one is embedded, byte for byte, in its game's version 2 bundle
(`../world_geography_challenge.json`, `../wild_kingdom_party.json`), so importing a game needs
nothing from this folder; it is kept so the images can be checked, licensed and regenerated.

| File | Size | Aspect | Used by | Source and licence |
|---|---|---|---|---|
| `world_map.png` | 1200 × 600, 16-colour palette PNG, 59 KB | 2.0 | *World Geography Challenge*, "Tap Cairo." | Rendered by Arjun from **Natural Earth** 1:110m Admin 0 countries (`ne_110m_admin_0_countries.geojson` from the official `nvkelso/natural-earth-vector` repository, downloaded 2026-10-06). Natural Earth is **public domain** ("No permission is needed to use Natural Earth", naturalearthdata.com terms of use). The rendered PNG is released **CC0**. |
| `savanna.png` | 1200 × 600, 128-colour palette PNG, 17 KB | 2.0 | *Wild Kingdom Party*, "Tap the giraffe." | **Self-made** by Arjun: a simple scene (sky, grass, sun, two acacias, an elephant, a giraffe and a zebra) drawn with Pillow. Released **CC0**. |

## How they were made

`render_images.py` draws both (Pillow; the map needs the GeoJSON path):

```bash
python sample_games/images/render_images.py path/to/ne_110m_admin_0_countries.geojson
```

It draws at 2× and downsamples for smooth edges, then saves palette PNGs.

- **Map:** every country polygon filled and outlined in a plain equirectangular projection over
  exactly −180..180° longitude and −90..90° latitude, **no labels and no margins**.
- **Savanna:** shapes only. The giraffe is drawn around the `GIRAFFE` constant, which is the
  hotspot target.

## Targets

| Question | Spec target | Authored target | Rings |
|---|---|---|---|
| "Tap Cairo." | `x = 0.5868, y = 0.3331` | `x = 0.5863, y = 0.3310` | inner 0.02, outer 0.05, partial 0.5 |
| "Tap the giraffe." | `x = 0.545, y = 0.52` | `x = 0.5449, y = 0.5177` | inner 0.07, outer 0.17, partial 0.5 |

- **Map derivation:** with no margins, a point at longitude λ and latitude φ is at
  `x = (λ + 180) / 360` and `y = (90 − φ) / 180`. Cairo is at 30.04° N, 31.24° E, which gives
  x = 211.24 / 360 = 0.5868 and y = 59.96 / 180 = 0.3331.
- **Giraffe:** the target is the giraffe's neck base, where `render_images.py` draws it. The rings
  were checked by drawing them on the image: the inner ring covers the body and neck base, the
  outer ring the whole giraffe (head and legs included), and no other animal or tree.
- **Authored vs spec:** both questions were authored in the host question editor (image picked
  with the image picker, centre placed with a click), so the stored centre is within one canvas
  pixel of the spec target (about 0.002 of the image height, 0.001 in scoring units). Tapping
  the spec target scores full points in both games.
