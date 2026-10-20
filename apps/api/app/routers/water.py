"""The flood nowcast: the forecast water for the map, and the forcing a coordinator sets.

Rain and reservoir releases are what the control room hears from the weather office
and the water resources department. Entered here, they drive the ensemble; every
report of water depth then corrects it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import numpy as np
import orjson
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.actions import events, nowcast
from app.core.clock import disaster_now
from app.core.deps import Coordinator, Principal, Session, disaster_or_404
from app.core.redis import redis
from app.services.hydro import Forcing, Source

router = APIRouter(prefix="/api/v1", tags=["water"])
RAIN_RAMP_MIN = 180  # "rain in three hours" is reached three hours from now
RELEASE_RAMP_MIN = 360
DEFAULT_SPINUP_MIN = -360


class WaterGrid(BaseModel):
    west: float
    north: float
    cell_m: float
    ny: int
    nx: int


class WaterMember(BaseModel):
    rain: float
    release: float
    weight: float


class WaterForecast(BaseModel):
    """Depths for wet cells only: `cells` are flat grid indices (uint32), `p50` and `p90` are
    frames x cells bytes in `step_m` steps. All three are little-endian base64."""

    issued_at: datetime
    every_min: float
    frames: int
    step_m: float
    grid: WaterGrid
    cells: str
    p50: str
    p90: str
    reports_used: int
    members: list[WaterMember]


class ReleaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    now_m3s: float = Field(ge=0, le=20_000)
    next_m3s: float = Field(ge=0, le=20_000, description="expected six hours from now")


class FloodModelIn(BaseModel):
    rain_now_mm_h: float = Field(ge=0, le=300)
    rain_next_mm_h: float = Field(ge=0, le=300, description="expected three hours from now")
    releases: list[ReleaseIn] = Field(default_factory=list, max_length=8)
    sea_level_m: float = Field(default=0.4, ge=-1, le=3)


class FloodModelOut(BaseModel):
    rain_now_mm_h: float
    rain_next_mm_h: float
    releases: list[ReleaseIn]
    sea_level_m: float


class WaterOut(BaseModel):
    available: bool
    reason: str | None = None
    forecast: WaterForecast | None = None
    forcing: FloodModelOut | None = None


def _summary(cfg: dict, minute: float) -> FloodModelOut:
    f = Forcing.from_dict(cfg["forcing"])

    def at(series: tuple[tuple[float, float], ...], m: float) -> float:
        if not series:
            return 0.0
        return float(np.interp(m, [t for t, _ in series], [v for _, v in series]))

    return FloodModelOut(
        rain_now_mm_h=round(at(f.rain_mm_h, minute), 1),
        rain_next_mm_h=round(at(f.rain_mm_h, minute + RAIN_RAMP_MIN), 1),
        releases=[
            ReleaseIn(
                name=s.name,
                lat=s.lat,
                lng=s.lng,
                now_m3s=round(at(s.m3s, minute)),
                next_m3s=round(at(s.m3s, minute + RELEASE_RAMP_MIN)),
            )
            for s in f.sources
        ],
        sea_level_m=float(cfg.get("sea_level_m", 0.0)),
    )


@router.get("/disasters/{disaster_id}/water", response_model=WaterOut)
async def water(disaster_id: uuid.UUID, claims: Principal, session: Session) -> WaterOut:
    d = await disaster_or_404(session, claims, disaster_id)
    reason = nowcast.unavailable_reason(d)
    cfg = nowcast.model_config(d)
    forcing = None
    if cfg is not None:
        now = await disaster_now(d.id, d.status)
        forcing = _summary(cfg, (now - datetime.fromisoformat(cfg["epoch"])).total_seconds() / 60)
    if reason:
        return WaterOut(available=False, reason=reason, forcing=forcing)
    raw = await redis().get(nowcast.water_key(d.id))
    if not raw:
        return WaterOut(available=False, reason="The first forecast is being computed", forcing=forcing)
    return WaterOut(available=True, forecast=WaterForecast.model_validate(orjson.loads(raw)), forcing=forcing)


@router.put("/disasters/{disaster_id}/flood-model", response_model=FloodModelOut)
async def set_flood_model(
    disaster_id: uuid.UUID, body: FloodModelIn, claims: Coordinator, session: Session
) -> FloodModelOut:
    """Set the rain and releases from now on. What already happened stays as it was forecast."""
    d = await disaster_or_404(session, claims, disaster_id)
    cfg = dict(nowcast.model_config(d) or {})
    epoch = datetime.fromisoformat(cfg["epoch"]) if cfg.get("epoch") else d.started_at
    now = await disaster_now(d.id, d.status)
    m = (now - epoch).total_seconds() / 60
    old = Forcing.from_dict(cfg["forcing"]) if cfg.get("forcing") else Forcing.none()
    grid = nowcast.terrain()

    def past(series: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
        return tuple(p for p in series if p[0] < m)

    sources = []
    for r in body.releases:
        prior = next((s.m3s for s in old.sources if s.name == r.name), ())
        lat, lng = grid.nearest_channel(r.lat, r.lng) if grid else (r.lat, r.lng)
        sources.append(Source(r.name, lat, lng, (*past(prior), (m, r.now_m3s), (m + RELEASE_RAMP_MIN, r.next_m3s))))
    forcing = Forcing(
        rain_mm_h=(*past(old.rain_mm_h), (m, body.rain_now_mm_h), (m + RAIN_RAMP_MIN, body.rain_next_mm_h)),
        sources=tuple(sources),
    )
    cfg |= {
        "epoch": epoch.isoformat(),
        "spinup_min": cfg.get("spinup_min", DEFAULT_SPINUP_MIN),
        "sea_level_m": body.sea_level_m,
        "forcing": forcing.to_dict(),
    }
    d.settings = {**(d.settings or {}), "flood_model": cfg}
    await session.commit()
    nowcast.refresh(d.id)
    await events.publish(d.id, "water.forcing", {})
    return _summary(cfg, m)
