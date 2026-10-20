"""Point-in-flood-zone lookups for code that runs without the database (replay, benchmark)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import Point, shape
from shapely.strtree import STRtree


@dataclass(frozen=True)
class Zone:
    name: str
    depth_m: float
    geom: shapely.Geometry


class FloodMap:
    def __init__(self, zones: list[Zone]):
        self.zones = zones
        self._tree = STRtree([z.geom for z in zones]) if zones else None

    @classmethod
    def from_geojson(cls, fc: dict[str, Any]) -> FloodMap:
        return cls(
            [
                Zone(
                    f["properties"].get("name") or "Flood zone",
                    float(f["properties"].get("depth_m") or 0.5),
                    shape(f["geometry"]),
                )
                for f in fc.get("features", [])
            ]
        )

    @classmethod
    def load(cls, path: Path) -> FloodMap:
        return cls.from_geojson(json.loads(path.read_text(encoding="utf-8")))

    def depth_at(self, lat: float, lng: float) -> tuple[bool, float | None]:
        """(inside any zone, deepest mapped depth there)."""
        if self._tree is None:
            return False, None
        p = Point(lng, lat)
        hits = [self.zones[i] for i in self._tree.query(p, predicate="intersects")]
        if not hits:
            return False, None
        return True, max(z.depth_m for z in hits)
