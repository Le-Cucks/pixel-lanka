"""Render maps as huge isometric pixel-art images, tiled as Deep Zoom (DZI) pyramids.

All maps share one projection frame (the Sri Lanka bbox), so a detailed city map is an exact,
scaled sub-rectangle of the island map and the site can stack it on top as an overlay.

Each 4096px region is rendered independently in a worker process, querying only the features
it needs through an R-tree index, so memory stays flat no matter how big the map is.

site/public/tiles/
  world.json                  projection frame + every built map's placement
  <map>/<map>.dzi, <map>/<map>_files/<level>/<col>_<row>.webp
  <map>/places.json           [name, category, lon, lat, score] search index, best first
site/app/opengraph-image.png  social preview crop around the Lotus Tower
"""

import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import time
from multiprocessing import get_context
from pathlib import Path

import duckdb
import numpy as np
from PIL import Image, ImageDraw
from shapely import wkb
from shapely.affinity import translate
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from fetch_overture import AREAS, LAYERS
from render import (C, P, SHADOW, ZK, GroundLayers, Iso, building_height, building_style, draw_building,
                    draw_ground, draw_tree, fill, hexc, mix, mul, polys)

TILE = 256
REGION = 4096
MAX_H = 360
FETCH_MARGIN = 900  # metres: tall buildings south of a region still poke up into it
FRAME = AREAS["sri-lanka"]
OUT = Path("site/public/tiles")
FEATURED = {"Colombo Lotus Tower": "lotus"}
LOTUS_TOP = 352
BUD = [(7, 226), (14, 236), (21, 248), (23, 258), (22, 266), (17, 277), (9, 287), (3, 293), (0.5, 297)]

MAPS = {
    "island": dict(area="sri-lanka", px=0.5, overlay=False, min_confidence=0.8),
    "colombo": dict(area="colombo", px=2.0, overlay=True, min_confidence=0.6),
}


def packed(c):
    return (c[0] << 16) | (c[1] << 8) | c[2]


SIMPLE = np.array([packed(P["bg"]), packed(P["ocean"]), packed(P["wave"])], dtype=np.uint32)


# ---------- geometry helpers ----------

def unproject(iso, sx, sy):
    a = (sx + iso.ox) / (C * iso.px)
    b = -(sy + iso.oy) / (0.5 * C * iso.px)
    return (a + b) / 2, (b - a) / 2


def screen_box(iso, xs, ys, z_top=0.0, pad=2):
    xs, ys = np.asarray(xs), np.asarray(ys)
    sx = (xs - ys) * C * iso.px - iso.ox
    sy = -(xs + ys) * C * 0.5 * iso.px - iso.oy
    return sx.min() - pad, sy.min() - z_top * ZK * iso.px - pad, sx.max() + pad, sy.max() + pad


def overlaps(bx, w, h):
    return bx[2] >= 0 and bx[0] <= w and bx[3] >= 0 and bx[1] <= h


def make_iso(cfg):
    return Iso(AREAS[cfg["area"]], cfg["px"], MAX_H, frame=FRAME)


# ---------- Lotus Tower landmark ----------

