"""Curated landmark cards: snap each to Overture data, render a thumbnail, write landmarks.json.

site/public/tiles/landmarks.json   [{id, name, si, ta, blurb, aliases, lon, lat, thumb}]
site/public/tiles/landmarks/<id>.webp
"""

import json
import math

from fetch_overture import AREAS
from tiles import MAPS, OUT, Source, W, init_worker, make_iso, render_region

# (id, name, Sinhala, Tamil, approx lon, approx lat, name pattern to snap to, aliases, blurb)
LANDMARKS = [
    ("lotus-tower", "Lotus Tower", "නෙළුම් කුළුණ", "தாமரைக் கோபுரம்", 79.8585, 6.9271, "%Lotus Tower%",
     ["Nelum Kuluna"], "South Asia's tallest self-supported tower, 350 m, with an observation deck in its lotus bud."),
    ("gangaramaya", "Gangaramaya Temple", "ගංගාරාමය", "கங்காராமய", 79.8566, 6.9167, "Gangarama%Temple",
     ["Gangaramaya", "Gangarama"], "One of Colombo's most important Buddhist temples, beside Beira Lake."),
    ("galle-face", "Galle Face Green", "ගාලු මුවදොර පිට්ටනිය", "காலி முகத்திடல்", 79.8457, 6.9236, "Galle Face Green%",
     ["Galle Face"], "Colombo's seafront promenade, busy with kites and food stalls at sunset."),
    ("independence-hall", "Independence Memorial Hall", "නිදහස් සමරු ශාලාව", "சுதந்திர நினைவு மண்டபம்", 79.8676, 6.9040,
     "Independence%Hall%", ["Independence Square"], "Built to commemorate Sri Lanka's independence in 1948."),
    ("red-mosque", "Jami Ul-Alfar Mosque", "රතු පල්ලිය", "சிவப்பு பள்ளிவாசல்", 79.8530, 6.9384, "%Alfar%",
     ["Red Mosque"], "Pettah's red-and-white striped mosque, completed in 1909."),
    ("kelaniya", "Kelaniya Raja Maha Vihara", "කැළණි රජ මහා විහාරය", "களனி ராஜ மகா விகாரை", 79.9187, 6.9530, "Kelaniya%Vihar%",
     ["Kelaniya Temple"], "An ancient temple on the Kelani River, believed to have been visited by the Buddha."),
    ("temple-of-the-tooth", "Temple of the Tooth", "ශ්‍රී දළදා මාළිගාව", "தலதா மாளிகை", 80.6413, 7.2936, "%Tooth%",
     ["Sri Dalada Maligawa", "Dalada Maligawa"], "Kandy's royal temple, home of the sacred tooth relic of the Buddha."),
    ("sigiriya", "Sigiriya", "සීගිරිය", "சிகிரியா", 80.7603, 7.9570, "Sigiriya%",
     ["Lion Rock", "Sigiri"], "A 5th-century rock fortress rising 200 m above the plains, ringed by water gardens and a moat."),
    ("dambulla", "Dambulla Cave Temple", "දඹුල්ල ලෙන් විහාරය", "தம்புள்ளை குகைக் கோயில்", 80.6492, 7.8567, "Dambulla%",
     ["Golden Temple", "Rangiri Dambulla"], "Five painted cave shrines filled with Buddha statues, used for over 2,000 years."),
    ("ruwanwelisaya", "Ruwanwelisaya", "රුවන්වැලිසෑය", "ருவன்வெலிசாய", 80.3964, 8.3500, "Ruwanweli%",
     ["Anuradhapura"], "The great white stupa of Anuradhapura, built by King Dutugamunu around 140 BC."),
    ("mihintale", "Mihintale", "මිහින්තලේ", "மிகிந்தலை", 80.5106, 8.3509, "Mihintale%",
     [], "The mountain where Buddhism was introduced to Sri Lanka in the 3rd century BC."),
    ("polonnaruwa", "Gal Vihara, Polonnaruwa", "ගල් විහාරය", "கல் விகாரை", 81.0011, 7.9659, "Gal Vihar%",
     ["Polonnaruwa"], "Four Buddha statues carved into one granite face in the 12th-century capital."),
    ("galle-fort", "Galle Fort", "ගාලු කොටුව", "காலி கோட்டை", 80.2170, 6.0269, "Galle Fort%",
     ["Galle"], "A walled 17th-century Dutch fort town on the southern coast, a UNESCO World Heritage Site."),
    ("sri-pada", "Sri Pada", "ශ්‍රී පාදය", "சிவனொளிபாத மலை", 80.4994, 6.8096, "%Pada%",
     ["Adam's Peak", "Samanala Kanda"], "A 2,243 m sacred mountain climbed by pilgrims of every faith overnight to see the sunrise."),
    ("nine-arch-bridge", "Nine Arch Bridge", "ආරුක්කු නවයේ පාලම", "ஒன்பது வளைவுப் பாலம்", 81.0608, 6.8768, "Nine Arch%",
     ["Ella", "Demodara Bridge"], "A colonial-era stone railway viaduct in the tea hills near Ella."),
    ("gregory-lake", "Gregory Lake", "ග්‍රෙගරි වැව", "கிரெகரி ஏரி", 80.7737, 6.9583, "Gregory%",
     ["Nuwara Eliya"], "The lake at the heart of Nuwara Eliya, Sri Lanka's cool hill-country town."),
    ("jaffna-fort", "Jaffna Fort", "යාපනය බලකොටුව", "யாழ்ப்பாணக் கோட்டை", 80.0080, 9.6615, "Jaffna Fort%",
     ["Jaffna"], "A star-shaped fort first built by the Portuguese in 1618 and rebuilt by the Dutch."),
    ("nallur", "Nallur Kandaswamy Kovil", "නල්ලූර් කන්දසාමි කෝවිල", "நல்லூர் கந்தசுவாமி கோவில்", 80.0294, 9.6745, "%Nallur%",
     ["Nallur"], "Jaffna's great Hindu temple to Lord Murugan, famed for its 25-day summer festival."),
    ("koneswaram", "Koneswaram Temple", "කෝනේශ්වරම් කෝවිල", "கோணேஸ்வரம்", 81.2453, 8.5833, "Kone%",
     ["Trincomalee"], "A clifftop Hindu temple on Swami Rock above Trincomalee's harbour."),
]

