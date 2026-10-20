"""Route geometry for the map and the field app.

Valhalla is preferred because it can exclude flood polygons natively, so a truck
route bends around deep water instead of through it. OSRM works without that.
With neither configured, routes are straight lines timed by the asset model.
Boats and helicopters always go direct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import orjson

from app.core.logging import log
from app.core.redis import redis
from app.core.settings import get_settings
from app.services import travel
from app.services.geocode import haversine_m

DIRECT_ASSETS = {"boat", "helicopter"}
COSTING = {"truck": "auto", "medical": "auto", "foot": "pedestrian"}


@dataclass
class Route:
    coords: list[tuple[float, float]]  # (lat, lng)
    distance_m: int
    duration_s: int
    source: str  # direct | estimate | valhalla | osrm


def direct(asset: str, a: tuple[float, float], b: tuple[float, float], source: str = "direct") -> Route:
    d = float(haversine_m(a[0], a[1], b[0], b[1]))
    return Route([a, b], int(d * travel.DETOUR[asset]), int(travel.travel_seconds(asset, d)), source)


def decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    coords, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        for is_lng in (False, True):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lng:
                lng += delta
            else:
                lat += delta
        coords.append((lat / 1e6, lng / 1e6))
    return coords


async def _valhalla(
    asset: str, a: tuple[float, float], b: tuple[float, float], avoid: list[list[list[float]]]
) -> Route:
    s = get_settings()
    body: dict[str, Any] = {
        "locations": [{"lat": a[0], "lon": a[1]}, {"lat": b[0], "lon": b[1]}],
        "costing": COSTING.get(asset, "auto"),
        "units": "kilometers",
    }
    if avoid:
        body["exclude_polygons"] = avoid
    async with httpx.AsyncClient(timeout=6) as client:
        r = await client.post(f"{s.router_url.rstrip('/')}/route", json=body)
    r.raise_for_status()
    trip = r.json()["trip"]
    coords = [pt for leg in trip["legs"] for pt in decode_polyline6(leg["shape"])]
    summary = trip["summary"]
    return Route(coords, int(summary["length"] * 1000), int(summary["time"]), "valhalla")


async def _osrm(a: tuple[float, float], b: tuple[float, float]) -> Route:
    s = get_settings()
    url = f"{s.router_url.rstrip('/')}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}"
    async with httpx.AsyncClient(timeout=6) as client:
        r = await client.get(url, params={"overview": "full", "geometries": "geojson"})
    r.raise_for_status()
    route = r.json()["routes"][0]
    coords = [(lat, lng) for lng, lat in route["geometry"]["coordinates"]]
    return Route(coords, int(route["distance"]), int(route["duration"]), "osrm")


async def route(
    asset: str,
    a: tuple[float, float],
    b: tuple[float, float],
    avoid: list[list[list[float]]] | None = None,
) -> Route:
    """avoid: flood rings as [[lng, lat], ...] lists that road assets must not enter."""
    s = get_settings()
    if asset in DIRECT_ASSETS or s.router == "estimate" or not s.router_url:
        return direct(asset, a, b, "direct" if asset in DIRECT_ASSETS else "estimate")
    key = f"route:{s.router}:{asset}:{a[0]:.4f},{a[1]:.4f}:{b[0]:.4f},{b[1]:.4f}:{len(avoid or [])}"
    try:
        if cached := await redis().get(key):
            data = orjson.loads(cached)
            return Route([tuple(p) for p in data["c"]], data["d"], data["t"], data["s"])  # type: ignore[misc]
    except Exception:  # noqa: BLE001,S110 (cache is optional)
        pass
    try:
        r = await (_valhalla(asset, a, b, avoid or []) if s.router == "valhalla" else _osrm(a, b))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        log.warning("router.fallback", router=s.router, error=str(e)[:200])
        return direct(asset, a, b, "estimate")
    try:
        await redis().set(
            key, orjson.dumps({"c": r.coords, "d": r.distance_m, "t": r.duration_s, "s": r.source}), ex=3600
        )
    except Exception:  # noqa: BLE001,S110
        pass
    return r
