"""Download Overture Maps layers for a bounding box into data/<area>/*.parquet."""

import argparse
from pathlib import Path

import duckdb

RELEASE = "2026-11-18.0"
BASE = f"s3://overturemaps-us-west-2/release/{RELEASE}"

AREAS = {
    "colombo-fort": (79.838, 6.924, 79.861, 6.944),
    "colombo": (79.835, 6.860, 79.900, 6.985),
    "sri-lanka": (79.50, 5.88, 81.92, 9.86),
}

LAYERS = {
    "buildings": (
        "theme=buildings/type=building",
        "id, height, num_floors, class, subtype, roof_shape, names.primary AS name, geometry",
    ),
    "building_parts": (
        "theme=buildings/type=building_part",
        "id, building_id, height, min_height, num_floors, geometry",
    ),
    "roads": (
        "theme=transportation/type=segment",
        "id, subtype, class, names.primary AS name, geometry",
    ),
    "water": ("theme=base/type=water", "id, subtype, class, geometry"),
    "land_use": ("theme=base/type=land_use", "id, subtype, class, geometry"),
    "land": ("theme=base/type=land", "id, subtype, class, geometry"),
    "land_cover": (
        "theme=base/type=land_cover",
        "id, subtype, cartography.min_zoom AS min_zoom, cartography.max_zoom AS max_zoom, geometry",
    ),
    "places": (
        "theme=places/type=place",
        "id, names.primary AS name, basic_category AS category, brand.names.primary AS brand, confidence, geometry",
    ),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("area", choices=AREAS)
    args = ap.parse_args()
    xmin, ymin, xmax, ymax = AREAS[args.area]
    out = Path("data") / args.area
    out.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.sql("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    for name, (path, cols) in LAYERS.items():
        if (out / f"{name}.parquet").exists():
            continue
        con.execute(f"""
            COPY (
                SELECT {cols} FROM read_parquet('{BASE}/{path}/*', hive_partitioning=1)
                WHERE bbox.xmin < {xmax} AND bbox.xmax > {xmin}
                  AND bbox.ymin < {ymax} AND bbox.ymax > {ymin}
            ) TO '{out / name}.parquet' (FORMAT parquet)
        """)
    for name in LAYERS:
        n = con.execute(f"SELECT count(*) FROM '{out / name}.parquet'").fetchone()[0]
        print(f"{name}: {n}")


if __name__ == "__main__":
    main()
