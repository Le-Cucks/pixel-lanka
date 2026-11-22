"""Render an area as one huge isometric pixel-art image, tiled as a Deep Zoom (DZI) pyramid.

site/public/tiles/<area>/
  <area>.dzi, <area>_files/<level>/<col>_<row>.webp
  meta.json     projection parameters so the site can map lat/lon <-> image pixels
  places.json   [name, category, x, y, score] search index in image pixels, best first
site/app/opengraph-image.png  social preview crop around the Lotus Tower
"""

import argparse
import copy
import json
import math
import shutil
import time
from pathlib import Path

import duckdb
import numpy as np
from PIL import Image, ImageDraw
from shapely.affinity import translate
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from fetch_overture import AREAS
from render import (C, P, SHADOW, ZK, GroundLayers, Iso, building_height, building_style, draw_building,
                    draw_ground, draw_tree, fill, hexc, load, mix, mul, polys)

TILE = 256
REGION = 4096
FEATURED = {"Colombo Lotus Tower": "lotus"}
LOTUS_TOP = 352
BUD = [(7, 226), (14, 236), (21, 248), (23, 258), (22, 266), (17, 277), (9, 287), (3, 293), (0.5, 297)]


def unproject(iso, sx, sy):
    a = (sx + iso.ox) / (C * iso.px)
    b = -(sy + iso.oy) / (0.5 * C * iso.px)
    return (a + b) / 2, (b - a) / 2


def screen_box(iso, xs, ys, z_top=0.0, pad=2):
    xs, ys = np.asarray(xs), np.asarray(ys)
    sx = (xs - ys) * C * iso.px - iso.ox
    sy = -(xs + ys) * C * 0.5 * iso.px - iso.oy
    return (sx.min() - pad, sy.min() - z_top * ZK * iso.px - pad, sx.max() + pad, sy.max() + pad)


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
    d.line([iso.xy(cx, cy, 297), iso.xy(cx, cy, LOTUS_TOP)], fill=hexc("#e2e2e2"), width=max(2, round(px)))
    d.line([iso.xy(cx, cy, 297), iso.xy(cx, cy, 330)], fill=hexc("#bdbdbd"), width=max(3, round(px * 1.6)))


