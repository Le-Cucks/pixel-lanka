"""Projection, overlay alignment and edge fade. These need no downloaded data, so they run in CI."""

import math

import numpy as np
import pytest
from PIL import Image

from fetch_overture import AREAS
from render import P
from tiles import FADE_LAND, FADE_SEA, MAPS, edge_distance, fade_edges, level_dims, make_iso, unproject, with_alpha

ISLAND = make_iso(MAPS["island"])
COLOMBO = make_iso(MAPS["colombo"])
POINTS = [(79.8585, 6.9271), (80.6413, 7.2936), (80.0080, 9.6615), (81.2453, 8.5833), (80.2170, 6.0269)]


@pytest.mark.parametrize("lon,lat", POINTS)
def test_lonlat_round_trip(lon, lat):
    e, n = ISLAND.en(lon, lat)
    assert ISLAND.to_ll(e, n) == pytest.approx((lon, lat), abs=1e-9)


@pytest.mark.parametrize("lon,lat", POINTS)
def test_screen_round_trip(lon, lat):
    e, n = ISLAND.en(lon, lat)
    assert unproject(ISLAND, *ISLAND.xy(e, n)) == pytest.approx((e, n), abs=1e-6)


def test_maps_share_one_frame():
    # overlays only line up with the base map if every map projects from the same origin
    assert (COLOMBO.lon0, COLOMBO.lat0, COLOMBO.mx, COLOMBO.my) == (ISLAND.lon0, ISLAND.lat0, ISLAND.mx, ISLAND.my)


@pytest.mark.parametrize("lon,lat", [(79.8585, 6.9271), (79.86, 6.90), (79.84, 6.97)])
def test_overlay_aligns_with_base(lon, lat):
    """Mirror of site/lib/geo.ts placement(): a Colombo pixel lands on the same spot of the island image."""
    k = ISLAND.px / COLOMBO.px
    e, n = ISLAND.en(lon, lat)
    cx, cy = COLOMBO.xy(e, n)
    bx, by = ISLAND.xy(e, n)
    assert (cx * k + (COLOMBO.ox * k - ISLAND.ox), cy * k + (COLOMBO.oy * k - ISLAND.oy)) == pytest.approx((bx, by), abs=1e-6)


def test_colombo_is_inside_the_island_frame():
    cx0, cy0, cx1, cy1 = AREAS[MAPS["colombo"]["area"]]
    fx0, fy0, fx1, fy1 = AREAS[MAPS["island"]["area"]]
    assert fx0 <= cx0 < cx1 <= fx1 and fy0 <= cy0 < cy1 <= fy1


def test_edge_distance_at_frame_and_centre():
    x0, y0, x1, y1 = ISLAND.clip.bounds
    sx, sy = ISLAND.xy(x0, (y0 + y1) / 2)  # middle of the west edge
    assert edge_distance(ISLAND, sx - 0.5, sy - 0.5, 1, 1)[0, 0] == pytest.approx(0, abs=5)
    cx, cy = ISLAND.xy((x0 + x1) / 2, (y0 + y1) / 2)
    assert edge_distance(ISLAND, cx, cy, 1, 1)[0, 0] == pytest.approx(min(x1 - x0, y1 - y0) / 2, rel=1e-3)


def sea(w=64, h=64):
    return Image.new("RGB", (w, h), P["ocean"])


def test_fade_leaves_the_interior_alone():
    x0, y0, x1, y1 = ISLAND.clip.bounds
    cx, cy = ISLAND.xy((x0 + x1) / 2, (y0 + y1) / 2)
    img = sea()
    assert np.array_equal(np.asarray(fade_edges(ISLAND, img, round(cx), round(cy))), np.asarray(img))


def test_fade_reaches_background_at_the_edge_and_keeps_land_crisper():
    x0, y0, x1, y1 = ISLAND.clip.bounds
    sx, sy = ISLAND.xy(x0 + FADE_LAND / 2, (y0 + y1) / 2)  # inside the frame, within both fade bands
    rx, ry = round(sx) - 1, round(sy) - 1
    water = np.asarray(fade_edges(ISLAND, sea(3, 3), rx, ry))[1, 1].astype(int)
    land = np.asarray(fade_edges(ISLAND, Image.new("RGB", (3, 3), P["forest"]), rx, ry))[1, 1].astype(int)
    bg = np.array(P["bg"])

    def remaining(c, original):
        return np.abs(c - bg).sum() / np.abs(np.array(original) - bg).sum()

    t_sea = 1 - (1 - (FADE_LAND / 2) / FADE_SEA) ** 2
    t_land = 1 - (1 - 0.5) ** 2
    assert remaining(water, P["ocean"]) == pytest.approx(t_sea, abs=0.03)
    assert remaining(land, P["forest"]) == pytest.approx(t_land, abs=0.03)


def test_overlay_alpha_marks_only_drawn_pixels():
    img = Image.new("RGB", (4, 1), P["bg"])
    img.putpixel((2, 0), P["road"])
    assert list(np.asarray(with_alpha(img))[0, :, 3]) == [0, 0, 255, 0]


def test_level_dims_halve_down_to_one_pixel():
    w, h = 1000, 300
    levels = math.ceil(math.log2(max(w, h))) + 1
    dims = level_dims(w, h, levels)
    assert dims[-1] == (w, h) and dims[0] == (1, 1)
    assert all(math.ceil(a[0] / 2) == b[0] for b, a in zip(dims, dims[1:]))
