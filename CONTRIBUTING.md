# Contributing to Pixel Lanka

Thanks for helping map Sri Lanka! Bug reports, landmark suggestions, translation fixes and code are all welcome.

## Ways to help

- **Suggest a landmark** or correct a name, translation or description with the *Landmark* issue template. Sinhala and Tamil corrections from native speakers are especially valuable.
- **Report a bug**: something drawn wrong, a place in the wrong spot, or a site problem. Include the `?at=` link from the address bar.
- **Fix the map at the source**: buildings, roads and names come from OpenStreetMap through Overture. Fixing them on [openstreetmap.org](https://www.openstreetmap.org) improves every map, and the fix shows up here after the next data refresh.

## Development

See the [README](README.md#getting-started) to set up. Before opening a pull request:

```bash
make check   # ruff + pytest + eslint + TypeScript
```

Guidelines:

- **Branches and commits**: work on a `feature/…`, `fix/…` or `chore/…` branch and use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:` …).
- **Projection changes** must be mirrored in both `pipeline/render.py` / `pipeline/tiles.py` and `site/lib/geo.ts`, and covered by `tests/test_projection.py`.
- **Rendering changes**: include a before/after screenshot. A quick way to preview is `uv run pipeline/render.py colombo-fort`.
- **Never commit generated files**: `data/`, `site/public/tiles/` and `out/` are ignored for a reason (they're gigabytes).
- **Next.js 16** has breaking changes from earlier versions. Check `site/node_modules/next/dist/docs/` before using an API from memory (see `site/AGENTS.md`).

## Code of conduct

Be kind and assume good faith. Harassment or discrimination of any kind isn't tolerated; maintainers may remove comments or contributors that break this.
