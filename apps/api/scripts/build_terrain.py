# pyright: reportMissingImports=false
# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy>=2", "shapely>=2.1", "tifffile>=2025.1", "imagecodecs>=2025.3"]
# ///
"""Ground elevation for the flood model: Copernicus GLO-30 resampled to a 200 m grid.

GLO-30 is a surface model, so roofs and trees stand above the street. Each 200 m
cell takes the 10th percentile of its ~45 source pixels, which lands near the
ground between buildings. Rivers and canals from OSM are then burned 2 m into
that surface and forced to fall monotonically downstream (OSM draws waterways in
the direction they flow), so water finds the channels the way it does in the city.

    uv run scripts/build_terrain.py

Elevation: Copernicus DEM GLO-30, (c) DLR e.V. 2010-2014 and (c) Airbus Defence
and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA.
"""

from __future__ import annotations

import itertools
import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import shapely
import tifffile
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[3] / "data"
OUT = ROOT / "geo" / "terrain.npz"
CACHE = ROOT / ".cache" / "dem"
BOUNDS = (79.98, 12.82, 80.33, 13.22)  # west, south, east, north: the replay's operational area
CELL_M = 200.0
M_PER_DEG_LAT = 110_600.0
M_PER_DEG_LNG = 107_800.0  # at 13 N, as everywhere else in the code base
BURN_M = 2.0
TILE_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif"

# water classes in the mask
CHANNEL, LAKE, SEA = 1, 2, 3


def tile_name(lat: int, lng: int) -> str:
    return f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lng:03d}_00_DEM"


def fetch(lat: int, lng: int) -> Path:
    name = tile_name(lat, lng)
    path = CACHE / f"{name}.tif"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"downloading {name}")
        urllib.request.urlretrieve(TILE_URL.format(n=name), path)
    return path


