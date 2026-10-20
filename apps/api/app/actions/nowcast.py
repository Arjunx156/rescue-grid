"""The water clock, live: one flood ensemble per disaster, fed by every report that says how deep.

A disaster runs the flood model when the terrain covers it and its forcing is set
(disaster.settings["flood_model"]: from the replay dataset, or entered by an admin).
Each cycle advances the ensemble to the disaster's clock, assimilates the levels
reported since the last cycle, forecasts three hours ahead, stores the forecast for
the map, gives every open case its water clock, rescores, and asks for a re-plan
when the clocks moved.

The ensemble lives in this process. After a restart the first cycle spins it up
again from the forcing and replays every report since the start, so nothing is lost.
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import numpy as np
import orjson
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import events, geo
from app.actions.resolve import rescore
from app.actions.serialize import case_out
from app.core.clock import disaster_now
from app.core.logging import log
from app.core.redis import redis
from app.core.settings import get_settings
from app.models import Case, Disaster, Extraction, SosMessage
from app.models.tables import OPEN_CASE_STATUSES
from app.services import waterclock
from app.services.hydro import M_PER_DEG_LAT, M_PER_DEG_LNG, Forcing, Forecast, Grid

CYCLE_SIM_MIN = 10.0  # a replay's clock runs fast: a cycle every ten minutes of it
CYCLE_WALL_S = 120.0  # a live disaster: at least every two minutes
DEPTH_STEP_M = 0.025  # the map gets depths in 2.5 cm steps, one byte each
SHOWN_M = 0.2  # cells drier than this in every frame stay off the map
KEY_TTL_S = 6 * 3600


@dataclass
class Run:
    epoch: datetime
    nowcast: waterclock.Nowcast
    seen_until: datetime
    wall: float = 0.0
    stale: bool = False  # the forcing changed: forecast again even if the clock has not moved


_runs: dict[uuid.UUID, Run] = {}


def water_key(disaster_id: uuid.UUID | str) -> str:
    return f"water:{disaster_id}"


@lru_cache
def terrain() -> Grid | None:
    path = get_settings().data_dir / "geo" / "terrain.npz"
    return Grid.load(path) if path.exists() else None


def model_config(d: Disaster) -> dict[str, Any] | None:
    cfg = (d.settings or {}).get("flood_model")
    return cfg if isinstance(cfg, dict) and cfg.get("forcing") is not None else None


def unavailable_reason(d: Disaster) -> str | None:
    """Why this disaster has no water clock, in words for the map; None when it has one."""
    grid = terrain()
    if grid is None:
        return "No terrain model is installed"
    centre = geo.center(d.area)
    if centre is None or grid.cell(*centre) is None:
        return "The terrain model does not cover this area"
    if model_config(d) is None:
        return "Rain and reservoir releases are not set for this disaster"
    return None


async def cycle(session: AsyncSession, d: Disaster) -> bool:
    """Run one nowcast for a disaster if one is due. True when a new forecast was issued."""
    cfg, grid = model_config(d), terrain()
    if cfg is None or grid is None or unavailable_reason(d):
        return False
    now = await disaster_now(d.id, d.status)
    epoch = datetime.fromisoformat(cfg["epoch"])
    minute = (now - epoch).total_seconds() / 60
    run = _runs.get(d.id)
    forcing = Forcing.from_dict(cfg["forcing"])
    if run is None or run.epoch != epoch:
        spinup = float(cfg.get("spinup_min", -360))
        nowcast = waterclock.Nowcast(grid, forcing, spinup, sea_level_m=float(cfg.get("sea_level_m", 0.0)))
        run = _runs[d.id] = Run(epoch, nowcast, epoch + timedelta(minutes=spinup))
    run.nowcast.ensemble.forcing = forcing  # an admin may have updated the forecast
    last = run.nowcast.forecast
    if last is not None and not run.stale:
        fresh = minute - last.minute < CYCLE_SIM_MIN and time.time() - run.wall < CYCLE_WALL_S
        if fresh or minute <= last.minute:
            return False
    run.stale = False

    for lat, lng, level, at in await _reports(session, d.id, run.seen_until, now):
        run.nowcast.report(waterclock.observation(lat, lng, level, (at - epoch).total_seconds() / 60))
    run.seen_until = now
    started = time.perf_counter()
    forecast = await asyncio.to_thread(run.nowcast.cycle, minute)
    run.wall = time.time()
    await redis().set(water_key(d.id), orjson.dumps(pack(forecast, now, run.nowcast)).decode(), ex=KEY_TTL_S)
    changed = await _apply_clocks(session, d, run.nowcast, minute, now)
    await events.publish(d.id, "water.update", {"issued_at": now.isoformat(), "clocks_changed": changed})
    if changed:
        await events.trigger_dispatch(d.id, "water_clock")
    log.info(
        "nowcast.cycle",
        disaster=str(d.id),
        minute=round(minute, 1),
        reports=run.nowcast.reports_used,
        clocks_changed=changed,
        ms=int((time.perf_counter() - started) * 1000),
    )
    return True


async def _reports(
    session: AsyncSession, disaster_id: uuid.UUID, since: datetime, until: datetime
) -> list[tuple[float, float, str, datetime]]:
    """Reported water levels at confidently located cases, received in (since, until]."""
    rows = await session.execute(
        select(Case.location, Extraction.water_level, SosMessage.received_at)
        .join(Extraction, Extraction.sos_message_id == SosMessage.id)
        .join(Case, Case.id == SosMessage.case_id)
        .where(
            SosMessage.disaster_id == disaster_id,
            SosMessage.received_at > since,
            SosMessage.received_at <= until,
            Case.location.is_not(None),
            Case.location_confidence >= get_settings().location_review_threshold,
            Extraction.water_level.in_(tuple(waterclock.OBSERVED)),
        )
    )
    out = []
    for location, level, at in rows:
        ll = geo.latlng(location)
        if ll:
            out.append((ll[0], ll[1], level, at))
    return out


async def _apply_clocks(
    session: AsyncSession, d: Disaster, nowcast: waterclock.Nowcast, minute: float, now: datetime
) -> int:
    cases = list(
        await session.scalars(
            select(Case).where(
                Case.disaster_id == d.id, Case.status.in_(OPEN_CASE_STATUSES), Case.location.is_not(None)
            )
        )
    )
    changed: list[Case] = []
    for c in cases:
        ll = geo.latlng(c.location)
        clock = nowcast.clock(minute, ll[0], ll[1], c.water_level, c.vulnerability) if ll else None
        fresh = clock.as_dict() | {"issued_at": now.isoformat()} if clock else None
        if _moved(c.water_clock, fresh):
            c.water_clock = fresh
            rescore(c, now)
            changed.append(c)
        elif fresh is not None:
            c.water_clock = fresh  # same story, newer issue time: no rescore or broadcast needed
    await session.commit()
    if changed:
        await events.publish(
            d.id,
            "cases.upsert",
            {
                "cases": [case_out(c, "coordinator").model_dump(mode="json") for c in changed],
                "masked": [case_out(c, "viewer").model_dump(mode="json") for c in changed],
            },
        )
    return len(changed)


def _moved(old: dict[str, Any] | None, new: dict[str, Any] | None) -> bool:
    """A clock change worth a rescore: it appeared, vanished, or moved by ten minutes or more."""
    if (old is None) != (new is None):
        return True
    if old is None or new is None:
        return False
    a, b = old.get("minutes"), new.get("minutes")
    if (a is None) != (b is None):
        return True
    elapsed = (datetime.fromisoformat(new["issued_at"]) - datetime.fromisoformat(old["issued_at"])).total_seconds()
    return a is not None and b is not None and abs((a - elapsed / 60) - b) >= 10


def pack(fc: Forecast, issued_at: datetime, nowcast: waterclock.Nowcast) -> dict[str, Any]:
    """The forecast for the map: wet cells only, depths as bytes, base64 for JSON."""
    frames = fc.p50.shape[0]
    p50, p90 = fc.p50.reshape(frames, -1), fc.p90.reshape(frames, -1)
    # the sea, rivers and lakes are always wet; the map shows flood, which is water where land should be
    land = fc.grid.water.reshape(-1) == 0
    cells = np.flatnonzero(land & (p90.max(axis=0) >= SHOWN_M)).astype("<u4")

    def b64(a: np.ndarray) -> str:
        return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()

    def quantize(a: np.ndarray) -> np.ndarray:
        return np.clip(np.round(a[:, cells] / DEPTH_STEP_M), 0, 255).astype(np.uint8)

    ny, nx = fc.grid.shape
    ens = nowcast.ensemble
    return {
        "issued_at": issued_at.isoformat(),
        "every_min": fc.every_min,
        "frames": frames,
        "step_m": DEPTH_STEP_M,
        "grid": {"west": fc.grid.west, "north": fc.grid.north, "cell_m": fc.grid.cell_m, "ny": ny, "nx": nx},
        "cells": b64(cells),
        "p50": b64(quantize(p50)),
        "p90": b64(quantize(p90)),
        "reports_used": nowcast.reports_used,
        "members": [
            {"rain": r, "release": q, "weight": round(float(w), 4)}
            for (r, q), w in zip(ens.scales, ens.weights, strict=True)
        ],
    }


async def depth_profiles(
    disaster_id: uuid.UUID, points: dict[str, tuple[float, float]], now: datetime
) -> dict[str, tuple[tuple[int, float], ...]]:
    """(seconds from now, middle forecast depth) at each point, from the stored forecast.

    Read from Redis rather than this process's ensemble, so a planner in another
    worker process sees the same water."""
    raw = await redis().get(water_key(disaster_id))
    if not raw:
        return {}
    p = orjson.loads(raw)
    g = p["grid"]
    cells = np.frombuffer(base64.b64decode(p["cells"]), dtype="<u4")
    p50 = np.frombuffer(base64.b64decode(p["p50"]), dtype=np.uint8).reshape(p["frames"], -1)
    elapsed_s = (now - datetime.fromisoformat(p["issued_at"])).total_seconds()
    frame_s = np.arange(p["frames"]) * p["every_min"] * 60.0
    dlat, dlng = g["cell_m"] / M_PER_DEG_LAT, g["cell_m"] / M_PER_DEG_LNG
    out = {}
    for key, (lat, lng) in points.items():
        i, j = int((g["north"] - lat) // dlat), int((lng - g["west"]) // dlng)
        if not (0 <= i < g["ny"] and 0 <= j < g["nx"]):
            continue
        k = int(np.searchsorted(cells, i * g["nx"] + j))
        if k >= len(cells) or cells[k] != i * g["nx"] + j:
            continue  # dry in every frame: no water to plan around
        depth = p50[:, k] * p["step_m"]
        ahead = [(round(t - elapsed_s), float(d)) for t, d in zip(frame_s, depth, strict=True) if t > elapsed_s]
        out[key] = ((0, float(np.interp(elapsed_s, frame_s, depth))), *ahead)
    return out


def refresh(disaster_id: uuid.UUID) -> None:
    """New forcing: the next cycle forecasts again with it."""
    if run := _runs.get(disaster_id):
        run.stale = True
