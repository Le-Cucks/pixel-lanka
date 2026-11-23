# Map data licensing

The MIT licence in [LICENSE](LICENSE) covers this repository's **code only**. The map tiles, `places.json`, `landmarks.json` thumbnails and everything in `data/` are produced from third-party open data, which keeps its own licence terms.

All data is read from [Overture Maps Foundation](https://overturemaps.org) release `2026-11-18.0`. Overture combines several sources:

| Overture theme used | Main upstream sources | Licence |
|---|---|---|
| Buildings | OpenStreetMap, Google Open Buildings, Microsoft Global ML Building Footprints | ODbL 1.0 (Google's footprints are also available under CC BY 4.0) |
| Transportation (roads, rail) | OpenStreetMap | ODbL 1.0 |
| Base (water, land, land use) | OpenStreetMap | ODbL 1.0 |
| Base (land cover) | ESA WorldCover | CC BY 4.0 |
| Places | Meta, Microsoft and others | CDLA Permissive 2.0 |

Check [Overture's attribution and licensing page](https://docs.overturemaps.org/attribution/) for the current, authoritative terms.

## What this means in practice

- **Rendered tiles** are images drawn from these databases ("Produced Works" in ODbL terms). They may be shared and reused, but must carry attribution. The map shows: © OpenStreetMap contributors · Overture Maps · Google Open Buildings · Microsoft · ESA WorldCover. Keep it if you redistribute or embed the tiles.
- **Extracted data**, such as the `places.json` search index or anything in `data/`, is a derivative database. Where it contains OpenStreetMap data it must stay under the ODbL (share-alike) if you publish it.
- **Landmark descriptions and translations** in `pipeline/landmarks.py` were written for this project and are covered by the MIT licence along with the code.

This is a plain-language summary, not legal advice.