def source_pixels() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(lat, lng, elevation) of every GLO-30 pixel inside the bounds."""
    west, south, east, north = BOUNDS
    lats, lngs, zs = [], [], []
    for tlat in range(math.floor(south), math.floor(north) + 1):
        for tlng in range(math.floor(west), math.floor(east) + 1):
            z = tifffile.imread(fetch(tlat, tlng)).astype(np.float32)
            rows, cols = z.shape
            # pixel centres; the tile spans [tlat, tlat+1] x [tlng, tlng+1], north row first
            plat = tlat + 1 - (np.arange(rows) + 0.5) / rows
            plng = tlng + (np.arange(cols) + 0.5) / cols
            r = (plat >= south) & (plat < north)
            c = (plng >= west) & (plng < east)
            sub = z[np.ix_(r, c)]
            glat, glng = np.meshgrid(plat[r], plng[c], indexing="ij")
            lats.append(glat.ravel())
            lngs.append(glng.ravel())
            zs.append(sub.ravel())
    return np.concatenate(lats), np.concatenate(lngs), np.concatenate(zs)


def grid_shape() -> tuple[int, int, float, float]:
    west, south, east, north = BOUNDS
    dlat, dlng = CELL_M / M_PER_DEG_LAT, CELL_M / M_PER_DEG_LNG
    return math.ceil((north - south) / dlat), math.ceil((east - west) / dlng), dlat, dlng


def resample(lat: np.ndarray, lng: np.ndarray, z: np.ndarray) -> np.ndarray:
    """10th percentile of the source pixels in each cell: the ground between the buildings."""
    west, _, _, north = BOUNDS
    ny, nx, dlat, dlng = grid_shape()
    i = np.clip(((north - lat) / dlat).astype(int), 0, ny - 1)
    j = np.clip(((lng - west) / dlng).astype(int), 0, nx - 1)
    cell = i * nx + j
    order = np.lexsort((z, cell))
    cell, z = cell[order], z[order]
    starts = np.searchsorted(cell, np.arange(ny * nx))
    ends = np.searchsorted(cell, np.arange(ny * nx), side="right")
    counts = ends - starts
    pick = starts + np.floor(0.1 * np.maximum(counts - 1, 0)).astype(int)
    out = np.where(counts > 0, z[np.minimum(pick, len(z) - 1)], np.nan)
    return out.reshape(ny, nx).astype(np.float32)


def cell_centres() -> tuple[np.ndarray, np.ndarray]:
    west, _, _, north = BOUNDS
    ny, nx, dlat, dlng = grid_shape()
    lat = north - (np.arange(ny) + 0.5) * dlat
    lng = west + (np.arange(nx) + 0.5) * dlng
    return np.meshgrid(lat, lng, indexing="ij")


def to_cell(lat: float, lng: float) -> tuple[int, int]:
    west, _, _, north = BOUNDS
    ny, nx, dlat, dlng = grid_shape()
    return min(ny - 1, max(0, int((north - lat) / dlat))), min(nx - 1, max(0, int((lng - west) / dlng)))


def densify(coords: list[list[float]], step_deg: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in itertools.pairwise(coords):
        n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / step_deg))
        out += [(y1 + (y2 - y1) * k / n, x1 + (x2 - x1) * k / n) for k in range(n)]
    out.append((coords[-1][1], coords[-1][0]))
    return out


def burn_channels(z: np.ndarray, mask: np.ndarray, water: dict) -> int:
    """Lower river and canal cells and make each waterway fall monotonically downstream."""
    ground = z.copy()  # burn depth is measured from the original surface, however many lines overlap
    burned = 0
    for f in water["features"]:
        g = f["geometry"]
        if g["type"] != "LineString" or f["properties"].get("kind") not in ("river", "canal", "stream"):
            continue
        cells = []
        for lat, lng in densify(g["coordinates"], CELL_M / M_PER_DEG_LNG / 3):
            c = to_cell(lat, lng)
            if not cells or cells[-1] != c:
                cells.append(c)
        floor = math.inf
        ny, nx = z.shape
        for i, j in cells:
            if mask[i, j] == SEA:
                break
            if i in (0, ny - 1) or j in (0, nx - 1):
                continue  # lines clipped to the area run along its edge; the edge is a wall anyway
            target = min(float(ground[i, j]) - BURN_M, floor)
            z[i, j] = min(float(z[i, j]), target)
            floor = float(z[i, j])
            mask[i, j] = CHANNEL
            burned += 1
    return burned


def sea_mask(z: np.ndarray) -> np.ndarray:
    """Cells at or below 0.5 m that connect to the eastern edge: the Bay of Bengal."""
    low = z <= 0.5
    sea = np.zeros_like(low)
    sea[:, -1] = low[:, -1]
    while True:
        grown = sea.copy()
        grown[:, :-1] |= sea[:, 1:]
        grown[:, 1:] |= sea[:, :-1]
        grown[:-1, :] |= sea[1:, :]
        grown[1:, :] |= sea[:-1, :]
        grown &= low
        if (grown == sea).all():
            return sea
        sea = grown


def main() -> None:
    lat, lng, zsrc = source_pixels()
    z = resample(lat, lng, zsrc)
    ny, nx, _, _ = grid_shape()
    if np.isnan(z).any():
        raise SystemExit("terrain has empty cells; check the tile coverage")
    mask = np.zeros((ny, nx), dtype=np.uint8)
    mask[sea_mask(z)] = SEA
    # quarry pits near Pallavaram read as -60 m holes; in the wet season they are full of water
    z[mask != SEA] = np.maximum(z[mask != SEA], -2.0)
    water = json.loads((ROOT / "geo" / "water.geojson").read_text(encoding="utf-8"))
    glat, glng = cell_centres()
    lakes = [
        shape(f["geometry"])
        for f in water["features"]
        if f["geometry"]["type"] in ("Polygon", "MultiPolygon")
        and f["properties"].get("kind") in ("lake", "reservoir", "water", "pond", "basin", "wetland")
    ]
    if lakes:
        inside = shapely.contains_xy(shapely.union_all(lakes), glng, glat)
        mask[inside & (mask != SEA)] = LAKE
    burned = burn_channels(z, mask, water)
    np.savez_compressed(
        OUT,
        z=z.astype(np.float32),
        water=mask,
        bounds=np.array(BOUNDS),
        cell_m=np.array(CELL_M),
    )
    land = z[mask != SEA]
    print(
        f"{ny}x{nx} cells at {CELL_M:.0f} m -> {OUT.relative_to(ROOT.parent)}; "
        f"land {land.min():.1f} to {land.max():.1f} m (median {np.median(land):.1f}); "
        f"sea {int((mask == SEA).sum())}, lakes {int((mask == LAKE).sum())}, channel cells burned {burned}"
    )


if __name__ == "__main__":
    main()
