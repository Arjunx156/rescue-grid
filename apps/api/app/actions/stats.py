"""Live counters for the top bar and the numbers on the analytics page."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import events, geo
from app.core.clock import disaster_now
from app.core.redis import redis
from app.models import Assignment, Case, Disaster, SosMessage, Team
from app.schemas.api import Counters

OPEN = ("new", "needs_review", "queued", "assigned", "en_route", "on_scene", "unreachable")


async def counters(session: AsyncSession, disaster_id: uuid.UUID) -> Counters:
    c = (
        await session.execute(
            select(
                func.count().filter(Case.status.in_(OPEN)),
                func.count().filter(Case.status.in_(OPEN), Case.urgency_level == "critical"),
                func.count().filter(Case.status == "needs_review"),
                func.count().filter(Case.status.in_(("assigned", "en_route", "on_scene"))),
                func.count().filter(Case.status == "rescued"),
                func.coalesce(func.sum(Case.people_rescued), 0),
            ).where(Case.disaster_id == disaster_id)
        )
    ).one()
    t = (
        await session.execute(
            select(
                func.count().filter(Team.status.in_(("assigned", "en_route", "on_scene"))),
                func.count().filter(Team.status != "off_duty"),
            ).where(Team.disaster_id == disaster_id)
        )
    ).one()
    messages = await session.scalar(
        select(func.count()).select_from(SosMessage).where(SosMessage.disaster_id == disaster_id)
    )
    return Counters(
        open=c[0],
        critical=c[1],
        needs_review=c[2],
        assigned=c[3],
        rescued=c[4],
        people_rescued=int(c[5] or 0),
        teams_active=t[0],
        teams_on_duty=t[1],
        messages=messages or 0,
    )


async def publish_counters(session: AsyncSession, disaster_id: uuid.UUID) -> None:
    """At most a few times a second per disaster, however busy intake gets."""
    if not await redis().set(f"counters:throttle:{disaster_id}", "1", nx=True, px=700):
        return
    await events.publish(disaster_id, "counters", (await counters(session, disaster_id)).model_dump())


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


async def summary(session: AsyncSession, disaster: Disaster) -> dict[str, Any]:
    now = await disaster_now(disaster.id, disaster.status)
    rows = list(
        await session.execute(
            select(
                Case.id,
                Case.status,
                Case.urgency_level,
                Case.first_reported_at,
                Case.assigned_at,
                Case.rescued_at,
                Case.source_count,
                Case.people_rescued,
                Case.people_count,
            ).where(Case.disaster_id == disaster.id)
        )
    )
    real = [r for r in rows if r.status != "duplicate"]
    to_assign = [(r.assigned_at - r.first_reported_at).total_seconds() / 60 for r in real if r.assigned_at]
    to_assign_crit = [
        (r.assigned_at - r.first_reported_at).total_seconds() / 60
        for r in real
        if r.assigned_at and r.urgency_level == "critical"
    ]
    critical = [r for r in real if r.urgency_level == "critical"]
    reached_3h = 0
    for r in critical:
        if r.rescued_at and r.rescued_at - r.first_reported_at <= timedelta(hours=3):
            reached_3h += 1
    messages = (
        await session.scalar(select(func.count()).select_from(SosMessage).where(SosMessage.disaster_id == disaster.id))
        or 0
    )
    by_status: dict[str, int] = {}
    by_level: dict[str, int] = {}
    for r in real:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.status in OPEN:
            by_level[r.urgency_level] = by_level.get(r.urgency_level, 0) + 1
    channel = func.coalesce(SosMessage.meta["original_channel"].astext, SosMessage.channel)
    channels = dict(
        list(
            await session.execute(
                select(channel, func.count()).where(SosMessage.disaster_id == disaster.id).group_by(channel)
            )
        )
    )
    teams = list(
        await session.execute(
            select(Team.status, func.count()).where(Team.disaster_id == disaster.id).group_by(Team.status)
        )
    )
    return {
        "now": now.isoformat(),
        "messages": messages,
        "cases": len(real),
        "duplicates_removed": messages - len(real) if messages else 0,
        "dedup_ratio": round(1 - len(real) / messages, 3) if messages else 0,
        "median_minutes_to_assign": _round(_median(to_assign)),
        "median_minutes_to_assign_critical": _round(_median(to_assign_crit)),
        "critical_total": len(critical),
        "critical_reached_3h": reached_3h,
        "critical_reached_3h_pct": round(reached_3h / len(critical), 3) if critical else None,
        "people_rescued": int(sum(r.people_rescued or 0 for r in real)),
        "by_status": by_status,
        "by_level": by_level,
        "channels": channels,
        "teams": dict(teams),
        "timeseries": await timeseries(session, disaster, now),
    }


def _round(v: float | None) -> float | None:
    return round(v, 1) if v is not None else None


async def timeseries(session: AsyncSession, disaster: Disaster, now: datetime) -> list[dict[str, Any]]:
    """Hourly reported / assigned / rescued counts since the first report."""
    first = await session.scalar(select(func.min(SosMessage.received_at)).where(SosMessage.disaster_id == disaster.id))
    if first is None:
        return []

    async def per_hour(column: Any) -> dict[datetime, int]:
        b = func.date_trunc("hour", column)
        rows = await session.execute(
            select(b, func.count())
            .where(Case.disaster_id == disaster.id, column.is_not(None), Case.status != "duplicate")
            .group_by(b)
        )
        return {k: v for k, v in rows}

    reported = await per_hour(Case.first_reported_at)
    assigned = await per_hour(Case.assigned_at)
    rescued = await per_hour(Case.rescued_at)
    out = []
    t = first.replace(minute=0, second=0, microsecond=0)
    end = min(now, first + timedelta(days=7))
    while t <= end:
        out.append(
            {
                "hour": t.isoformat(),
                "reported": reported.get(t, 0),
                "assigned": assigned.get(t, 0),
                "rescued": rescued.get(t, 0),
            }
        )
        t += timedelta(hours=1)
    return out


async def heatmap(session: AsyncSession, disaster_id: uuid.UUID) -> list[list[float]]:
    rows = await session.execute(
        select(Case.location, Case.urgency_score).where(
            Case.disaster_id == disaster_id, Case.location.is_not(None), Case.status != "duplicate"
        )
    )
    out = []
    for loc, score in rows:
        ll = geo.latlng(loc)
        if ll:
            out.append([round(ll[1], 5), round(ll[0], 5), round(max(score, 5) / 100, 2)])
    return out


async def team_utilisation(session: AsyncSession, disaster_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(
            Team.call_sign,
            Team.asset_type,
            func.count(Assignment.id).filter(Assignment.status == "completed"),
            func.coalesce(func.sum(Assignment.outcome_people_rescued), 0),
            func.avg(cast(func.extract("epoch", Assignment.reached_at - Assignment.started_at), Float)).filter(
                Assignment.reached_at.is_not(None)
            ),
        )
        .join(Assignment, Assignment.team_id == Team.id, isouter=True)
        .where(Team.disaster_id == disaster_id)
        .group_by(Team.id)
        .order_by(Team.call_sign)
    )
    return [
        {
            "call_sign": cs,
            "asset_type": at,
            "completed": n,
            "people_rescued": int(p or 0),
            "avg_travel_min": round(t / 60, 1) if t else None,
        }
        for cs, at, n, p, t in rows
    ]
