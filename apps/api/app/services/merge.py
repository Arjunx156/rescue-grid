"""How a new report changes what we believe about a case. Shared by the live pipeline and the simulator."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.schemas.extraction import WATER_RANK

VULN_KEYS = ("elderly", "child", "infant", "pregnant", "disabled")
SOURCE_RANK = {"manual": 4, "pin": 3, "geocoded": 2, "unknown": 0}


@dataclass
class LocationFix:
    lat: float
    lng: float
    confidence: float
    source: str  # pin | geocoded | manual
    label: str = ""
    locality: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)


def merge_vulnerability(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    """Relatives each mention part of the picture; keep the largest count each one gave."""
    a, b = a or {}, b or {}
    out: dict[str, Any] = {k: max(int(a.get(k, 0) or 0), int(b.get(k, 0) or 0)) for k in VULN_KEYS}
    out["medical"] = sorted(set(a.get("medical", [])) | set(b.get("medical", [])))
    return out


def worse_water(a: str | None, b: str | None) -> str | None:
    if not a or a == "unknown":
        return b or a
    if not b or b == "unknown":
        return a
    return a if WATER_RANK.get(a, 0) >= WATER_RANK.get(b, 0) else b


def merge_people(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def merge_needs(a: Sequence[str] | None, b: Sequence[str] | None) -> list[str]:
    return list(dict.fromkeys([*(a or []), *(b or [])]))


def better_location(current: LocationFix | None, new: LocationFix | None) -> LocationFix | None:
    """A coordinator's pin is final; otherwise a GPS pin beats geocoding, then confidence decides."""
    if new is None:
        return current
    if current is None:
        return new
    if current.source == "manual":
        return current
    cur_rank, new_rank = SOURCE_RANK.get(current.source, 0), SOURCE_RANK.get(new.source, 0)
    if new_rank != cur_rank:
        return new if new_rank > cur_rank else current
    return new if new.confidence > current.confidence + 0.02 else current
