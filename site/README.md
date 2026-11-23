# Pixel Lanka: site

The web app: Next.js 16 (App Router) with [OpenSeadragon](https://openseadragon.github.io/) showing the deep-zoom map tiles that `pipeline/` renders. See the [main README](../README.md) for the whole project.

```bash
npm ci
npm run dev        # http://localhost:3000
npm run lint
npm run typecheck
npm run build      # static export into out/
```

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_TILES_BASE` | `<basePath>/tiles` | Where `world.json`, `landmarks.json` and the tile pyramids are served from |
| `NEXT_PUBLIC_BASE_PATH` | — | Sub-path the site is served from, e.g. `/pixel-lanka` on GitHub Pages (set by the deploy workflow) |
| `NEXT_PUBLIC_SITE_URL` | — | Origin of the public site (no path), used for social preview (Open Graph) links |

Layout:

- `components/MapViewer.tsx`: viewer setup, overlay stacking, URL sync, fly-to, pins.
- `components/Search.tsx`: client-side search over every map's `places.json` plus the landmarks.
- `components/Landmarks.tsx`: landmark card strip and detail panel.
- `lib/geo.ts`: lat/long ↔ image pixel maths. It mirrors `pipeline/render.py` and is covered by `tests/test_projection.py`.

The map uses the canvas drawer (`drawer: 'canvas'`), because OpenSeadragon's WebGL drawer mis-blends the transparent city overlay tiles.
