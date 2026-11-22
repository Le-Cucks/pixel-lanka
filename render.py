"""Render a fetched Overture area as one isometric pixel-art PNG."""

import argparse
import hashlib
import math
from pathlib import Path

import duckdb
import numpy as np
from PIL import Image, ImageDraw
import shapely
from shapely import STRtree, wkb
from shapely.affinity import translate
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from fetch_overture import AREAS

C = math.sqrt(0.5)
ZK = 0.82  # screen height per metre of elevation, relative to ground scale
FLOOR = 3.2
SHADOW = (-0.55, 0.12)  # ground offset per metre of height; sun from the east-north-east


def hexc(h):
    return tuple(int(h[i : i + 2], 16) for i in (1, 3, 5))


def mul(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c)


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rnd(key, salt=""):
    return int(hashlib.md5(f"{key}{salt}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def pick(seq, key, salt=""):
    return seq[int(rnd(key, salt) * len(seq)) % len(seq)]


P = {k: hexc(v) for k, v in {
    "bg": "#201e1c", "ocean": "#2b6a8f", "wave": "#5d97b8", "land": "#b3aa96",
    "grass": "#7aa356", "park": "#679646", "beach": "#e6d3a1", "lake": "#3a7ea6",
    "pool": "#5fc4d8", "road": "#5f5d5a", "major": "#514f4c", "curb": "#8c877b",
    "foot": "#cbbd9c", "ballast": "#8a7b6a", "rail": "#3b3530", "trunk": "#5a4030",
    "tree0": "#2f5e2e", "tree1": "#44803a", "tree2": "#6aa84f", "outline": "#2a2724",
    "dash": "#e8e2cf",
}.items()}

WALLS = [hexc(h) for h in ("#ece5d3", "#f3f0e7", "#e8c9a0", "#dcbab1", "#c9d8c0",
                           "#e8d790", "#c0d0da", "#d8d0c4", "#e3b98f")]
ROOFS_FLAT = [hexc(h) for h in ("#aaa69d", "#bbb5a9", "#949088", "#c4bfb3")]
ROOFS_TILE = [hexc(h) for h in ("#b4553a", "#c06a43", "#a84a35")]
TALL_WALLS = [hexc(h) for h in ("#a3b6c2", "#cfd3cf", "#b9c4c9", "#8fa7b6")]

GROUND = {
    ("land", "land"): "land", ("land", "island"): "land", ("grass", "grass"): "grass",
    ("grass", "grassland"): "grass", ("sand", "beach"): "beach", ("shrub", "scrub"): "park",
    ("tree", "tree"): "park",
}
LANDUSE_GREEN = {"grass", "park", "garden", "pitch", "playground", "recreation_ground",
                 "village_green", "cemetery", "golf_course"}
ROAD_W = {"motorway": 14, "trunk": 12, "primary": 10, "secondary": 9, "tertiary": 8,
          "residential": 6, "unclassified": 6, "living_street": 5, "service": 4,
          "pedestrian": 4, "footway": 2, "path": 2, "steps": 2, "cycleway": 2}
MAJOR = {"motorway", "trunk", "primary", "secondary"}
FOOT = {"pedestrian", "footway", "path", "steps", "cycleway"}


def polys(g):
    if isinstance(g, Polygon):
        return [] if g.is_empty else [g]
    if isinstance(g, (MultiPolygon, GeometryCollection)):
        return [p for sub in g.geoms for p in polys(sub)]
    return []


class Frame:
    """Local metre grid (east, north) centred on the area's bbox."""

    def __init__(self, bbox, px):
        xmin, ymin, xmax, ymax = bbox
        self.lon0, self.lat0 = (xmin + xmax) / 2, (ymin + ymax) / 2
        self.mx = 111320 * math.cos(math.radians(self.lat0))
        self.my = 110574.0
        self.px = px
        self.clip = box(*self.en(xmin, ymin), *self.en(xmax, ymax))

    def en(self, lon, lat):
        return (lon - self.lon0) * self.mx, (lat - self.lat0) * self.my

    def to_m(self, g):
        return shapely.transform(g, lambda a: (a - [self.lon0, self.lat0]) * [self.mx, self.my])

    def ring(self, coords, z=0.0):
        return [self.xy(c[0], c[1], z) for c in coords]


class Iso(Frame):
    def __init__(self, bbox, px, max_h):
        super().__init__(bbox, px)
        self.ox = self.oy = 0
        pts = [self.xy(x, y) for x, y in self.clip.exterior.coords]
        margin = 16
        self.ox = min(p[0] for p in pts) - margin
        self.oy = min(p[1] for p in pts) - max_h * ZK * px - margin
        self.w = round(max(p[0] for p in pts) - self.ox + margin)
        self.h = round(max(p[1] for p in pts) - self.oy + margin)

    def xy(self, e, n, z=0.0):
        return ((e - n) * C * self.px - self.ox,
                (-(e + n) * C * 0.5 - z * ZK) * self.px - self.oy)


class TopDown(Frame):
    def __init__(self, bbox, px, clip=None):
        super().__init__(bbox, px)
        if clip is not None:
            self.clip = clip
        self.x0, self.y0, self.x1, self.y1 = self.clip.bounds
        self.w = math.ceil((self.x1 - self.x0) * px)
        self.h = math.ceil((self.y1 - self.y0) * px)

    def xy(self, e, n, z=0.0):
        return (e - self.x0) * self.px, (self.y1 - n) * self.px


def load(con, area, layer):
    cur = con.execute(
        f"SELECT * EXCLUDE geometry, ST_AsWKB(geometry) AS g FROM 'data/{area}/{layer}.parquet'")
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        d["g"] = wkb.loads(bytes(d["g"]))
        yield d


def fill(img, iso, geoms, color):
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    for p in (p for g in geoms for p in polys(g)):
        d.polygon(iso.ring(p.exterior.coords), fill=255)
        for hole in p.interiors:
            d.polygon(iso.ring(hole.coords), fill=0)
    img.paste(color, (0, 0), mask)
    return mask


def building_height(b, poly):
    if b["height"]:
        return float(b["height"])
    if b["num_floors"]:
        return b["num_floors"] * FLOOR + 1
    a, r = poly.area, rnd(b["id"], "h")
    for limit, lo, span in ((50, 4, 2), (200, 6, 6), (1000, 8, 10), (5000, 10, 14)):
        if a < limit:
            return lo + span * r
    return 12 + 12 * r


def building_style(b, poly, h):
    key = b["id"]
    if h >= 35:
        wall = pick(TALL_WALLS, key)
        return dict(wall=wall, roof=hexc("#c9c7c0"), win=hexc("#4f6f84"), glint=hexc("#dce9f0"))
    wall = pick(WALLS, key)
    tiled = poly.area < 400 and h < 10 and rnd(key, "t") < 0.55
    roof = pick(ROOFS_TILE if tiled else ROOFS_FLAT, key, "r")
    return dict(wall=wall, roof=roof, win=mul(wall, 0.5), glint=None, tiled=tiled)


def draw_building(d, iso, poly, h, s):
    poly = orient(poly, 1.0)
    ring = list(poly.exterior.coords)
    walls = []
    for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:]):
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        nx, ny = dy / L, -dx / L
        if nx + ny >= 0:
            continue
        walls.append(((x1 + x2 + y1 + y2) * C / 2, x1, y1, x2, y2, nx, ny, L))
    walls.sort(reverse=True)

    for _, x1, y1, x2, y2, nx, ny, L in walls:
        t = ((nx - ny) * C + 1) / 2
        col = mix(mul(s["wall"], 0.66), s["wall"], t)
        d.polygon([iso.xy(x1, y1), iso.xy(x2, y2), iso.xy(x2, y2, h), iso.xy(x1, y1, h)], fill=col)
        if h < 5 or L < 2.5:
            continue
        win = mix(mul(s["win"], 0.8), s["win"], t)
        n = int(L / 2.6)
        half = 0.6 / L
        for k in range(int((h - 1) / FLOOR)):
            z0 = k * FLOOR + 1.0
            for i in range(n):
                a = (i + 0.5) / n
                ax, ay = x1 + (x2 - x1) * (a - half), y1 + (y2 - y1) * (a - half)
                bx, by = x1 + (x2 - x1) * (a + half), y1 + (y2 - y1) * (a + half)
                c = s["glint"] if s["glint"] and rnd(f"{x1}{k}{i}") < 0.08 else win
                d.polygon([iso.xy(ax, ay, z0), iso.xy(bx, by, z0),
                           iso.xy(bx, by, z0 + 1.4), iso.xy(ax, ay, z0 + 1.4)], fill=c)

    roof = iso.ring(ring, h)
    d.polygon(roof, fill=mul(s["roof"], 0.82))
    for p in polys(poly.buffer(-0.9, join_style=2)):
        d.polygon(iso.ring(p.exterior.coords, h), fill=s["roof"])
        if s.get("tiled"):
            c = p.centroid
            d.line([iso.xy(c.x - 1.5, c.y + 1.5, h), iso.xy(c.x + 1.5, c.y - 1.5, h)],
                   fill=mul(s["roof"], 1.15))
    d.polygon(roof, outline=P["outline"])


