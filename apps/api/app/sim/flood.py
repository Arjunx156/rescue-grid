"""The December 2015 Chennai flood, simulated: the ground truth the replay is built on.

The forcing follows what was published about the event: rain peaking overnight on
1-2 December (Tambaram logged about 490 mm in a day), the Chembarambakkam reservoir
releasing up to about 29,000 cusecs (820 m3/s) into the Adyar, and breached tanks
feeding the upper Adyar. It runs on real terrain, but no gauge data calibrated it,
so it is an illustration of how that flood moved, not a hindcast.

Rescue Grid never sees this forcing. It starts from the forecast below, which, like
the forecasts and release notices of 2015, is too low and too late; the crowd's
reports have to correct it.

Writes, under data/replay/chennai-2015:
- water.npz            depth every 10 minutes for 60 hours: the truth
- forcing.json         the true forcing, and the forecast Rescue Grid starts from
- flood_zones.geojson  the modelled maximum extent in three depth bands

    uv run python -m app.sim.flood
"""

from __future__ import annotations

import json
import time

import numpy as np
import shapely
from shapely.geometry import box, mapping

from app.core.settings import get_settings
from app.services.hydro import Forcing, Grid, Model, Source

SPINUP_MIN = -720  # 6 am IST on 1 December; the replay starts at 6 pm
END_MIN = 3600
EVERY_MIN = 10
DEPTH_STEP_M = 0.025  # frames are stored as uint8 in 2.5 cm steps
SEA_LEVEL_M = 0.4  # a high tide, backing water up the Adyar mouth
BANDS = ((0.3, 0.8), (0.8, 1.5), (1.5, 99.0))
MIN_ZONE_CELLS = 4

# minutes from 6 pm IST, 1 December 2015
TRUTH = Forcing(
    rain_mm_h=(
        (-720, 2),
        (-480, 4),
        (-240, 7),
        (-60, 12),
        (120, 34),
        (300, 40),
        (480, 30),
        (660, 18),
        (840, 8),
        (1080, 4),
        (1440, 2),
        (1800, 0.5),
        (2160, 0),
    ),
    sources=(
        Source(
            "Chembarambakkam reservoir release",
            13.0004,
            80.0809,
            (
                (-720, 60),
                (-240, 120),
                (0, 300),
                (300, 850),
                (900, 850),
                (1200, 600),
                (1560, 350),
                (2160, 200),
                (3600, 100),
            ),
        ),
        Source(
            "Upper Adyar tank breaches",
            12.8468,
            79.9876,
            ((-720, 20), (0, 80), (360, 350), (900, 300), (1440, 120), (2160, 50)),
        ),
    ),
)

# what a control room would have believed: the rain forecast too low, the release notices late and small
FORECAST = Forcing(
    rain_mm_h=((-720, 2), (-240, 6), (120, 20), (480, 18), (840, 8), (1440, 2), (2160, 0)),
    sources=(
        Source(
            "Chembarambakkam reservoir release",
            13.0004,
            80.0809,
            ((-720, 50), (0, 150), (480, 450), (1080, 450), (1560, 250), (2160, 150), (3600, 80)),
        ),
        Source("Upper Adyar tank breaches", 12.8468, 79.9876, ((-720, 20), (360, 120), (1440, 60), (2160, 30))),
    ),
)


def snap_to_channel(grid: Grid, forcing: Forcing) -> Forcing:
    sources = []
    for src in forcing.sources:
        lat, lng = grid.nearest_channel(src.lat, src.lng, within_m=10_000)
        sources.append(Source(src.name, round(lat, 5), round(lng, 5), src.m3s))
    return Forcing(forcing.rain_mm_h, tuple(sources))


def zones(grid: Grid, peak: np.ndarray) -> list[dict]:
    """The maximum extent over the first 48 hours, polygonised by depth band. Rivers, lakes and sea are not zones."""
    land = grid.water == 0
    features = []
    for lo, hi in BANDS:
        sel = land & (peak >= lo) & (peak < hi)
        cells = []
        for i, j in zip(*np.nonzero(sel), strict=True):
            north, west = grid.north - i * grid.dlat, grid.west + j * grid.dlng
            cells.append(box(west, north - grid.dlat, west + grid.dlng, north))
        if not cells:
            continue
        # pockets of a cell or two are mostly roofs and trees the surface model kept; drop them
        parts = shapely.get_parts(shapely.union_all(cells))
        geom = shapely.union_all([g for g in parts if g.area >= MIN_ZONE_CELLS * grid.dlat * grid.dlng])
        geom = geom.simplify(grid.dlng * 0.3)
        label = f"over {lo:g} m" if hi > 50 else f"{lo:g} to {hi:g} m"
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": f"Modelled flood, {label}",
                    "depth_m": round(float(np.median(peak[sel])), 1),
                    "source": "Rescue Grid flood model on Copernicus GLO-30 terrain, Dec 2015 replay (illustrative)",
                },
                "geometry": mapping(geom),
            }
        )
    return features


def main() -> None:
    data = get_settings().data_dir
    out = data / "replay" / "chennai-2015"
    grid = Grid.load(data / "geo" / "terrain.npz")
    truth, forecast = snap_to_channel(grid, TRUTH), snap_to_channel(grid, FORECAST)
    model = Model(grid, sea_level_m=SEA_LEVEL_M, minute=SPINUP_MIN)
    started = time.perf_counter()
    model.run_to(0, truth)
    count = (END_MIN // EVERY_MIN) + 1
    frames = np.zeros((count, *grid.shape), dtype=np.uint8)
    for k in range(count):
        if k:
            model.run_to(k * EVERY_MIN, truth)
        frames[k] = np.clip(np.round(model.h / DEPTH_STEP_M), 0, 255).astype(np.uint8)
    peak = frames[: 48 * 60 // EVERY_MIN + 1].max(axis=0) * DEPTH_STEP_M

    np.savez_compressed(out / "water.npz", frames=frames, every_min=EVERY_MIN, step_m=DEPTH_STEP_M)
    (out / "forcing.json").write_text(
        json.dumps(
            {
                "spinup_min": SPINUP_MIN,
                "sea_level_m": SEA_LEVEL_M,
                "truth": truth.to_dict(),
                "forecast": forecast.to_dict(),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    fc = {"type": "FeatureCollection", "features": zones(grid, peak)}
    (out / "flood_zones.geojson").write_text(json.dumps(fc), encoding="utf-8")
    land = grid.water == 0
    print(
        f"{count} frames in {time.perf_counter() - started:.1f}s; peak land depth {peak[land].max():.2f} m; "
        + ", ".join(f"{lo:g}+ m: {int((land & (peak >= lo)).sum())} cells" for lo, _ in BANDS)
    )


if __name__ == "__main__":
    main()
