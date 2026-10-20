"""A water clock for every household: how long until the water reaches its danger line.

The danger line is where the family's refuge fails: the first floor for people who
have moved up, the roof for people already on it, a single-storey roof for people
still at ground level (they will climb), and far lower when someone cannot be
carried up or walked out.
The depth comes from the flood ensemble (app.services.hydro), so the clock carries
its uncertainty: an early and a late estimate around the middle one.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np

from app.agents.lexicon import CRITICAL_MEDICAL
from app.services.hydro import DEFAULT_MEMBERS, DRAIN_MM_H, Ensemble, Forcing, Forecast, Grid, Observation

HORIZON_MIN = 180
FRAME_MIN = 15
BATCH_MIN = 10  # reports are assimilated in ten-minute batches at their own time

# what a reported level says about depth: (metres, one standard error)
OBSERVED: dict[str, tuple[float, float]] = {
    "ankle": (0.15, 0.1),
    "knee": (0.45, 0.15),
    "waist": (0.8, 0.2),
    "chest": (1.15, 0.2),
    "neck": (1.6, 0.3),
    "first_floor": (1.9, 0.6),  # the ground floor is lost, but by how much is anyone's guess
    "roof": (2.3, 0.6),
    "second_floor": (3.3, 0.8),
}
NON_WALKING = ("infant", "disabled", "pregnant")


@dataclass(frozen=True)
class DangerLine:
    depth_m: float
    label: str


def danger_line(water_level: str | None, vulnerability: dict[str, Any]) -> DangerLine:
    if water_level == "second_floor":
        return DangerLine(6.0, "Water reaches the second floor")
    if water_level == "first_floor":
        return DangerLine(3.2, "Water reaches the first floor")
    if water_level == "roof":
        return DangerLine(2.6, "Water reaches the roof")
    v = vulnerability or {}
    if any(int(v.get(k, 0) or 0) for k in NON_WALKING) or set(v.get("medical", [])) & CRITICAL_MEDICAL:
        return DangerLine(1.0, "Too deep to carry out the most vulnerable")
    # people climb; with no word on the building, assume the worst case: a single storey
    return DangerLine(2.4, "Water reaches a single-storey roof")


def observation(lat: float, lng: float, water_level: str | None, minute: float) -> Observation | None:
    """A report as a gauge reading. Vague levels ("unknown") say nothing and are skipped."""
    if water_level not in OBSERVED:
        return None
    depth, sigma = OBSERVED[water_level]
    return Observation(lat, lng, depth, sigma, minute)


@dataclass(frozen=True)
class WaterClock:
    depth_m: float  # middle estimate now
    danger_m: float
    danger_label: str
    minutes: float | None  # middle estimate until the line; None if not within the horizon
    early: float | None
    late: float | None  # None: the slow members never get there within the horizon
    rise_cm_h: float  # middle estimate over the next hour

    def remaining(self, elapsed_min: float) -> float | None:
        """Minutes left once `elapsed_min` have passed since the forecast was issued."""
        return None if self.minutes is None else max(0.0, self.minutes - elapsed_min)

    def as_dict(self) -> dict[str, Any]:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> WaterClock:
        return cls(
            float(d["depth_m"]),
            float(d["danger_m"]),
            str(d["danger_label"]),
            d.get("minutes"),
            d.get("early"),
            d.get("late"),
            float(d.get("rise_cm_h") or 0.0),
        )


def clock_for(
    forecast: Forecast, lat: float, lng: float, water_level: str | None, vulnerability: dict[str, Any]
) -> WaterClock | None:
    band = forecast.depths(lat, lng)
    if band is None:
        return None
    line = danger_line(water_level, vulnerability)
    t = forecast.time_to(lat, lng, line.depth_m)
    hour = min(len(band.minutes) - 1, round(60 / forecast.every_min))
    rise = (float(band.p50[hour]) - float(band.p50[0])) * 100 * 60 / max(1.0, float(band.minutes[hour]))
    return WaterClock(
        depth_m=float(band.p50[0]),
        danger_m=line.depth_m,
        danger_label=line.label,
        minutes=t.p50 if t else None,
        early=t.early if t else None,
        late=t.late if t else None,
        rise_cm_h=rise,
    )


class Nowcast:
    """The ensemble and its latest forecast, on a disaster's clock (minutes from an epoch).

    Reports queue between cycles. A cycle advances the ensemble to each batch of
    reports' own time before assimilating it, because a reading taken twenty minutes
    ago describes the water of twenty minutes ago.
    """

    def __init__(
        self,
        grid: Grid,
        forcing: Forcing,
        spinup_min: float,
        members: Sequence[tuple[float, float]] = DEFAULT_MEMBERS,
        drain_mm_h: float = DRAIN_MM_H,
        sea_level_m: float = 0.0,
    ):
        self.ensemble = Ensemble(grid, forcing, members, drain_mm_h, spinup_min, sea_level_m)
        self.pending: list[Observation] = []
        self.forecast: Forecast | None = None
        self.reports_used = 0

    def report(self, obs: Observation | None) -> None:
        if obs is not None:
            self.pending.append(obs)

    def cycle(self, minute: float) -> Forecast:
        batches: dict[float, list[Observation]] = {}
        for o in sorted(self.pending, key=lambda o: o.minute):
            at = min(minute, max(self.ensemble.minute, math.ceil(o.minute / BATCH_MIN) * BATCH_MIN))
            batches.setdefault(at, []).append(o)
        for at, batch in sorted(batches.items()):
            self.ensemble.advance(at)
            self.reports_used += self.ensemble.assimilate(batch)
        self.pending = []
        self.ensemble.advance(minute)
        self.forecast = self.ensemble.forecast(HORIZON_MIN, FRAME_MIN)
        return self.forecast

    def profile(self, minute: float, lat: float, lng: float) -> tuple[tuple[int, float], ...]:
        """(seconds from `minute`, middle depth) for the rest of the forecast."""
        fc = self.forecast
        band = fc.depths(lat, lng) if fc else None
        if fc is None or band is None:
            return ()
        elapsed = minute - fc.minute
        now = float(np.interp(elapsed, band.minutes, band.p50))
        ahead = [(round((m - elapsed) * 60), float(d)) for m, d in zip(band.minutes, band.p50, strict=True)]
        return ((0, now), *((s, d) for s, d in ahead if s > 0))

    def clock(
        self, minute: float, lat: float, lng: float, water_level: str | None, vulnerability: dict[str, Any]
    ) -> WaterClock | None:
        """The household's clock as of `minute`, counted down from the latest forecast."""
        fc = self.forecast
        base = clock_for(fc, lat, lng, water_level, vulnerability) if fc else None
        if fc is None or base is None:
            return None
        elapsed = minute - fc.minute
        band = fc.depths(lat, lng)
        assert band is not None

        def left(m: float | None) -> float | None:
            return None if m is None else max(0.0, m - elapsed)

        return replace(
            base,
            depth_m=float(np.interp(elapsed, band.minutes, band.p50)),
            minutes=left(base.minutes),
            early=left(base.early),
            late=left(base.late),
        )
