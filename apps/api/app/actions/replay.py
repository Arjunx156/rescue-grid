"""Disaster replay: stream a historical (or modelled) SOS dataset through the live pipeline.

A replay is a real disaster with status "replay": messages go through intake,
understanding, resolution and dispatch exactly like live traffic, on a simulated
clock. Virtual teams drive themselves through the field state machine, so the
whole loop runs unattended at 60x or more.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import events, field, geo, intake
from app.actions.events import Actor
from app.core.clock import ReplayClock, load_replay_clock, replay_key, save_replay_clock
from app.core.logging import log
from app.core.redis import redis
from app.core.settings import get_settings
from app.models import (
    Assignment,
    Case,
    Disaster,
    DisasterOrganization,
    FloodZone,
    Organization,
    ReplayDataset,
    Team,
)
from app.models.tables import ASSIGNMENT_ACTIVE
from app.services import travel

SIM_TEAM = Actor("team", None, "Simulated crew")
MAX_PER_TICK = 150


def _dir(slug: str) -> Path:
    path = (get_settings().data_dir / "replay" / slug).resolve()
    if not path.is_relative_to((get_settings().data_dir / "replay").resolve()):
        raise ValueError("bad dataset slug")
    return path


@lru_cache
def meta(slug: str) -> dict[str, Any]:
    return json.loads((_dir(slug) / "dataset.json").read_text(encoding="utf-8"))


@lru_cache
def messages(slug: str) -> list[dict[str, Any]]:
    lines = (_dir(slug) / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(x) for x in lines if x.strip()]
    rows.sort(key=lambda m: m["t"])
    return rows


def flood_model(slug: str, epoch: datetime) -> dict[str, Any] | None:
    """The forecast a control room would have had for this dataset, if it ships one (app.sim.flood)."""
    path = _dir(slug) / "forcing.json"
    if not path.exists():
        return None
    f = json.loads(path.read_text(encoding="utf-8"))
    return {
        "epoch": epoch.isoformat(),
        "spinup_min": f["spinup_min"],
        "sea_level_m": f["sea_level_m"],
        "forcing": f["forecast"],
    }


def available() -> list[dict[str, Any]]:
    base = get_settings().data_dir / "replay"
    out = []
    for p in sorted(base.glob("*/dataset.json")) if base.exists() else []:
        m = json.loads(p.read_text(encoding="utf-8"))
        out.append(
            {
                k: m[k]
                for k in (
                    "slug",
                    "name",
                    "description",
                    "starts_at",
                    "ends_at",
                    "message_count",
                    "household_count",
                    "source_url",
                )
                if k in m
            }
        )
    return out


def cursor_key(disaster_id: uuid.UUID) -> str:
    return f"{replay_key(disaster_id)}:cursor"


async def ensure_dataset(session: AsyncSession, slug: str) -> ReplayDataset:
    m = meta(slug)
    ds = await session.scalar(select(ReplayDataset).where(ReplayDataset.slug == slug))
    if ds is None:
        ds = ReplayDataset(
            slug=slug,
            name=m["name"],
            description=m["description"],
            source_url=m.get("source_url"),
            message_count=m["message_count"],
            file_path=f"replay/{slug}/messages.jsonl",
            starts_at=datetime.fromisoformat(m["starts_at"]),
            ends_at=datetime.fromisoformat(m["ends_at"]),
            meta={"teams": len(m["teams"])},
        )
        session.add(ds)
        await session.flush()
    return ds


async def start(session: AsyncSession, slug: str, speed: float, autopilot: bool) -> Disaster:
    m = meta(slug)
    ds = await ensure_dataset(session, slug)
    # one replay per dataset: starting again wipes the previous run
    for old in await session.scalars(select(Disaster).where(Disaster.replay_dataset_id == ds.id)):
        await redis().delete(replay_key(old.id), cursor_key(old.id))
        await session.delete(old)
    await session.flush()
    starts = datetime.fromisoformat(m["starts_at"])
    d = Disaster(
        name=f"{m['name']} (replay)",
        status="replay",
        description=m["description"],
        area=geo.multipolygon(m["area"]),
        started_at=starts,
        replay_dataset_id=ds.id,
        settings={
            "autopilot": autopilot,
            "speed": speed,
            "dataset": slug,
            "ends_at": m["ends_at"],
            "total": len(messages(slug)),
        }
        | ({"flood_model": model} if (model := flood_model(slug, starts)) else {}),
    )
    session.add(d)
    await session.flush()
    for org_id in await session.scalars(select(Organization.id)):
        session.add(DisasterOrganization(disaster_id=d.id, organization_id=org_id))
    zones = json.loads((_dir(slug) / "flood_zones.geojson").read_text(encoding="utf-8"))
    for f in zones["features"]:
        session.add(
            FloodZone(
                disaster_id=d.id,
                name=f["properties"].get("name"),
                geom=geo.multipolygon(f["geometry"]),
                depth_estimate_m=f["properties"].get("depth_m"),
                source=f["properties"]["source"],
                valid_from=starts,
            )
        )
    for t in m["teams"]:
        session.add(
            Team(
                disaster_id=d.id,
                call_sign=t["call_sign"],
                asset_type=t["asset_type"],
                capacity=t["capacity"],
                status="available",
                current_location=geo.point(t["lat"], t["lng"]),
                base_location=geo.point(t["lat"], t["lng"]),
                base_name=t.get("base_name"),
                is_virtual=True,
                location_updated_at=starts,
                notes=t.get("organization"),
            )
        )
    await session.commit()
    await save_replay_clock(d.id, ReplayClock("playing", speed, starts, time.time()))
    await redis().set(cursor_key(d.id), 0)
    log.info("replay.started", disaster=str(d.id), dataset=slug, speed=speed)
    await events.publish(d.id, "replay.state", await state(d))
    return d


async def control(session: AsyncSession, d: Disaster, action: str, speed: float | None = None) -> dict[str, Any]:
    clock = await load_replay_clock(d.id)
    if clock is None:
        raise ValueError("replay has no clock; start it again")
    now_sim, wall = clock.now(), time.time()
    if action == "pause":
        clock = ReplayClock("paused", clock.speed, now_sim, wall)
    elif action == "resume":
        if clock.status == "finished":
            return await state(d)
        clock = ReplayClock("playing", clock.speed, now_sim, wall)
    elif action == "speed" and speed:
        clock = ReplayClock(clock.status, speed, now_sim, wall)
        d.settings = {**(d.settings or {}), "speed": speed}
        await session.commit()
    elif action == "stop":
        clock = ReplayClock("finished", clock.speed, now_sim, wall)
    await save_replay_clock(d.id, clock)
    s = await state(d)
    await events.publish(d.id, "replay.state", s)
    return s


async def state(d: Disaster) -> dict[str, Any]:
    clock = await load_replay_clock(d.id)
    slug = (d.settings or {}).get("dataset", "")
    total = (d.settings or {}).get("total") or 0
    emitted = int(await redis().get(cursor_key(d.id)) or 0)
    ends = datetime.fromisoformat((d.settings or {}).get("ends_at", d.started_at.isoformat()))
    sim_now = clock.now() if clock else d.started_at
    span = (ends - d.started_at).total_seconds() or 1
    return {
        "disaster_id": str(d.id),
        "dataset": slug,
        "status": clock.status if clock else "idle",
        "speed": clock.speed if clock else 0,
        "sim_now": sim_now.isoformat(),
        "starts_at": d.started_at.isoformat(),
        "ends_at": ends.isoformat(),
        "progress": round(min(1.0, max(0.0, (sim_now - d.started_at).total_seconds() / span)), 4),
        "emitted": emitted,
        "total": total,
        "autopilot": bool((d.settings or {}).get("autopilot")),
    }


async def tick(session: AsyncSession, d: Disaster, wall_tick: int) -> None:
    """Advance one replay: emit due messages, move simulated crews, finish when done."""
    clock = await load_replay_clock(d.id)
    if clock is None or clock.status != "playing":
        return
    sim_now = clock.now()
    slug = (d.settings or {})["dataset"]
    rows = messages(slug)
    cursor = int(await redis().get(cursor_key(d.id)) or 0)
    due = []
    while cursor + len(due) < len(rows) and len(due) < MAX_PER_TICK:
        m = rows[cursor + len(due)]
        if datetime.fromisoformat(m["t"]) > sim_now:
            break
        due.append(m)
    ids = []
    for m in due:
        msg, created = await intake.ingest(
            session,
            intake.Incoming(
                disaster_id=d.id,
                channel="replay",
                text=m["text"],
                received_at=datetime.fromisoformat(m["t"]),
                external_id=f"{d.id}:{m['id']}",
                sender_phone=m.get("sender_phone"),
                pin=tuple(m["pin"]) if m.get("pin") else None,  # type: ignore[arg-type]
                meta={"original_channel": m["channel"], "dataset_message": m["id"]},
            ),
        )
        if created:
            ids.append(msg.id)
    if due:
        await redis().set(cursor_key(d.id), cursor + len(due))
        await intake.enqueue(ids)
    await _drive_crews(session, d, sim_now, publish_moves=wall_tick % 2 == 0)

    ends = datetime.fromisoformat((d.settings or {})["ends_at"])
    if cursor + len(due) >= len(rows) and sim_now >= ends + timedelta(hours=6):
        await save_replay_clock(d.id, ReplayClock("finished", clock.speed, sim_now, time.time()))
        await events.publish(d.id, "replay.state", await state(d))
    elif wall_tick % 4 == 0:
        await events.publish(d.id, "replay.state", await state(d))


async def _drive_crews(session: AsyncSession, d: Disaster, sim_now: datetime, publish_moves: bool) -> None:
    rows = list(
        await session.execute(
            select(Assignment, Team, Case)
            .join(Team, Team.id == Assignment.team_id)
            .join(Case, Case.id == Assignment.case_id)
            .where(Team.disaster_id == d.id, Team.is_virtual.is_(True), Assignment.status.in_(ASSIGNMENT_ACTIVE))
            .order_by(Assignment.team_id, Assignment.sequence)
        )
    )
    seen: set[uuid.UUID] = set()
    for a, team, case in rows:
        if team.id in seen:
            continue  # one stop at a time per crew
        seen.add(team.id)
        if a.status == "approved":
            await field.update(session, a, "started", SIM_TEAM, at=max(sim_now, a.approved_at or sim_now))
            continue
        if a.status == "started" and a.started_at:
            travel_s = a.travel_s or 600
            done = (sim_now - a.started_at).total_seconds() / max(travel_s, 1)
            if done >= 1:
                dest = geo.latlng(case.location)
                if dest:
                    await field.record_location(session, team, dest[0], dest[1], at=sim_now, store_history=False)
                await field.update(session, a, "reached", SIM_TEAM, at=a.started_at + timedelta(seconds=travel_s))
            elif publish_moves:
                coords = [(lat, lng) for lng, lat in (geo.line_coords(a.route) or [])]
                if len(coords) >= 2:
                    lat, lng, heading = travel.point_along(coords, done)
                    await field.record_location(
                        session, team, lat, lng, heading=heading, at=sim_now, store_history=False
                    )
            continue
        if a.status == "reached" and a.reached_at:
            service = travel.service_seconds(team.asset_type, case.people_count)
            if (sim_now - a.reached_at).total_seconds() >= service:
                await field.update(
                    session,
                    a,
                    "completed",
                    SIM_TEAM,
                    people_rescued=case.people_count or 2,
                    at=a.reached_at + timedelta(seconds=service),
                )


async def wipe(session: AsyncSession, d: Disaster) -> None:
    await redis().delete(replay_key(d.id), cursor_key(d.id))
    await session.execute(delete(Disaster).where(Disaster.id == d.id))
    await session.commit()
