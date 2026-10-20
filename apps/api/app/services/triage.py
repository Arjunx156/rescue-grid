"""Explainable 0-100 urgency. Every point is a line a coordinator can read.

A transparent weighted model on purpose: when a dispatcher asks "why is this
above that", the breakdown answers it, factor by factor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.agents.lexicon import CRITICAL_MEDICAL

LEVELS = (("critical", 70), ("high", 50), ("medium", 30), ("low", 0))

WATER_POINTS = {
    "roof": 34,
    "neck": 34,
    "chest": 28,
    "first_floor": 22,
    "waist": 17,
    "second_floor": 16,
    "knee": 9,
    "ankle": 3,
    "unknown": 12,
    "none": 0,
}
WATER_LABEL = {
    "roof": "On the roof",
    "neck": "Neck-deep water",
    "chest": "Chest-deep water",
    "first_floor": "Ground floor flooded",
    "waist": "Waist-deep water",
    "second_floor": "Sheltering on 2nd floor",
    "knee": "Knee-deep water",
    "ankle": "Ankle-deep water",
    "unknown": "Water level not reported",
    "none": "No flooding reported",
}
RESCUE_NEEDS = {"rescue", "evacuation", "boat", "medical"}
# water clock: minutes until the forecast water reaches the family's danger line -> points. Within the hour
# it weighs about as much as being at the line now: the forecast earns that trust in evals/water.py
CLOCK_POINTS = ((30, 30), (60, 24), (120, 14), (180, 7))
MEDICAL_LABEL = {
    "dialysis": "dialysis",
    "oxygen": "oxygen dependent",
    "labour": "in labour",
    "cardiac": "cardiac",
    "unconscious": "unconscious / seizure",
    "injury": "injured",
    "diabetes": "insulin dependent",
    "cancer": "cancer care",
    "fever": "fever / illness",
    "post_surgery": "post-surgery",
    "medication": "needs medicines",
}


@dataclass
class Factor:
    key: str
    label: str
    points: int
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "points": self.points, "detail": self.detail}


@dataclass
class TriageInput:
    people_count: int | None
    vulnerability: dict[str, Any]
    water_level: str | None
    water_rising: bool | None
    needs: list[str]
    first_reported_at: datetime
    source_count: int = 1
    flood_depth_m: float | None = None
    in_flood_zone: bool = False
    minutes_to_danger: float | None = None  # the water clock; None when the forecast sees no crossing
    danger_label: str | None = None


@dataclass
class TriageResult:
    score: int
    level: str
    breakdown: list[Factor] = field(default_factory=list)

    def breakdown_dicts(self) -> list[dict[str, Any]]:
        return [f.as_dict() for f in self.breakdown]


def level_for(score: int) -> str:
    return next(name for name, floor in LEVELS if score >= floor)


def score(inp: TriageInput, now: datetime) -> TriageResult:
    f: list[Factor] = []
    v = inp.vulnerability or {}
    medical = [m for m in v.get("medical", []) if m in MEDICAL_LABEL]
    critical_med = [m for m in medical if m in CRITICAL_MEDICAL]
    needs = set(inp.needs or [])
    water = inp.water_level or "unknown"

    if needs & RESCUE_NEEDS:
        f.append(Factor("rescue", "Rescue requested", 10, "Stranded and asking to be taken out"))

    f.append(Factor("water", WATER_LABEL.get(water, water), WATER_POINTS.get(water, 12)))
    if inp.water_rising:
        f.append(Factor("rising", "Water rising", 8, "Reporter says the level is still going up"))

    if medical:
        other = [m for m in medical if m not in CRITICAL_MEDICAL]
        crit_pts = 24 + 4 * (len(critical_med) - 1) if critical_med else 0
        chronic_pts = 10 + 3 * (len(other) - 1) if other else 0
        # chronic needs add a little on top of an acute one, never as much on their own
        pts = min(28, crit_pts + min(chronic_pts, 6 if critical_med else 14))
        f.append(Factor("medical", "Medical need", pts, ", ".join(MEDICAL_LABEL[m] for m in medical)))

    parts, vul = [], 0
    for key, each, cap, label in (
        ("infant", 9, 14, "infant"),
        ("pregnant", 12, 12, "pregnant"),
        ("disabled", 9, 14, "disabled"),
        ("elderly", 6, 12, "elderly"),
        ("child", 5, 10, "child"),
    ):
        n = int(v.get(key, 0) or 0)
        if n:
            vul += min(cap, each * n)
            parts.append(f"{n} {label}")
    if vul:
        f.append(Factor("vulnerable", "Vulnerable people", min(24, vul), ", ".join(parts)))

    if inp.people_count:
        pts = min(8, 2 * (inp.people_count - 1))
        if pts:
            f.append(Factor("headcount", f"{inp.people_count} people", pts))
    else:
        f.append(Factor("headcount", "Headcount unknown", 2))

    waited = max(0.0, (now - inp.first_reported_at).total_seconds() / 60)
    if (pts := min(12, int(waited // 15))) > 0:
        f.append(Factor("waiting", "Time waiting", pts, _ago(waited)))

    if inp.minutes_to_danger is not None:
        # a forecast can raise urgency but never lower it: no points is the floor
        m = inp.minutes_to_danger
        pts = next((p for limit, p in CLOCK_POINTS if m <= limit), 0)
        if pts:
            label = "Water at the danger line" if m < 1 else f"Water reaches the danger line in ~{round(m)} min"
            f.append(Factor("water_clock", label, pts, inp.danger_label or ""))

    depth = inp.flood_depth_m
    if depth is not None and depth >= 1.5:
        f.append(Factor("flood_zone", "Deep flood zone", 6, f"~{depth:.1f} m mapped depth"))
    elif depth is not None and depth >= 0.8:
        f.append(Factor("flood_zone", "Flood zone", 4, f"~{depth:.1f} m mapped depth"))
    elif inp.in_flood_zone:
        f.append(Factor("flood_zone", "Inside flood zone", 2))

    if inp.source_count >= 3:
        f.append(Factor("reports", f"{inp.source_count} independent reports", 2))

    total = sum(x.points for x in f)
    supplies_only = needs and not needs & RESCUE_NEEDS and not critical_med and water in ("none", "unknown", "ankle")
    if supplies_only and total > 40:
        f.append(Factor("cap", "Supplies only, no life threat", 40 - total, "Capped at 40"))
        total = 40
    total = max(0, min(100, total))
    return TriageResult(total, level_for(total), sorted(f, key=lambda x: -x.points))


def _ago(minutes: float) -> str:
    if minutes < 90:
        return f"{int(minutes)} min since first report"
    hours = minutes / 60
    return f"{hours:.1f} h since first report" if hours < 10 else f"{math.floor(hours)} h since first report"
