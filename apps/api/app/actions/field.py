"""What field teams do: move, start, reach, rescue, or report they could not get through.

Simulated replay teams call exactly these functions, so a replay exercises the
same state machine as a real boat crew.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import events, geo, notify
from app.actions.events import Actor
from app.actions.serialize import assignment_out, case_out, team_out
from app.core.clock import disaster_now
from app.core.logging import log
from app.core.redis import redis
from app.models import Assignment, Case, Disaster, Team, TeamLocation
from app.models.tables import ASSIGNMENT_ACTIVE
from app.services import travel

ROAD_ASSETS = {"truck", "medical", "foot"}
NEXT = {
    "started": {"approved"},
    "reached": {"approved", "started"},
    "completed": {"approved", "started", "reached"},
    "failed": {"approved", "started", "reached"},
}


class TransitionError(ValueError):
    pass


async def current(session: AsyncSession, team: Team) -> tuple[Assignment | None, Assignment | None]:
    """(now, next): the active stop with the lowest sequence and the one after it."""
    rows = list(
        await session.scalars(
            select(Assignment)
            .where(Assignment.team_id == team.id, Assignment.status.in_(ASSIGNMENT_ACTIVE))
            .order_by(Assignment.sequence, Assignment.approved_at)
        )
    )
    return (rows[0] if rows else None, rows[1] if len(rows) > 1 else None)


async def update(
    session: AsyncSession,
    a: Assignment,
    status: str,
    actor: Actor,
    *,
    people_rescued: int | None = None,
    note: str | None = None,
    client_id: str | None = None,
    at: datetime | None = None,
) -> Assignment:
    # the offline queue may deliver the same tap twice; only the first counts
    if client_id and not await redis().set(f"idem:{client_id}", "1", nx=True, ex=86_400):
        return a
    if status == a.status:
        return a
    if a.status not in NEXT.get(status, set()):
        raise TransitionError(f"cannot go from {a.status} to {status}")
    case = await session.get(Case, a.case_id, with_for_update=True)
    team = await session.get(Team, a.team_id, with_for_update=True)
    assert case is not None and team is not None
    disaster = await session.get(Disaster, case.disaster_id)
    assert disaster is not None
    now = at or await disaster_now(disaster.id, disaster.status)
    payload: dict[str, object] = {"team": team.call_sign, "assignment_id": str(a.id)}

    if status == "started":
        a.status, a.started_at = "started", now
        case.status, team.status = "en_route", "en_route"
    elif status == "reached":
        a.status, a.reached_at = "reached", now
        a.started_at = a.started_at or now
        case.status, team.status = "on_scene", "on_scene"
    elif status == "completed":
        rescued = people_rescued if people_rescued is not None else (case.people_count or 1)
        a.status, a.completed_at, a.outcome_people_rescued, a.outcome_note = "completed", now, rescued, note
        case.people_rescued = (case.people_rescued or 0) + rescued
        remaining = (case.people_count or 0) - rescued
        if case.people_count and remaining > 0:
            # a boat of six at a house of ten: the rest go back in the queue
            case.people_count = remaining
            case.status, case.current_team_id = "queued", None
            payload["remaining"] = remaining
        else:
            case.status, case.rescued_at = "rescued", now
        payload["people_rescued"] = rescued
    elif status == "failed":
        a.status, a.completed_at, a.outcome_note = "failed", now, note
        case.status, case.current_team_id = "unreachable", None
        case.review_reasons = sorted(set(case.review_reasons or []) | {"team_could_not_reach"})
        if team.asset_type in ROAD_ASSETS:
            # a road team turned back: assume deep water so the next plan sends a boat
            case.flood_depth_m = max(case.flood_depth_m or 0, travel.MAX_DEPTH_M["truck"] + 0.1)
        payload["note"] = note
    case.version += 1
    events.record(session, case, f"field_{status}", actor, now, payload)
    await session.flush()

    if status in ("completed", "failed"):
        left = await session.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(Assignment.team_id == team.id, Assignment.status.in_(ASSIGNMENT_ACTIVE))
        )
        team.status = "assigned" if left else "available"
    await session.commit()

    await events.publish(
        disaster.id,
        "case.upsert",
        {
            "case": case_out(case, "coordinator").model_dump(mode="json"),
            "masked": case_out(case, "viewer").model_dump(mode="json"),
            "created": False,
        },
    )
    await events.publish(disaster.id, "team.upsert", team_out(team).model_dump(mode="json"))
    await events.publish(disaster.id, "assignment.upsert", assignment_out(a, team.call_sign).model_dump(mode="json"))
    if status == "completed":
        await events.publish(
            disaster.id,
            "toast",
            {
                "kind": "rescued",
                "case_id": str(case.id),
                "text": f"{team.call_sign} rescued {payload['people_rescued']}"
                + (f" · {case.locality}" if case.locality else ""),
            },
        )
    if status in ("completed", "failed"):
        await events.trigger_dispatch(disaster.id, f"field_{status}")
    if status == "completed" and case.status == "rescued" and disaster.status != "replay":
        try:
            await notify.case_rescued(session, case, team, now)
        except Exception as e:  # noqa: BLE001
            log.warning("notify.rescued_failed", error=str(e))
    return a


async def record_location(
    session: AsyncSession,
    team: Team,
    lat: float,
    lng: float,
    *,
    speed: float | None = None,
    heading: float | None = None,
    at: datetime | None = None,
    store_history: bool = True,
) -> None:
    disaster = await session.get(Disaster, team.disaster_id)
    assert disaster is not None
    now = at or await disaster_now(disaster.id, disaster.status)
    team.current_location = geo.point(lat, lng)
    team.location_updated_at = now
    if heading is not None:
        team.heading = heading
    if store_history:
        session.add(TeamLocation(team_id=team.id, location=geo.point(lat, lng), recorded_at=now, speed=speed))
    await session.commit()
    try:
        await redis().set(f"team:{team.id}:loc", f"{lat},{lng}", ex=300)
    except Exception:  # noqa: BLE001,S110 (the row is already saved)
        pass
    await events.publish(
        disaster.id,
        "team.location",
        {
            "id": str(team.id),
            "lat": lat,
            "lng": lng,
            "heading": team.heading,
            "at": now.isoformat(),
        },
    )
