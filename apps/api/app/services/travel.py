"""How fast each asset moves through a flooded city, and where it cannot go.

Used for the optimiser's travel matrix and as the router of last resort, so it
must be cheap: straight-line distance, a detour factor, and a flood-aware speed.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from app.services.geocode import bearing_deg, haversine_m

SPEED_KMH = {"boat": 8.0, "truck": 16.0, "medical": 20.0, "foot": 3.5, "helicopter": 110.0}
DETOUR = {"boat": 1.2, "truck": 1.45, "medical": 1.4, "foot": 1.3, "helicopter": 1.0}
STARTUP_S = {"boat": 120, "truck": 60, "medical": 60, "foot": 0, "helicopter": 600}
# how deep each asset can drive or wade through before it must turn back
MAX_DEPTH_M = {"truck": 0.9, "medical": 0.5, "foot": 0.7, "boat": 99.0, "helicopter": 99.0}
SERVICE_BASE_S = {"boat": 600, "truck": 420, "medical": 900, "foot": 600, "helicopter": 1200}
SERVICE_PER_PERSON_S = 60

WATER_DEPTH_M = {
    "none": 0.0,
    "ankle": 0.15,
    "knee": 0.5,
    "waist": 1.0,
    "chest": 1.3,
    "first_floor": 1.5,
    "neck": 1.6,
    "second_floor": 3.0,
    "roof": 3.0,
}
ASSET_LABEL = {
    "boat": "boat",
    "truck": "truck",
    "medical": "medical team",
    "foot": "foot team",
    "helicopter": "helicopter",
}


@dataclass(frozen=True)
class Reach:
    ok: bool
    reason: str


def effective_depth(water_level: str | None, flood_depth_m: float | None) -> float | None:
    reported = WATER_DEPTH_M.get(water_level or "unknown")
    known = [d for d in (reported, flood_depth_m) if d is not None]
    return max(known) if known else None


def can_reach(asset: str, depth_m: float | None, in_flood_zone: bool) -> Reach:
    if asset == "helicopter":
        return Reach(True, "Helicopter reaches anywhere")
    if asset == "boat":
        if (depth_m is not None and depth_m >= 0.4) or in_flood_zone:
            return Reach(True, "Boat can operate in this water")
        return Reach(False, "Too shallow for a boat")
    limit = MAX_DEPTH_M[asset]
    if depth_m is not None and depth_m > limit:
        return Reach(False, f"{depth_m:.1f} m is too deep for a {ASSET_LABEL[asset]}")
    return Reach(True, f"{ASSET_LABEL[asset].capitalize()} can get through")


def service_seconds(asset: str, people: int | None) -> int:
    return SERVICE_BASE_S[asset] + SERVICE_PER_PERSON_S * max(1, people or 2)


def travel_seconds(asset: str, meters: float | np.ndarray) -> np.ndarray:
    speed_ms = SPEED_KMH[asset] * 1000 / 3600
    return np.asarray(meters) * DETOUR[asset] / speed_ms + STARTUP_S[asset]


def distance_matrix_m(lat: np.ndarray, lng: np.ndarray) -> np.ndarray:
    return haversine_m(lat[:, None], lng[:, None], lat[None, :], lng[None, :])


def point_along(coords: list[tuple[float, float]], fraction: float) -> tuple[float, float, float]:
    """(lat, lng, heading) a given fraction of the way along a (lat, lng) polyline."""
    if len(coords) == 1:
        return coords[0][0], coords[0][1], 0.0
    pairs = list(itertools.pairwise(coords))
    seg = [float(haversine_m(a[0], a[1], b[0], b[1])) for a, b in pairs]
    target = max(0.0, min(1.0, fraction)) * sum(seg)
    for i, ((a, b), length) in enumerate(zip(pairs, seg, strict=True)):
        if target <= length or i == len(pairs) - 1:
            f = min(1.0, target / length) if length else 0.0
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, bearing_deg(a[0], a[1], b[0], b[1])
        target -= length
    raise AssertionError("unreachable")
