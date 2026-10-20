"""Build the Chennai gazetteer and water layer from a Geofabrik OSM extract.

    curl -LO https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf
    uv run --with osmium python scripts/build_geo.py southern-zone-latest.osm.pbf

Writes data/geo/landmarks.json and data/geo/water.geojson (committed).
Data (c) OpenStreetMap contributors, ODbL 1.0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import osmium  # pyright: ignore[reportMissingImports] (installed with --with osmium)
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping

SOUTH, WEST, NORTH, EAST = 12.82, 79.98, 13.22, 80.33
OUT = Path(__file__).resolve().parents[3] / "data" / "geo"

LANDMARK_TAGS = {
    "amenity": {
        "place_of_worship",
        "school",
        "college",
        "university",
        "hospital",
        "clinic",
        "bus_station",
        "marketplace",
        "police",
        "fire_station",
        "community_centre",
        "cinema",
        "bank",
        "fuel",
        "post_office",
        "townhall",
        "library",
        "kindergarten",
        "marriage_hall",
        "pharmacy",
        "restaurant",
    },
    "railway": {"station", "halt"},
    "public_transport": {"station"},
    "shop": {"mall", "supermarket", "department_store"},
    "leisure": {"park", "stadium", "playground", "sports_centre"},
    "tourism": {"attraction", "hotel", "museum"},
    "highway": {"bus_stop"},
    "building": {"apartments", "residential", "hospital", "school", "temple", "church", "mosque"},
    "place": {"suburb", "neighbourhood", "quarter", "locality", "village", "town", "hamlet"},
    "man_made": {"water_tower", "bridge"},
    "bridge": {"yes"},
}
STREET_TYPES = {"primary", "secondary", "tertiary", "residential", "trunk", "unclassified", "living_street"}
ALIAS_KEYS = ("name:ta", "name:en", "alt_name", "old_name", "short_name", "official_name")


def inside(lat: float, lon: float) -> bool:
    return SOUTH <= lat <= NORTH and WEST <= lon <= EAST


def category(tags: osmium.osm.TagList) -> str | None:
    for key, values in LANDMARK_TAGS.items():
        value = tags.get(key)
        if value in values:
            return f"{key}:{value}"
    if tags.get("highway") in STREET_TYPES:
        return "street"
    # many suburbs (Mudichur, Varadarajapuram) exist only as boundaries or housing areas
    if tags.get("boundary") == "administrative" and tags.get("admin_level") in ("8", "9", "10", "11"):
        return "place:admin"
    if tags.get("landuse") == "residential":
        return "place:residential"
    return None


def aliases(tags: osmium.osm.TagList, name: str) -> list[str]:
    out = {tags.get(k, "").strip() for k in ALIAS_KEYS}
    out.discard("")
    out.discard(name)
    return sorted(out)


def main(pbf: str) -> None:
    landmarks: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    water: list[dict] = []

    def add(name: str, cat: str, lat: float, lon: float, tags: osmium.osm.TagList) -> None:
        # streets come back as many short ways; keep one point per ~500 m
        key = (name.lower(), round(lat * 200), round(lon * 200))
        if key in seen or not inside(lat, lon):
            return
        seen.add(key)
        landmarks.append(
            {"name": name, "aliases": aliases(tags, name), "category": cat, "lat": round(lat, 6), "lng": round(lon, 6)}
        )

    proc = osmium.FileProcessor(pbf).with_locations("sparse_mem_array").with_areas()
    for obj in proc:
        tags = obj.tags
        name = tags.get("name", "").strip()
        if obj.is_node():
            if name and (cat := category(tags)) and obj.location.valid():
                add(name, cat, obj.location.lat, obj.location.lon, tags)
        elif obj.is_way():
            kind = tags.get("waterway")
            try:
                pts = [(n.location.lon, n.location.lat) for n in obj.nodes if n.location.valid()]
            except osmium.InvalidLocationError:
                continue
            if len(pts) < 2 or not any(inside(lat, lon) for lon, lat in pts):
                continue
            if kind in ("river", "canal", "stream", "drain") and (name or kind in ("river", "canal")):
                line = LineString(pts).simplify(0.00015)
                water.append(
                    {"type": "Feature", "properties": {"name": name or None, "kind": kind}, "geometry": mapping(line)}
                )
            elif name and (cat := category(tags)):
                if len(pts) > 3 and pts[0] == pts[-1]:
                    c = Polygon(pts).representative_point()
                    lon, lat = c.x, c.y
                else:
                    lon, lat = pts[len(pts) // 2]
                add(name, cat, lat, lon, tags)
        elif obj.is_area():
            nat = tags.get("natural")
            kind = nat if nat in ("water", "wetland") else None
            if tags.get("landuse") == "reservoir" or tags.get("water") in ("lake", "reservoir", "pond", "river"):
                kind = "water"
            if not kind and not (name and category(tags) and not obj.from_way()):
                continue  # named ways were already added above
            polys = []
            for outer in obj.outer_rings():
                ring = [(n.lon, n.lat) for n in outer]
                if len(ring) >= 4:
                    holes = [[(n.lon, n.lat) for n in inner] for inner in obj.inner_rings(outer)]
                    polys.append(Polygon(ring, [h for h in holes if len(h) >= 4]))
            if not polys:
                continue
            geom = MultiPolygon(polys).buffer(0)
            c = geom.centroid
            if not kind:
                add(name, category(tags) or "other", c.y, c.x, tags)
                continue
            # ponds under ~2 ha are noise at city scale
            if not inside(c.y, c.x) or geom.area < 2e-6:
                continue
            water.append(
                {
                    "type": "Feature",
                    "properties": {"name": name or None, "kind": tags.get("water") or kind},
                    "geometry": mapping(geom.simplify(0.0001)),
                }
            )

    OUT.mkdir(parents=True, exist_ok=True)
    landmarks.sort(key=lambda r: (r["category"], r["name"]))
    (OUT / "landmarks.json").write_text(
        json.dumps(landmarks, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    fc = {"type": "FeatureCollection", "features": water, "attribution": "(c) OpenStreetMap contributors, ODbL 1.0"}
    (OUT / "water.geojson").write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"landmarks {len(landmarks)}  water {len(water)}")


if __name__ == "__main__":
    main(sys.argv[1])