def draw_tree(d, iso, e, n, key):
    r = 2.2 + rnd(key) * 2.0
    bx, by = iso.xy(e, n)
    d.rectangle([bx - 1, by - 2.5 * ZK * iso.px, bx, by], fill=P["trunk"])
    cx, cy = iso.xy(e, n, 2.0 + r)
    rx, ry = r * iso.px, r * iso.px * 0.9
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=P["tree0"])
    d.ellipse([cx - rx * 0.85, cy - ry, cx + rx * 0.6, cy + ry * 0.55], fill=P["tree1"])
    d.ellipse([cx - rx * 0.5, cy - ry * 0.8, cx + rx * 0.05, cy - ry * 0.2], fill=P["tree2"])


class GroundLayers:
    """Ground features loaded once in metres, with spatial indexes for drawing any sub-area."""

    ORDER = ("land", "beach", "grass", "park", "lake", "foot", "curb", "road", "major", "ballast")

    def __init__(self, con, area, frame):
        clip = frame.clip
        L = {k: [] for k in (*self.ORDER, "pool", "rail")}
        for f in load(con, area, "land"):
            key = GROUND.get((f["subtype"], f["class"]))
            if key:
                L[key].append(frame.to_m(f["g"]).intersection(clip))
        for f in load(con, area, "land_use"):
            if f["class"] in LANDUSE_GREEN:
                L["grass"].append(frame.to_m(f["g"]).intersection(clip))
        for f in load(con, area, "water"):
            if f["class"] not in ("ocean", "sea"):
                key = "pool" if f["class"] == "swimming_pool" else "lake"
                L[key].append(frame.to_m(f["g"]).intersection(clip))
        for f in load(con, area, "roads"):
            g = frame.to_m(f["g"]).intersection(clip)
            if g.is_empty:
                continue
            if f["subtype"] == "rail":
                L["rail"].append(g)
                L["ballast"].append(g.buffer(2.2, 4))
                continue
            w = ROAD_W.get(f["class"])
            if not w:
                continue
            if f["class"] in FOOT:
                L["foot"].append(g.buffer(w / 2, 4))
            else:
                L["curb"].append(g.buffer(w / 2 + 1, 4))
                L["major" if f["class"] in MAJOR else "road"].append(g.buffer(w / 2, 4))
        self.layers = {k: [g for g in v if not g.is_empty] for k, v in L.items()}
        self.trees = {k: STRtree(v) for k, v in self.layers.items()}

    def get(self, key, clip):
        geoms = self.layers[key]
        return [geoms[i].intersection(clip) for i in self.trees[key].query(clip)]


