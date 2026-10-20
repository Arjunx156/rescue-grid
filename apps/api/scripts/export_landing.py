"""Shrink the benchmark and the simulated flood into the landing page's static files.

    uv run python scripts/export_landing.py      (just bench runs it)

- chennai-2015.json: the side-by-side replay. Times become minutes from the start,
  coordinates four decimals, geometry simplified.
- chennai-2015-water.bin: the 3D twin. Ground height, then the flood every hour,
  one byte per 400 m cell (see "water" in the JSON for the layout).

Synthetic replay data only: no real person's details.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
OUT = ROOT / "apps" / "web" / "public" / "replay" / "chennai-2015.json"
WATER_OUT = OUT.with_name("chennai-2015-water.bin")
COARSEN = 2  # 200 m model cells -> 400 m columns
FRAME_MIN = 60
ELEV_STEP_M = 0.25
DEPTH_STEP_M = 0.025
RIVERS = (
    "Adyar River",
    "Buckingham Canal",
    "Buckingham Kaalvaai",
    "Chembrampakkam Surplus to Adayar",
    "Otteri Nullah",
    "Okkiyam Maduvu",
    "Kosasthalaiyar",
)
LAKES = ("Pallikaranai Marsh", "Chembarambakkam Lake", "Velachery Lake", "Madipakkam Lake", "Porur Lake")


def rnd(coords: object) -> object:
    if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
        return [round(coords[0], 4), round(coords[1], 4)]
    return [rnd(c) for c in coords]  # type: ignore[union-attr]


def bounds(houses: list[dict]) -> list[float]:
    """Frame the families, not the whole metro: a margin of 6% on every side."""
    lats = sorted(h["lat"] for h in houses)
    lngs = sorted(h["lng"] for h in houses)
    # ignore the outermost 1% so one stray household cannot shrink the picture
    k = max(1, len(lats) // 100)
    y1, y2, x1, x2 = lats[k], lats[-k - 1], lngs[k], lngs[-k - 1]
    my, mx = (y2 - y1) * 0.06, (x2 - x1) * 0.06
    return [round(x1 - mx, 4), round(y1 - my, 4), round(x2 + mx, 4), round(y2 + my, 4)]


def coarsen(a: np.ndarray, how: str) -> np.ndarray:
    ny, nx = (a.shape[-2] // COARSEN) * COARSEN, (a.shape[-1] // COARSEN) * COARSEN
    a = a[..., :ny, :nx].reshape(*a.shape[:-2], ny // COARSEN, COARSEN, nx // COARSEN, COARSEN)
    return a.mean(axis=(-3, -1)) if how == "mean" else a.min(axis=(-3, -1))


def export_water() -> dict:
    """Ground (lowest of each 2x2, so rivers stay rivers) then hourly mean depth, as bytes."""
    terrain = np.load(DATA / "geo" / "terrain.npz")
    flood = np.load(DATA / "replay" / "chennai-2015" / "water.npz")
    every = int(flood["every_min"])
    frames = flood["frames"][:: FRAME_MIN // every].astype(np.float32) * float(flood["step_m"])
    ground = coarsen(np.where(terrain["water"] == 3, 0.0, terrain["z"]), "min")
    sea = coarsen((terrain["water"] == 3).astype(np.float32), "mean") >= 0.5
    depth = coarsen(frames, "mean")
    depth[:, sea] = 0
    elev = np.clip(np.round(np.maximum(ground, 0) / ELEV_STEP_M), 0, 254).astype(np.uint8)
    elev[sea] = 255  # 255 marks the sea
    body = np.clip(np.round(depth / DEPTH_STEP_M), 0, 255).astype(np.uint8)
    WATER_OUT.write_bytes(elev.tobytes() + body.tobytes())
    bounds = terrain["bounds"]
    cell = float(terrain["cell_m"]) * COARSEN
    ny, nx = elev.shape
    return {
        "file": f"/replay/{WATER_OUT.name}",
        "ny": ny,
        "nx": nx,
        "west": float(bounds[0]),
        "north": float(bounds[3]),
        "dlat": cell / 110_600,
        "dlng": cell / 107_800,
        "frames": int(body.shape[0]),
        "every_min": FRAME_MIN,
        "elev_step_m": ELEV_STEP_M,
        "depth_step_m": DEPTH_STEP_M,
    }


def main() -> None:
    bench = json.loads((DATA / "replay" / "chennai-2015" / "benchmark.json").read_text(encoding="utf-8"))
    zones = json.loads((DATA / "replay" / "chennai-2015" / "flood_zones.geojson").read_text(encoding="utf-8"))
    water = json.loads((DATA / "geo" / "water.geojson").read_text(encoding="utf-8"))
    start = datetime.fromisoformat(bench["starts_at"])

    def minutes(iso: str | None) -> float | None:
        return round((datetime.fromisoformat(iso) - start).total_seconds() / 60, 1) if iso else None

    houses = bench["households"]
    index = {h["id"]: i for i, h in enumerate(houses)}
    policies = {}
    for key, p in bench["policies"].items():
        rescued: list[float | None] = [None] * len(houses)
        for hid, iso in p["outcomes"].items():
            rescued[index[hid]] = minutes(iso)
        tracks = {
            tid: [
                [minutes(s[0]), minutes(s[1]), round(s[2], 4), round(s[3], 4), round(s[4], 4), round(s[5], 4)]
                for s in segs
            ]
            for tid, segs in p["tracks"].items()
        }
        m = p["metrics"]
        policies[key] = {
            "label": p["label"],
            "rescued": rescued,
            "tracks": tracks,
            "metrics": {
                k: m[k]
                for k in (
                    "at_risk",
                    "reached_before_water",
                    "critical_total",
                    "critical_reached_3h",
                    "households_reached",
                    "people_rescued",
                    "median_minutes_to_assign_critical",
                    "median_minutes_to_rescue",
                    "wasted_trips",
                )
            },
        }
    geo = {
        "flood": [
            rnd(mapping(shape(f["geometry"]).simplify(0.002))["coordinates"])
            for f in zones["features"]
            if f["properties"]["depth_m"] >= 1.0
        ],
        "rivers": [
            rnd(mapping(shape(f["geometry"]).simplify(0.0008))["coordinates"])
            for f in water["features"]
            if (f["properties"].get("name") or "").startswith(RIVERS) and f["geometry"]["type"] == "LineString"
        ],
        "lakes": [
            rnd(mapping(shape(f["geometry"]).simplify(0.0008))["coordinates"])
            for f in water["features"]
            if (f["properties"].get("name") or "").startswith(LAKES)
            and f["geometry"]["type"] in ("Polygon", "MultiPolygon")
        ],
    }
    out = {
        "name": bench["name"],
        "starts_at": bench["starts_at"],
        "duration": minutes(bench["ends_at"]),
        "bounds": bounds(houses),
        # lat, lng, critical, first report minute, people, minute the water reached the danger line (or null)
        "houses": [
            [
                round(h["lat"], 4),
                round(h["lng"], 4),
                1 if h["critical"] else 0,
                minutes(h["first_t"]),
                h["people"],
                minutes(h.get("danger_t")),
            ]
            for h in houses
        ],
        "policies": policies,
        "comparison": bench["comparison"],
        "geo": geo,
        "water": export_water(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB), "
        f"{WATER_OUT.name} ({WATER_OUT.stat().st_size // 1024} KB)"
    )


if __name__ == "__main__":
    main()