class Scene:
    def __init__(self, area, px):
        con = duckdb.connect()
        con.execute("LOAD spatial")
        tmp = Iso(AREAS[area], px, 0)
        featured, raw = [], []
        for b in load(con, area, "buildings"):
            g = tmp.to_m(b["g"])
            if not tmp.clip.contains(g.centroid):
                continue
            if b["name"] in FEATURED:
                featured.append(dict(kind=FEATURED[b["name"]], name=b["name"], x=g.centroid.x, y=g.centroid.y,
                                     r=math.sqrt(g.area / math.pi)))
            else:
                raw.append((b, g))

        buildings = []
        for b, g in raw:
            c = g.centroid
            if any(math.dist((c.x, c.y), (f["x"], f["y"])) < max(f["r"], 30) + 4 for f in featured):
                continue
            for p in polys(g):
                h = building_height(b, p)
                buildings.append((p, h, building_style(b, p, h)))
        max_h = max([h for _, h, _ in buildings] + [LOTUS_TOP if featured else 0])
        self.iso = iso = Iso(AREAS[area], px, max_h)
        self.featured = featured

        items, boxes, shadows, sboxes = [], [], [], []
        for p, h, s in buildings:
            xs, ys = p.exterior.coords.xy
            items.append(((p.centroid.x + p.centroid.y) * C, 0, p, h, s))
            boxes.append(screen_box(iso, xs, ys, h))
            sh = min(h, 90)
            moved = translate(p, SHADOW[0] * sh, SHADOW[1] * sh)
            u = unary_union([p, moved])
            shadow = u.convex_hull if len(p.exterior.coords) < 12 else u
            shadows.append(shadow)
            bx, by = shadow.exterior.coords.xy if shadow.geom_type == "Polygon" else shadow.convex_hull.exterior.coords.xy
            sboxes.append(screen_box(iso, bx, by))
        for f in load(con, area, "land"):
            if f["class"] == "tree" and f["g"].geom_type == "Point":
                g = iso.to_m(f["g"])
                if iso.clip.contains(g):
                    items.append(((g.x + g.y) * C, 1, g, f["id"], None))
                    boxes.append(screen_box(iso, [g.x - 5, g.x + 5], [g.y - 5, g.y + 5], 10))
        for f in featured:
            items.append(((f["x"] + f["y"]) * C, 2, Point(f["x"], f["y"]), f["kind"], None))
            boxes.append(screen_box(iso, [f["x"] - 45, f["x"] + 45], [f["y"] - 45, f["y"] + 45], LOTUS_TOP + 5))

        order = sorted(range(len(items)), key=lambda i: -items[i][0])
        self.items = [items[i] for i in order]
        self.boxes = np.array([boxes[i] for i in order])
        self.shadows = shadows
        self.sboxes = np.array(sboxes)
        self.ground = GroundLayers(con, area, iso)
        self.con, self.area = con, area

    @staticmethod
    def _hits(boxes, x0, y0, x1, y1):
        return np.nonzero((boxes[:, 2] >= x0) & (boxes[:, 0] <= x1) & (boxes[:, 3] >= y0) & (boxes[:, 1] <= y1))[0]

    def render(self, rx, ry, w, h):
        iso = self.iso
        v = copy.copy(iso)
        v.ox, v.oy, v.w, v.h = iso.ox + rx, iso.oy + ry, w, h
        corners = [unproject(iso, rx + dx, ry + dy) for dx, dy in ((-8, -8), (w + 8, -8), (w + 8, h + 8), (-8, h + 8))]
        v.clip = Polygon(corners).intersection(iso.clip)
        img = Image.new("RGB", (w, h), P["bg"])
        if v.clip.is_empty:
            return img
        img = draw_ground(img, v, self.ground)

        sel = self._hits(self.sboxes, rx, ry, rx + w, ry + h)
        if len(sel):
            mask = np.array(fill(Image.new("L", img.size, 0), v, [self.shadows[i] for i in sel], 255)) > 0
            arr = np.array(img)
            arr[mask] = (arr[mask] * np.array([0.66, 0.68, 0.76])).astype(np.uint8)
            img = Image.fromarray(arr)

        d = ImageDraw.Draw(img)
        for i in self._hits(self.boxes, rx, ry, rx + w, ry + h):
            _, kind, g, a, s = self.items[i]
            if kind == 0:
                draw_building(d, v, g, a, s)
            elif kind == 1:
                draw_tree(d, v, g.x, g.y, a)
            else:
                draw_lotus(d, v, g.x, g.y)
        return img


def level_dims(w, h, levels):
    return [(math.ceil(w / 2 ** (levels - 1 - lv)), math.ceil(h / 2 ** (levels - 1 - lv))) for lv in range(levels)]


def save_tile(img, path):
    img.save(path, format="WEBP", lossless=True, method=4)


def build_pyramid(files, W, H):
    levels = math.ceil(math.log2(max(W, H))) + 1
    dims = level_dims(W, H, levels)
    for lv in range(levels - 2, -1, -1):
        lw, lh = dims[lv]
        cw, ch = dims[lv + 1]
        (files / str(lv)).mkdir()
        for col in range(math.ceil(lw / TILE)):
            for row in range(math.ceil(lh / TILE)):
                x0, y0 = col * TILE, row * TILE
                tw, th = min(TILE, lw - x0), min(TILE, lh - y0)
                canvas = Image.new("RGB", (TILE * 2, TILE * 2), P["bg"])
                for dc in (0, 1):
                    for dr in (0, 1):
                        cc, cr = col * 2 + dc, row * 2 + dr
                        if cc * TILE < cw and cr * TILE < ch:
                            canvas.paste(Image.open(files / str(lv + 1) / f"{cc}_{cr}.webp"), (dc * TILE, dr * TILE))
                cwid, chei = min(tw * 2, cw - x0 * 2), min(th * 2, ch - y0 * 2)
                save_tile(canvas.crop((0, 0, cwid, chei)).resize((tw, th), Image.BOX), files / str(lv) / f"{col}_{row}.webp")
    return levels