def draw_ground(img, proj, ground):
    """Ocean, land cover, water, roads and rail inside proj.clip, through any Frame projection."""
    clip = proj.clip
    fill(img, proj, [clip], P["ocean"])
    ocean = np.array(img)
    for key in GroundLayers.ORDER:
        fill(img, proj, ground.get(key, clip), P[key])
    d = ImageDraw.Draw(img)
    for r in ground.get("rail", clip):
        for line in getattr(r, "geoms", [r]):
            if line.geom_type != "LineString":
                continue
            for off in (-0.75, 0.75):
                o = line.offset_curve(off)
                for part in getattr(o, "geoms", [o]):
                    if len(part.coords) > 1:
                        d.line(proj.ring(part.coords), fill=P["rail"])
    fill(img, proj, ground.get("pool", clip), P["pool"])

    arr = np.array(img)
    sea = (ocean == P["ocean"]).all(-1) & (arr == P["ocean"]).all(-1)
    rng = np.random.default_rng(7)
    waves = sea & (rng.random(sea.shape) < 0.0015)
    for dx in range(3):
        arr[:, dx:][waves[:, : arr.shape[1] - dx]] = P["wave"]
    return Image.fromarray(arr)


def render(area, px):
    con = duckdb.connect()
    con.execute("LOAD spatial")
    tmp = Iso(AREAS[area], px, 0)

    buildings = []
    for b in load(con, area, "buildings"):
        g = tmp.to_m(b["g"])
        if not tmp.clip.contains(g.centroid):
            continue
        for p in polys(g):
            h = building_height(b, p)
            buildings.append((p, h, building_style(b, p, h)))
    iso = Iso(AREAS[area], px, max(h for _, h, _ in buildings))
    clip = iso.clip

    img = draw_ground(Image.new("RGB", (iso.w, iso.h), P["bg"]), iso, GroundLayers(con, area, iso))

    shadows = []
    for p, h, _ in buildings:
        sh = min(h, 90)
        moved = translate(p, SHADOW[0] * sh, SHADOW[1] * sh)
        shadows.append(unary_union([p, moved]).convex_hull if len(p.exterior.coords) < 12
                       else unary_union([p, moved]))
    mask = np.array(fill(Image.new("L", img.size, 0), iso, shadows, 255)) > 0
    arr = np.array(img)
    arr[mask] = (arr[mask] * np.array([0.66, 0.68, 0.76])).astype(np.uint8)

    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)

    items = [((p.centroid.x + p.centroid.y) * C, 0, p, h, s) for p, h, s in buildings]
    for f in load(con, area, "land"):
        if f["class"] == "tree" and f["g"].geom_type == "Point":
            g = iso.to_m(f["g"])
            if clip.contains(g):
                items.append(((g.x + g.y) * C, 1, g, f["id"], None))
    items.sort(key=lambda t: -t[0])
    for _, kind, g, a, s in items:
        if kind == 0:
            draw_building(d, iso, g, a, s)
        else:
            draw_tree(d, iso, g.x, g.y, a)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("area", choices=AREAS)
    ap.add_argument("--px", type=float, default=2.0, help="pixels per metre")
    args = ap.parse_args()
    img = render(args.area, args.px)
    out = Path("out")
    out.mkdir(exist_ok=True)
    path = out / f"{args.area}.png"
    img.save(path, optimize=True)
    print(path, img.size)


if __name__ == "__main__":
    main()
