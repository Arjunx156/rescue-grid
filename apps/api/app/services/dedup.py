"""Is this report the same household as an existing case?

Location says "maybe"; phones, door numbers and names say "yes" or veto it.
Two families behind the same temple must stay two cases, so disagreement on a
specific identifier counts against a merge as strongly as agreement counts for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from rapidfuzz import fuzz

from app.schemas.extraction import WATER_RANK
from app.services import textnorm
from app.services.geocode import haversine_m

MERGE_AT = 0.6
REVIEW_AT = 0.35
WINDOW = timedelta(hours=12)
PHONE_WINDOW = timedelta(hours=48)
CLOSE_IN_TIME = timedelta(hours=3)  # relatives of one family report within hours of each other
WATER_GAP = timedelta(minutes=90)
ANCHORED_CLOSE = 0.1  # beyond this, a different level may just be the water rising
SEARCH_RADIUS_M = 1_000.0
# after a rescue, nearby open cases this similar get a human check before another team goes
RESCUED_NEARBY_M = 300.0
RESCUED_NEARBY_SCORE = 0.3
SPECIFIC_MEDICAL = {"dialysis", "oxygen", "labour", "cardiac", "cancer", "post_surgery", "unconscious"}

_DOOR = re.compile(r"\b(?:no|door|house|flat|plot|#)\s*\.?\s*(\d+[a-z]?(?:/\d+[a-z]?)?)", re.IGNORECASE)
_SLASH_NO = re.compile(r"\b(\d+[a-z]?/\d+[a-z]?)\b", re.IGNORECASE)


@dataclass
class Signals:
    """What dedup compares, for a new report or an existing case."""

    lat: float | None
    lng: float | None
    location_confidence: float
    phone_hashes: set[str]  # numbers written in the message: they name the household
    reported_at: datetime
    sender_hashes: set[str] = field(default_factory=set)  # volunteers forward for many families
    contact_name: str | None = None
    address: str | None = None
    people_count: int | None = None
    vulnerability: dict[str, Any] = field(default_factory=dict)
    location_text: str | None = None
    embedding: list[float] | None = None
    last_reported_at: datetime | None = None
    anchors: set[str] = field(default_factory=set)  # landmark / street entries the location rests on
    locality: str | None = None
    water_level: str | None = None

    def door(self) -> str | None:
        if not self.address:
            return None
        m = _DOOR.search(self.address) or _SLASH_NO.search(self.address)
        return m.group(1).lower() if m else None


@dataclass
class Verdict:
    score: float
    decision: str  # merge | review | separate
    reasons: list[dict[str, Any]]


def _add(reasons: list[dict[str, Any]], key: str, weight: float, detail: str) -> float:
    reasons.append({"key": key, "weight": round(weight, 2), "detail": detail})
    return weight


def compare(new: Signals, old: Signals) -> Verdict:
    reasons: list[dict[str, Any]] = []
    s = 0.0
    phone_match = bool(new.phone_hashes & old.phone_hashes)
    sender_match = bool(
        new.sender_hashes & (old.phone_hashes | old.sender_hashes) or old.sender_hashes & new.phone_hashes
    )
    last = old.last_reported_at or old.reported_at
    gap = abs(new.reported_at - last)
    if gap > (PHONE_WINDOW if phone_match else WINDOW):
        return Verdict(0.0, "separate", [{"key": "time", "weight": 0, "detail": "Too far apart in time"}])

    if phone_match:
        s += _add(reasons, "phone", 0.6, "Same contact number")
    elif new.phone_hashes and old.phone_hashes:
        s += _add(reasons, "phone", -0.3, "Different contact numbers")
    if sender_match and not phone_match:
        s += _add(reasons, "sender", 0.25, "Reported from the same phone")

    shared_anchor = bool(new.anchors & old.anchors)
    if new.lat is not None and old.lat is not None:
        d = float(haversine_m(new.lat, new.lng, old.lat, old.lng))
        sure = min(new.location_confidence, old.location_confidence) >= 0.6
        k = 1.0 if sure else 0.5
        if shared_anchor and d <= 150:
            # pins placed on the same landmark agree by construction: mostly the same evidence as the landmark
            s += _add(reasons, "distance", ANCHORED_CLOSE * k, f"{d:.0f} m apart, same landmark")
        elif d <= 50:
            s += _add(reasons, "distance", 0.25 * k, f"{d:.0f} m apart")
        elif d <= 150:
            s += _add(reasons, "distance", 0.18 * k, f"{d:.0f} m apart")
        elif d <= 300:
            s += _add(reasons, "distance", 0.1 * k, f"{d:.0f} m apart")
        elif d > 600 and sure and not phone_match:
            s += _add(reasons, "distance", -0.45, f"{d / 1000:.1f} km apart")

    nd, od = new.door(), old.door()
    if nd and od:
        if nd == od:
            street = fuzz.token_set_ratio(textnorm.key(new.address or ""), textnorm.key(old.address or ""))
            s += _add(reasons, "address", 0.35 if street >= 70 else 0.2, f"Same door number {nd}")
        else:
            s += _add(reasons, "address", -0.35, f"Door {nd} vs {od}")

    if new.contact_name and old.contact_name:
        r = fuzz.token_set_ratio(new.contact_name.lower(), old.contact_name.lower())
        if r >= 88:
            s += _add(reasons, "name", 0.25, f"Same name ({new.contact_name})")
        elif r < 60:
            s += _add(reasons, "name", -0.15, "Different names")

    if new.people_count and old.people_count:
        diff = abs(new.people_count - old.people_count)
        if diff == 0:
            s += _add(reasons, "people", 0.08, f"Both {new.people_count} people")
        elif diff == 1:
            s += _add(reasons, "people", 0.04, "Headcount within 1")
        else:  # relatives miscount by one, rarely by more
            s += _add(reasons, "people", -0.1, f"{new.people_count} vs {old.people_count} people")

    # neighbours stand in the same water, so agreement says "same street", not "same family";
    # and one family's level rises over hours, so only a quick contradiction counts against
    nw, ow = new.water_level or "unknown", old.water_level or "unknown"
    if nw == ow and nw != "unknown":
        s += _add(reasons, "water", 0.02, f"Same water level ({nw.replace('_', ' ')})")
    elif "unknown" not in (nw, ow) and abs(WATER_RANK.get(nw, 0) - WATER_RANK.get(ow, 0)) >= 2 and gap <= WATER_GAP:
        s += _add(reasons, "water", -0.08, f"{nw.replace('_', ' ')} vs {ow.replace('_', ' ')}")
    if gap <= CLOSE_IN_TIME:
        s += _add(reasons, "time", 0.06, f"Reported {int(gap.total_seconds() // 60)} min apart")

    if new.anchors & old.anchors:
        s += _add(reasons, "landmark", 0.28, "Described by the same landmark or street")
    elif new.locality and old.locality and new.locality.lower() == old.locality.lower():
        s += _add(reasons, "locality", 0.05, f"Both in {new.locality}")

    nv, ov = new.vulnerability or {}, old.vulnerability or {}
    shared_med = set(nv.get("medical", [])) & set(ov.get("medical", [])) & SPECIFIC_MEDICAL
    if shared_med:
        s += _add(reasons, "medical", 0.15, "Both mention " + ", ".join(sorted(shared_med)))
    shared = [k for k in ("infant", "pregnant", "disabled", "elderly", "child") if nv.get(k) and ov.get(k)]
    if shared:
        weight = min(0.15, sum(0.08 if k in ("infant", "pregnant", "disabled") else 0.04 for k in shared))
        s += _add(reasons, "vulnerable", weight, "Both mention " + ", ".join(shared))

    # same words for the place, unless that place already counted as a shared landmark
    if new.location_text and old.location_text and not new.anchors & old.anchors:
        r = fuzz.token_set_ratio(textnorm.key(new.location_text), textnorm.key(old.location_text))
        if r >= 85:
            s += _add(reasons, "text", 0.1, "Same place description")

    if new.embedding is not None and old.embedding is not None:
        a, b = np.asarray(new.embedding), np.asarray(old.embedding)
        cos = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        if cos >= 0.9:
            s += _add(reasons, "semantic", 0.15, f"Very similar wording ({cos:.2f})")
        elif cos >= 0.85:
            s += _add(reasons, "semantic", 0.08, f"Similar wording ({cos:.2f})")

    s = max(0.0, min(1.0, s))
    decision = "merge" if s >= MERGE_AT else "review" if s >= REVIEW_AT else "separate"
    return Verdict(round(s, 3), decision, reasons)


def best_match(new: Signals, candidates: list[tuple[Any, Signals]]) -> tuple[Any, Verdict] | None:
    """The strongest candidate that is at least worth a human look."""
    best: tuple[Any, Verdict] | None = None
    for ref, sig in candidates:
        v = compare(new, sig)
        if v.decision != "separate" and (best is None or v.score > best[1].score):
            best = (ref, v)
    return best