SNAP_RADIUS = 2500  # metres
THUMB = (300, 190)
THUMB_Z = {"lotus-tower": 262}  # frame tall landmarks on their top instead of their base


def snap(src, iso, lon, lat, pattern):
    """Nearest named place or building matching the pattern, if it is close to the approximate position."""
    best = None
    for table, geom in (("places", "geometry"), ("buildings", "ST_Centroid(geometry)")):
        for name, x, y in src.con.execute(
                f"SELECT name, ST_X({geom}), ST_Y({geom}) FROM {table} WHERE name ILIKE ? "
                f"AND ST_Intersects(geometry, ST_MakeEnvelope(?, ?, ?, ?))",
                [pattern, lon - 0.03, lat - 0.03, lon + 0.03, lat + 0.03]).fetchall():
            d = math.dist(iso.en(lon, lat), iso.en(x, y))
            if d < SNAP_RADIUS and (best is None or d < best[0]):
                best = (d, name, x, y)
    return best


def detail_map(lon, lat):
    """Most detailed map whose area covers the point."""
    inside = [n for n, c in MAPS.items() if AREAS[c["area"]][0] <= lon <= AREAS[c["area"]][2]
              and AREAS[c["area"]][1] <= lat <= AREAS[c["area"]][3]]
    return max(inside, key=lambda n: MAPS[n]["px"])


def thumbnail(lon, lat, path, z=0.0):
    name = detail_map(lon, lat)
    if W.get("name") != name:
        iso = make_iso(MAPS[name])
        init_worker(name, Source(MAPS[name]["area"]).featured(iso))
    iso = W["iso"]
    x, y = iso.xy(*iso.en(lon, lat), z)
    w, h = THUMB
    render_region(round(x - w / 2), round(y - h * (0.5 if z else 0.62)), w, h).save(path, format="WEBP", lossless=True)


def main():
    cfg = MAPS["island"]
    iso = make_iso(cfg)
    src = Source(cfg["area"])
    thumbs = OUT / "landmarks"
    thumbs.mkdir(parents=True, exist_ok=True)
    out = []
    for lid, name, si, ta, lon, lat, pattern, aliases, blurb in LANDMARKS:
        hit = snap(src, iso, lon, lat, pattern)
        if hit:
            d, matched, lon, lat = hit
            print(f"{lid:22} snapped to {matched!r} ({d:.0f} m away)")
        else:
            print(f"{lid:22} NOT FOUND in data, using curated position")
        thumbnail(lon, lat, thumbs / f"{lid}.webp", THUMB_Z.get(lid, 0.0))
        out.append(dict(id=lid, name=name, si=si, ta=ta, blurb=blurb, aliases=aliases,
                        lon=round(lon, 6), lat=round(lat, 6), thumb=f"landmarks/{lid}.webp"))
    (OUT / "landmarks.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(out)} landmarks written")


if __name__ == "__main__":
    main()