def places_index(scene):
    iso, con, area = scene.iso, scene.con, scene.area
    seen, out = set(), []

    def add(name, cat, g, score):
        if not name or not iso.clip.contains(g):
            return
        key = (name.lower(), round(g.x / 50), round(g.y / 50))
        if key in seen:
            return
        seen.add(key)
        x, y = iso.xy(g.x, g.y)
        out.append([name, cat or "", round(x), round(y), round(score, 2)])

    for b in load(con, area, "buildings"):
        if b["name"]:
            add(b["name"], b["class"] or "building", iso.to_m(b["g"]).centroid, 1.0)
    for p in load(con, area, "places"):
        if (p["confidence"] or 0) >= 0.6:
            add(p["name"], (p["category"] or "").replace("_", " "), iso.to_m(p["g"]), p["confidence"])
    for r in load(con, area, "roads"):
        if r["name"] and r["subtype"] == "road":
            add(r["name"], "street", iso.to_m(r["g"]).interpolate(0.5, normalized=True), 0.5)
    out.sort(key=lambda t: (-t[4], t[0].lower()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("area", choices=AREAS)
    ap.add_argument("--px", type=float, default=2.0, help="image pixels per metre")
    args = ap.parse_args()
    t0 = time.time()

    scene = Scene(args.area, args.px)
    iso = scene.iso
    W, H = iso.w, iso.h
    out = Path("site/public/tiles") / args.area
    if out.exists():
        shutil.rmtree(out)
    files = out / f"{args.area}_files"
    levels = math.ceil(math.log2(max(W, H))) + 1
    top = files / str(levels - 1)
    top.mkdir(parents=True)
    print(f"scene ready in {time.time() - t0:.0f}s: {W}x{H}px, {len(scene.items)} items, {levels} levels")

    for rx in range(0, W, REGION):
        for ry in range(0, H, REGION):
            w, h = min(REGION, W - rx), min(REGION, H - ry)
            img = scene.render(rx, ry, w, h)
            for tx in range(0, w, TILE):
                for ty in range(0, h, TILE):
                    save_tile(img.crop((tx, ty, min(tx + TILE, w), min(ty + TILE, h))),
                              top / f"{(rx + tx) // TILE}_{(ry + ty) // TILE}.webp")
            print(f"  region {rx // REGION},{ry // REGION} done ({time.time() - t0:.0f}s)")

    build_pyramid(files, W, H)
    (out / f"{args.area}.dzi").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        f'TileSize="{TILE}" Overlap="0" Format="webp"><Size Width="{W}" Height="{H}"/></Image>\n')

    lotus = next((f for f in scene.featured if f["kind"] == "lotus"), None)
    meta = dict(dzi=f"{args.area}.dzi", width=W, height=H, px=iso.px, ox=iso.ox, oy=iso.oy,
                lon0=iso.lon0, lat0=iso.lat0, mx=iso.mx, my=iso.my, bbox=AREAS[args.area])
    if lotus:
        lx, ly = iso.xy(lotus["x"], lotus["y"], 150)
        meta["start"] = dict(x=round(lx), y=round(ly))
        sx, sy = iso.xy(lotus["x"], lotus["y"], 176)
        scene.render(round(sx) - 600, round(sy) - 315, 1200, 630).save("site/app/opengraph-image.png", optimize=True)
    (out / "meta.json").write_text(json.dumps(meta))
    places = places_index(scene)
    (out / "places.json").write_text(json.dumps(places, ensure_ascii=False, separators=(",", ":")))
    print(f"done in {time.time() - t0:.0f}s: {len(places)} searchable places")


if __name__ == "__main__":
    main()
