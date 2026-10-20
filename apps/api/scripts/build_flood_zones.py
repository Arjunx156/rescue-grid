"""Model the December 2015 Chennai flood extent from OSM hydrography.

Depth bands are buffered around the corridors that flooded worst in 2015: the
Adyar after the Chembarambakkam release, the southern marshes (Pallikaranai,
Velachery, Madipakkam) and the Buckingham Canal. Illustrative for replay and
training, not an official flood map; a real event loads Bhuvan or Copernicus EMS
polygons through the admin page instead.

    uv run python scripts/build_flood_zones.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3] / "data"
OUT = ROOT / "replay" / "chennai-2015" / "flood_zones.geojson"
LAT0 = 13.0
M_PER_DEG_LAT = 110_600.0
M_PER_DEG_LNG = 107_800.0  # at 13 N
BBOX = box(79.98, 12.82, 80.33, 13.22)

# (zone name, source features by name prefix, (inner band m, depth), (outer band m, depth))
ZONES = [
    (
        "Adyar river overflow",
        ("Adyar River", "Chembrampakkam Surplus to Adayar", "Adyar Creek"),
        (450, 2.0),
        (1100, 1.0),
    ),
    (
        "Southern marshes",
        (
            "Pallikaranai Marsh",
            "Pallikaranai Sadhuppunilam",
            "Velachery Lake",
            "Madipakkam Lake",
            "Narayanapuram Lake",
            "Pallikaranai Anai Lake",
        ),
        (700, 1.4),
        (1500, 0.7),
    ),
    ("Buckingham Canal, OMR", ("Buckingham Canal", "Buckingham Kaalvaai", "Okkiyam Maduvu"), (400, 1.1), (800, 0.6)),
    (
        "Western canals",
        ("Virugambakkam Canal", "Mambalam Canal", "Otteri Nullah", "Veerangal Canal", "Otteri Lake", "Porur Lake"),
        (300, 0.8),
        (600, 0.4),
    ),
]


# a local equirectangular projection: buffers in metres without a CRS library
_SCALE = np.array([M_PER_DEG_LNG, M_PER_DEG_LAT])
_SHIFT = np.array([0.0, LAT0])


def to_m(g: BaseGeometry) -> BaseGeometry:
    return shapely.transform(g, lambda c: (c - _SHIFT) * _SCALE)


def to_deg(g: BaseGeometry) -> BaseGeometry:
    return shapely.transform(g, lambda c: c / _SCALE + _SHIFT)


def main() -> None:
    water = json.loads((ROOT / "geo" / "water.geojson").read_text(encoding="utf-8"))
    features = []
    for name, sources, (inner_m, inner_depth), (outer_m, outer_depth) in ZONES:
        geoms = [
            to_m(shape(f["geometry"]))
            for f in water["features"]
            if (f["properties"].get("name") or "").startswith(sources)
        ]
        if not geoms:
            raise SystemExit(f"no OSM features for {name}")
        src = unary_union(geoms)
        inner = src.buffer(inner_m, resolution=8)
        outer = src.buffer(outer_m, resolution=8).difference(inner)
        for band, geom, depth in (("deep", inner, inner_depth), ("shallow", outer, outer_depth)):
            geom = to_deg(geom.simplify(40)).intersection(BBOX)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "name": f"{name} ({band})",
                        "depth_m": depth,
                        "source": "Modeled from OSM hydrography for the Dec 2015 replay (illustrative)",
                    },
                    "geometry": mapping(geom),
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    print(f"{len(features)} zones -> {OUT.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
