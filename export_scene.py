"""Export an area for the 3D web viewer as streamable chunks.

web/data/<area>/
  manifest.json          bounds, chunk grid, featured landmarks
  overview.png           whole area top-down with roofs baked in (far-away layer)
  chunks/<i>_<j>.json    buildings and trees whose centroid falls in the chunk
  chunks/<i>_<j>.png     ground texture for the chunk
"""

import argparse
import json
import math
import shutil
from pathlib import Path

import duckdb
from PIL import Image, ImageDraw
from shapely.geometry import box
from shapely.geometry.polygon import orient

from fetch_overture import AREAS
from render import (P, GroundLayers, TopDown, building_height, building_style, draw_ground, load,
                    mul, polys, rnd)

FEATURED = {"Colombo Lotus Tower": "lotus"}
CHUNK = 500
OVERVIEW_MAX = 4096


def hexs(c):
    return "#%02x%02x%02x" % c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("area", choices=AREAS)
    ap.add_argument("--px", type=float, default=1.6, help="chunk ground texture pixels per metre")
    args = ap.parse_args()
    bbox = AREAS[args.area]

    con = duckdb.connect()
    con.execute("LOAD spatial")
    frame = TopDown(bbox, 1.0)
    x0, y0, x1, y1 = frame.clip.bounds
    nx, ny = math.ceil((x1 - x0) / CHUNK), math.ceil((y1 - y0) / CHUNK)
    out = Path("web/data") / args.area
    if out.exists():
        shutil.rmtree(out)
    (out / "chunks").mkdir(parents=True)

    def cell(x, y):
        return min(int((x - x0) // CHUNK), nx - 1), min(int((y - y0) // CHUNK), ny - 1)

    raw, featured = [], []
    for b in load(con, args.area, "buildings"):
        g = frame.to_m(b["g"])
        if not frame.clip.contains(g.centroid):
            continue
        if b["name"] in FEATURED:
            c = g.centroid
            featured.append(dict(kind=FEATURED[b["name"]], name=b["name"], x=round(c.x, 1),
                                 y=round(c.y, 1), r=round(math.sqrt(g.area / math.pi), 1)))
            continue
        raw.append((b, g))

    chunks = {}
    overview_roofs = []
    for b, g in raw:
        c = g.centroid
        if any(math.dist((c.x, c.y), (f["x"], f["y"])) < max(f["r"], 28) + 4 for f in featured):
            continue
        for p in polys(g):
            h = building_height(b, p)
            s = building_style(b, p, h)
            p = orient(p.simplify(0.25), 1.0)
            if p.is_empty or p.area < 4:
                continue
            pts = [v for x, y in p.exterior.coords[:-1] for v in (round(x, 1), round(y, 1))]
            chunks.setdefault(cell(c.x, c.y), {"buildings": [], "trees": []})["buildings"].append(
                dict(p=pts, h=round(h, 1), w=hexs(s["wall"]), r=hexs(s["roof"]), t=int(h >= 35),
                     s=round(rnd(b["id"], "s"), 3)))
            overview_roofs.append((p, h, s["roof"]))

    for f in load(con, args.area, "land"):
        if f["class"] == "tree" and f["g"].geom_type == "Point":
            g = frame.to_m(f["g"])
            if frame.clip.contains(g):
                chunks.setdefault(cell(g.x, g.y), {"buildings": [], "trees": []})["trees"] += [
                    round(g.x, 1), round(g.y, 1), round(2.2 + rnd(f["id"]) * 2.0, 1)]

    ground = GroundLayers(frame, lambda layer: load(con, args.area, layer))
    written = []
    for i in range(nx):
        for j in range(ny):
            clip = box(x0 + i * CHUNK, y0 + j * CHUNK,
                       min(x0 + (i + 1) * CHUNK, x1), min(y0 + (j + 1) * CHUNK, y1))
            data = chunks.get((i, j))
            if not data and not len(ground.trees["land"].query(clip, predicate="intersects")):
                continue
            proj = TopDown(bbox, args.px, clip=clip)
            draw_ground(Image.new("RGB", (proj.w, proj.h)), proj, ground).save(
                out / "chunks" / f"{i}_{j}.png", optimize=True)
            payload = dict(bounds=[round(v, 1) for v in clip.bounds], **(data or {"buildings": [], "trees": []}))
            (out / "chunks" / f"{i}_{j}.json").write_text(json.dumps(payload, separators=(",", ":")))
            written.append([i, j])

    opx = OVERVIEW_MAX / max(x1 - x0, y1 - y0)
    oproj = TopDown(bbox, opx)
    ov = draw_ground(Image.new("RGB", (oproj.w, oproj.h)), oproj, ground)
    d = ImageDraw.Draw(ov)
    for p, h, roof in sorted(overview_roofs, key=lambda t: t[1]):
        ring = oproj.ring(p.exterior.coords)
        sh = min(h, 60) * 0.5
        d.polygon([(x - sh * opx, y + sh * 0.3 * opx) for x, y in ring], fill=mul(P["land"], 0.7))
        d.polygon(ring, fill=roof)
    ov.save(out / "overview.png", optimize=True)

    manifest = dict(bounds=[round(v, 1) for v in (x0, y0, x1, y1)], chunk=CHUNK, nx=nx, ny=ny,
                    chunks=written, featured=featured, ocean=hexs(P["ocean"]),
                    overview=dict(file="overview.png", size=list(ov.size)))
    (out / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
    n = sum(len(c["buildings"]) for c in chunks.values())
    print(f"{n} buildings in {len(written)} chunks ({nx}x{ny} grid), overview {ov.size}, featured={featured}")


if __name__ == "__main__":
    main()
