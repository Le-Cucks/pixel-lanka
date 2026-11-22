"""Export an area for the 3D web viewer: web/data/<area>/{scene.json, ground.png}."""

import argparse
import json
import math
from pathlib import Path

import duckdb
from PIL import Image
from shapely.geometry.polygon import orient

from fetch_overture import AREAS
from render import P, TopDown, building_height, building_style, draw_ground, load, polys, rnd

FEATURED = {"Colombo Lotus Tower": "lotus"}


def hexs(c):
    return "#%02x%02x%02x" % c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("area", choices=AREAS)
    ap.add_argument("--px", type=float, default=1.6, help="ground texture pixels per metre")
    args = ap.parse_args()

    con = duckdb.connect()
    con.execute("LOAD spatial")
    proj = TopDown(AREAS[args.area], args.px)
    out = Path("web/data") / args.area
    out.mkdir(parents=True, exist_ok=True)

    ground = draw_ground(Image.new("RGB", (proj.w, proj.h), P["bg"]), proj, con, args.area)
    ground.save(out / "ground.png", optimize=True)

    raw, featured = [], []
    for b in load(con, args.area, "buildings"):
        g = proj.to_m(b["g"])
        if not proj.clip.contains(g.centroid):
            continue
        if b["name"] in FEATURED:
            c = g.centroid
            featured.append(dict(kind=FEATURED[b["name"]], name=b["name"], x=round(c.x, 1),
                                 y=round(c.y, 1), r=round(math.sqrt(g.area / math.pi), 1)))
            continue
        raw.append((b, g))

    buildings = []
    for b, g in raw:
        if any(math.dist((g.centroid.x, g.centroid.y), (f["x"], f["y"])) < max(f["r"], 28) + 4
               for f in featured):
            continue
        for p in polys(g):
            h = building_height(b, p)
            s = building_style(b, p, h)
            p = orient(p.simplify(0.25), 1.0)
            if p.is_empty or p.area < 4:
                continue
            pts = [v for x, y in p.exterior.coords[:-1] for v in (round(x, 1), round(y, 1))]
            buildings.append(dict(p=pts, h=round(h, 1), w=hexs(s["wall"]), r=hexs(s["roof"]),
                                  t=int(h >= 35), s=round(rnd(b["id"], "s"), 3)))

    trees = []
    for f in load(con, args.area, "land"):
        if f["class"] == "tree" and f["g"].geom_type == "Point":
            g = proj.to_m(f["g"])
            if proj.clip.contains(g):
                trees += [round(g.x, 1), round(g.y, 1), round(2.2 + rnd(f["id"]) * 2.0, 1)]

    scene = dict(bounds=[round(v, 1) for v in proj.clip.bounds], buildings=buildings,
                 trees=trees, featured=featured, ocean=hexs(P["ocean"]))
    (out / "scene.json").write_text(json.dumps(scene, separators=(",", ":")))
    print(f"{len(buildings)} buildings, {len(trees) // 3} trees, featured={featured}, ground={ground.size}")


if __name__ == "__main__":
    main()