def bud_radius(z):
    for (r0, z0), (r1, z1) in zip(BUD, BUD[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return 0.0


def draw_lotus(d, iso, cx, cy):
    px = iso.px
    draw_building(d, iso, Point(cx, cy).buffer(30, 24), 8,
                  dict(wall=hexc("#ece4d3"), roof=hexc("#cfc6b4"), win=hexc("#8a8070"), glint=None))
    for i in range(18):
        a = i / 18 * math.tau
        sx, sy = iso.xy(cx + math.cos(a) * 31, cy + math.sin(a) * 31, 9)
        d.ellipse([sx - 3 * px, sy - 2.2 * px, sx + 3 * px, sy + 1.4 * px],
                  fill=hexc("#b65a9c") if i % 2 else hexc("#9c4688"))
    draw_building(d, iso, Point(cx, cy).buffer(7, 20), 228,
                  dict(wall=hexc("#9cc7a4"), roof=hexc("#9cc7a4"), win=hexc("#9cc7a4"), glint=None, nowin=True))
    petal_lo, petal_hi = hexc("#b0508f"), hexc("#d27db4")

    def petals(front):
        for i in range(10):
            a = i / 10 * math.tau + 0.3
            ex, ey = math.cos(a), math.sin(a)
            if ((ex + ey) < 0) != front:
                continue
            base = [iso.xy(cx + math.cos(a + s) * 12, cy + math.sin(a + s) * 12, 229) for s in (-0.28, 0.28)]
            mid = [iso.xy(cx + math.cos(a + s) * 19, cy + math.sin(a + s) * 19, 243) for s in (0.2, -0.2)]
            tip = iso.xy(cx + ex * 23, cy + ey * 23, 254)
            shade = (math.cos(a) - math.sin(a)) * C * 0.5 + 0.5
            d.polygon([base[0], base[1], mid[0], tip, mid[1]], fill=mix(mul(petal_lo, 0.75), petal_hi, shade))

    petals(front=False)
    dark, mid, light = hexc("#7d2f6a"), hexc("#a8458e"), hexc("#cd6fb0")
    for z in np.arange(226, 297.5, 0.5):
        r = bud_radius(z)
        sx, sy = iso.xy(cx, cy, z)
        rx, ry = r * px, r * px * 0.5
        d.ellipse([sx - rx, sy - ry, sx + rx, sy + ry], fill=dark)
        d.ellipse([sx - rx * 0.55, sy - ry, sx + rx, sy + ry * 0.92], fill=mid)
        d.ellipse([sx + rx * 0.2, sy - ry * 0.9, sx + rx * 0.75, sy + ry * 0.5], fill=light)
    petals(front=True)
    d.line([iso.xy(cx, cy, 297), iso.xy(cx, cy, LOTUS_TOP)], fill=hexc("#e2e2e2"), width=max(1, round(px)))
    d.line([iso.xy(cx, cy, 297), iso.xy(cx, cy, 330)], fill=hexc("#bdbdbd"), width=max(1, round(px * 1.6)))


# ---------- data access ----------

def index_path(area):
    return Path(f"data/{area}/index.duckdb")


def build_index(area):
    db = index_path(area)
    if db.exists():
        return
    tmp = db.with_name("index.tmp.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute("LOAD spatial")
    for layer in LAYERS:
        src = Path(f"data/{area}/{layer}.parquet")
        if src.exists():
            con.execute(f"CREATE TABLE {layer} AS SELECT * FROM '{src}'")
            con.execute(f"CREATE INDEX {layer}_rtree ON {layer} USING RTREE (geometry)")
    con.close()
    tmp.rename(db)


class Source:
    def __init__(self, area):
        self.con = duckdb.connect(str(index_path(area)), read_only=True)
        self.con.execute("LOAD spatial")
        self.tables = {r[0] for r in self.con.execute("SELECT table_name FROM information_schema.tables").fetchall()}

    def fetch(self, layer, env):
        if layer not in self.tables:
            return
        x0, y0, x1, y1 = env
        cur = self.con.execute(
            f"SELECT * EXCLUDE geometry, ST_AsWKB(geometry) AS g FROM {layer} "
            f"WHERE ST_Intersects(geometry, ST_MakeEnvelope({x0}, {y0}, {x1}, {y1}))")
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d["g"] = wkb.loads(bytes(d["g"]))
            yield d

    def featured(self, iso):
        names = ", ".join(f"'{n}'" for n in FEATURED)
        out = []
        for name, g in self.con.execute(
                f"SELECT name, ST_AsWKB(geometry) FROM buildings WHERE name IN ({names})").fetchall():
            m = iso.to_m(wkb.loads(bytes(g)))
            if iso.clip.contains(m.centroid):
                out.append(dict(kind=FEATURED[name], name=name, x=m.centroid.x, y=m.centroid.y,
                                r=math.sqrt(m.area / math.pi)))
        return out


def env_ll(iso, bounds, margin=0.0):
    x0, y0, x1, y1 = bounds
    lo = iso.to_ll(x0 - margin, y0 - margin)
    hi = iso.to_ll(x1 + margin, y1 + margin)
    return lo[0], lo[1], hi[0], hi[1]


# ---------- region rendering (runs in workers) ----------

W = {}


def init_worker(name, featured):
    cfg = MAPS[name]
    W.update(name=name, cfg=cfg, iso=make_iso(cfg), src=Source(cfg["area"]), featured=featured)


def render_region(rx, ry, w, h):
    iso, src, featured = W["iso"], W["src"], W["featured"]
    v = copy.copy(iso)
    v.ox, v.oy, v.w, v.h = iso.ox + rx, iso.oy + ry, w, h
    region = Polygon([unproject(iso, rx + dx, ry + dy) for dx, dy in ((-8, -8), (w + 8, -8), (w + 8, h + 8), (-8, h + 8))])
    v.clip = region.intersection(iso.clip)
    img = Image.new("RGB", (w, h), P["bg"])
    if v.clip.is_empty:
        return img

    ground_env = env_ll(iso, v.clip.bounds)
    img = draw_ground(img, v, GroundLayers(v, lambda layer: src.fetch(layer, ground_env)), phase=(ry % TILE, rx % TILE))

    near = env_ll(iso, v.clip.bounds, FETCH_MARGIN)
    items, shadows = [], []
    for b in src.fetch("buildings", near):
        g = iso.to_m(b["g"])
        c = g.centroid
        if not iso.clip.contains(c):
            continue
        if any(math.dist((c.x, c.y), (f["x"], f["y"])) < max(f["r"], 30) + 4 for f in featured):
            continue
        for p in polys(g):
            h_ = building_height(b, p)
            xs, ys = p.exterior.coords.xy
            sh = min(h_, 90)
            u = unary_union([p, translate(p, SHADOW[0] * sh, SHADOW[1] * sh)])
            shadow = u.convex_hull if len(p.exterior.coords) < 12 or u.geom_type != "Polygon" else u
            if overlaps(screen_box(v, *shadow.exterior.coords.xy), w, h):
                shadows.append(shadow)
            if overlaps(screen_box(v, xs, ys, h_), w, h):
                items.append(((c.x + c.y) * C, 0, p, h_, building_style(b, p, h_)))
    for f in src.fetch("land", near):
        if f["class"] == "tree" and f["g"].geom_type == "Point":
            g = iso.to_m(f["g"])
            if iso.clip.contains(g) and overlaps(screen_box(v, [g.x], [g.y], 10, pad=12), w, h):
                items.append(((g.x + g.y) * C, 1, g, f["id"], None))
    for f in featured:
        if overlaps(screen_box(v, [f["x"] - 45, f["x"] + 45], [f["y"] - 45, f["y"] + 45], LOTUS_TOP + 5), w, h):
            items.append(((f["x"] + f["y"]) * C, 2, Point(f["x"], f["y"]), f["kind"], None))

    if shadows:
        mask = np.array(fill(Image.new("L", img.size, 0), v, shadows, 255)) > 0
        arr = np.array(img)
        arr[mask] = (arr[mask] * np.array([0.66, 0.68, 0.76])).astype(np.uint8)
        img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    for _, kind, g, a, s in sorted(items, key=lambda t: -t[0]):
        if kind == 0:
            draw_building(d, v, g, a, s)
        elif kind == 1:
            draw_tree(d, v, g.x, g.y, a)
        else:
            draw_lotus(d, v, g.x, g.y)
    return img


def with_alpha(img):
    a = np.asarray(img)
    alpha = ((a != P["bg"]).any(-1) * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([a, alpha]), "RGBA")


def link_canonical(store, key, path, make):
    canon = store / f"{key}.webp"
    if not canon.exists():
        tmp = store / f"{key}.{os.getpid()}.tmp"
        make().save(tmp, format="WEBP", lossless=True, method=4)
        os.replace(tmp, canon)
    os.link(canon, path)


def save_tile(img, path, store):
    """Write a tile; plain sea/blank tiles are stored once and hard-linked everywhere else."""
    a = np.asarray(img)
    if img.size == (TILE, TILE):
        rgb = a[..., :3].astype(np.uint32)
        if np.isin((rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2], SIMPLE).all():
            return link_canonical(store, hashlib.sha1(a.tobytes()).hexdigest(), path, lambda: img)
    img.save(path, format="WEBP", lossless=True, method=4)


def region_task(job):
    rx, ry, w, h, top, store = job
    img = render_region(rx, ry, w, h)
    if W["cfg"]["overlay"]:
        img = with_alpha(img)
    for tx in range(0, w, TILE):
        for ty in range(0, h, TILE):
            save_tile(img.crop((tx, ty, min(tx + TILE, w), min(ty + TILE, h))),
                      Path(top) / f"{(rx + tx) // TILE}_{(ry + ty) // TILE}.webp", Path(store))
    return rx, ry


# ---------- pyramid ----------

def level_dims(w, h, levels):
    return [(math.ceil(w / 2 ** (levels - 1 - lv)), math.ceil(h / 2 ** (levels - 1 - lv))) for lv in range(levels)]


def shrink(img, mode, size=(TILE, TILE)):
    if mode == "RGBA":
        return img.convert("RGBa").resize(size, Image.BOX).convert("RGBA")
    return img.resize(size, Image.BOX)


def parent_task(job):
    files, store, lv, col, dims, overlay = job
    files, store = Path(files), Path(store)
    (lw, lh), (cw, ch) = dims
    mode, bg = ("RGBA", (0, 0, 0, 0)) if overlay else ("RGB", P["bg"])
    for row in range(math.ceil(lh / TILE)):
        x0, y0 = col * TILE, row * TILE
        tw, th = min(TILE, lw - x0), min(TILE, lh - y0)
        kids = [(dc, dr, files / str(lv + 1) / f"{col * 2 + dc}_{row * 2 + dr}.webp")
                for dc in (0, 1) for dr in (0, 1)
                if (col * 2 + dc) * TILE < cw and (row * 2 + dr) * TILE < ch]
        out = files / str(lv) / f"{col}_{row}.webp"

        def compose(crop=True):
            canvas = Image.new(mode, (TILE * 2, TILE * 2), bg)
            for dc, dr, path in kids:
                canvas.paste(Image.open(path).convert(mode), (dc * TILE, dr * TILE))
            if crop:
                canvas = canvas.crop((0, 0, min(tw * 2, cw - x0 * 2), min(th * 2, ch - y0 * 2)))
            return shrink(canvas, mode, (tw, th))

        stats = [k[2].stat() for k in kids]
        if (len(kids) == 4 and (tw, th) == (TILE, TILE) and len({s.st_ino for s in stats}) == 1
                and stats[0].st_nlink > 1):
            link_canonical(store, f"parent-{stats[0].st_ino}", out, lambda: compose(crop=False))
        else:
            compose().save(out, format="WEBP", lossless=True, method=4)
    return col


def build_pyramid(pool, files, store, W_, H_, overlay):
    levels = math.ceil(math.log2(max(W_, H_))) + 1
    dims = level_dims(W_, H_, levels)
    for lv in range(levels - 2, -1, -1):
        (files / str(lv)).mkdir()
        jobs = [(str(files), str(store), lv, col, (dims[lv], dims[lv + 1]), overlay)
                for col in range(math.ceil(dims[lv][0] / TILE))]
        for _ in pool.imap_unordered(parent_task, jobs, chunksize=4):
            pass


# ---------- search index ----------

def build_places(src, cfg):
    bx0, by0, bx1, by1 = AREAS[cfg["area"]]
    inside = f"ST_Intersects(geometry, ST_MakeEnvelope({bx0}, {by0}, {bx1}, {by1}))"
    rows = [(n, c or "building", x, y, 1.0, 50.0) for n, c, x, y in src.con.execute(
        f"SELECT name, class, ST_X(ST_Centroid(geometry)), ST_Y(ST_Centroid(geometry)) FROM buildings "
        f"WHERE name IS NOT NULL AND {inside}").fetchall()]
    rows += [(n, (c or "").replace("_", " "), x, y, conf, 50.0) for n, c, x, y, conf in src.con.execute(
        f"SELECT name, category, ST_X(geometry), ST_Y(geometry), confidence FROM places "
        f"WHERE name IS NOT NULL AND confidence >= {cfg['min_confidence']} AND {inside}").fetchall()]
    rows += [(n, "street", x, y, 0.5, 1500.0) for n, x, y in src.con.execute(
        f"SELECT name, ST_X(ST_PointOnSurface(geometry)), ST_Y(ST_PointOnSurface(geometry)) FROM roads "
        f"WHERE name IS NOT NULL AND subtype = 'road' AND {inside}").fetchall()]
    mx, my = 111320 * math.cos(math.radians((by0 + by1) / 2)), 110574.0
    seen, out = set(), []
    for name, cat, lon, lat, score, cell in rows:
        key = (name.lower(), round(lon * mx / cell), round(lat * my / cell))
        if key not in seen:
            seen.add(key)
            out.append([name, cat, round(lon, 6), round(lat, 6), round(score, 2)])
    out.sort(key=lambda t: (-t[4], t[0].lower()))
    return out


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map", choices=MAPS)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    cfg = MAPS[args.map]
    t0 = time.time()

    build_index(cfg["area"])
    iso = make_iso(cfg)
    src = Source(cfg["area"])
    featured = src.featured(iso)
    W_, H_ = iso.w, iso.h
    out = OUT / args.map
    if out.exists():
        shutil.rmtree(out)
    files, store = out / f"{args.map}_files", out / "_store"
    levels = math.ceil(math.log2(max(W_, H_))) + 1
    top = files / str(levels - 1)
    top.mkdir(parents=True)
    store.mkdir()
    jobs = [(rx, ry, min(REGION, W_ - rx), min(REGION, H_ - ry), str(top), str(store))
            for ry in range(0, H_, REGION) for rx in range(0, W_, REGION)]
    print(f"{args.map}: {W_}x{H_}px, {len(jobs)} regions, {levels} levels, {args.workers} workers", flush=True)

    with get_context("spawn").Pool(args.workers, initializer=init_worker, initargs=(args.map, featured)) as pool:
        for i, _ in enumerate(pool.imap_unordered(region_task, jobs), 1):
            if i % max(1, len(jobs) // 20) == 0 or i == len(jobs):
                print(f"  regions {i}/{len(jobs)} ({time.time() - t0:.0f}s)", flush=True)
        build_pyramid(pool, files, store, W_, H_, cfg["overlay"])
    print(f"  pyramid done ({time.time() - t0:.0f}s)", flush=True)

    (out / f"{args.map}.dzi").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        f'TileSize="{TILE}" Overlap="0" Format="webp"><Size Width="{W_}" Height="{H_}"/></Image>\n')
    places = build_places(src, cfg)
    (out / "places.json").write_text(json.dumps(places, ensure_ascii=False, separators=(",", ":")))

    entry = dict(dzi=f"{args.map}/{args.map}.dzi", places=f"{args.map}/places.json", width=W_, height=H_,
                 px=iso.px, ox=iso.ox, oy=iso.oy, overlay=cfg["overlay"], bbox=AREAS[cfg["area"]])
    lotus = next((f for f in featured if f["kind"] == "lotus"), None)
    if lotus and cfg["px"] >= 1:
        init_worker(args.map, featured)
        sx, sy = iso.xy(lotus["x"], lotus["y"], 176)
        render_region(round(sx) - 600, round(sy) - 315, 1200, 630).save("site/app/opengraph-image.png", optimize=True)
        lon, lat = iso.to_ll(*unproject(iso, *iso.xy(lotus["x"], lotus["y"], 150)))
        entry["start"] = dict(lon=round(lon, 6), lat=round(lat, 6))

    world_path = OUT / "world.json"
    world = json.loads(world_path.read_text()) if world_path.exists() else {"maps": {}}
    world["frame"] = dict(lon0=iso.lon0, lat0=iso.lat0, mx=iso.mx, my=iso.my)
    world["maps"][args.map] = entry
    world_path.write_text(json.dumps(world, indent=1))
    n = sum(1 for _ in files.rglob("*.webp"))
    print(f"done in {time.time() - t0:.0f}s: {n} tiles, {len(places)} searchable places")


if __name__ == "__main__":
    main()
