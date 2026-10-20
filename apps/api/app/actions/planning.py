"""Dispatch plans: build from live state, persist as proposals, approve or override.

Nothing reaches a field team until a coordinator approves it (replay autopilot
is the one exception, and only for simulated teams).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import events, geo, notify, nowcast, resolve
from app.actions.events import SYSTEM, Actor
from app.actions.serialize import assignment_out, case_out, team_out
from app.core.clock import disaster_now
from app.core.logging import log
from app.core.settings import get_settings
from app.models import Assignment, Case, Disaster, DispatchPlan, FloodZone, Team
from app.models.tables import ASSIGNMENT_ACTIVE
from app.schemas.api import PlanOut, PlanStop
from app.services import dispatch, router, travel
from app.services.geocode import haversine_m

RESCUE_NEEDS = {"rescue", "evacuation", "boat", "medical"}
DISPATCHABLE = ("queued", "unreachable")


async def _avoid_rings(session: AsyncSession, disaster_id: uuid.UUID, max_depth: float) -> list[list[list[float]]]:
    """Flood rings a road asset must stay out of, simplified for the router."""
    zones = await session.scalars(
        select(FloodZone).where(FloodZone.disaster_id == disaster_id, FloodZone.depth_estimate_m > max_depth)
    )
    rings: list[list[list[float]]] = []
    for z in zones:
        g = to_shape(z.geom).simplify(0.001)
        for poly in getattr(g, "geoms", [g]):
            rings.append([[round(x, 5), round(y, 5)] for x, y in poly.exterior.coords])
    return rings[:20]


async def _team_starts(
    session: AsyncSession, teams: list[Team], now: datetime
) -> dict[uuid.UUID, tuple[float, float, int, int]]:
    """team -> (lat, lng, seconds until free, active stop count): busy teams start where their queue ends."""
    out: dict[uuid.UUID, tuple[float, float, int, int]] = {}
    active = list(
        await session.execute(
            select(Assignment, Case)
            .join(Case, Case.id == Assignment.case_id)
            .where(Assignment.team_id.in_([t.id for t in teams]), Assignment.status.in_(ASSIGNMENT_ACTIVE))
            .order_by(Assignment.team_id, Assignment.sequence)
        )
    )
    queues: dict[uuid.UUID, list[tuple[Assignment, Case]]] = {}
    for a, c in active:
        queues.setdefault(a.team_id, []).append((a, c))
    for t in teams:
        pos = geo.latlng(t.current_location) or geo.latlng(t.base_location)
        if pos is None:
            continue
        busy_s, lat, lng = 0.0, pos[0], pos[1]
        for a, c in queues.get(t.id, []):
            ll = geo.latlng(c.location)
            if ll is None:
                continue
            if a.status == "reached":
                busy_s += travel.service_seconds(t.asset_type, c.people_count) / 2
            else:
                d = float(haversine_m(lat, lng, ll[0], ll[1]))
                busy_s += float(travel.travel_seconds(t.asset_type, d)) + travel.service_seconds(
                    t.asset_type, c.people_count
                )
            lat, lng = ll
        out[t.id] = (lat, lng, int(busy_s), len(queues.get(t.id, [])))
    return out


async def build(session: AsyncSession, disaster: Disaster) -> DispatchPlan | None:
    settings = get_settings()
    now = await disaster_now(disaster.id, disaster.status)
    teams = list(await session.scalars(select(Team).where(Team.disaster_id == disaster.id, Team.status != "off_duty")))
    busy_cases = select(Assignment.case_id).where(Assignment.status.in_(ASSIGNMENT_ACTIVE))
    cases = list(
        await session.scalars(
            select(Case).where(
                Case.disaster_id == disaster.id,
                Case.status.in_(DISPATCHABLE),
                Case.location.is_not(None),
                Case.id.not_in(busy_cases),
            )
        )
    )
    cases = [c for c in cases if set(c.needs or ["rescue"]) & RESCUE_NEEDS]
    starts = await _team_starts(session, teams, now)
    dteams = [
        dispatch.DTeam(
            str(t.id), t.call_sign, t.asset_type, t.capacity, starts[t.id][0], starts[t.id][1], starts[t.id][2]
        )
        for t in teams
        if t.id in starts
    ]
    points = {str(c.id): ll for c in cases if (ll := geo.latlng(c.location))}
    # the water clock: plan against the water at arrival, and against each family's deadline
    profiles = await nowcast.depth_profiles(disaster.id, points, now)
    dcases = []
    for c in cases:
        ll = points.get(str(c.id))
        if ll:
            left = resolve.clock_minutes(c, now)
            dcases.append(
                dispatch.DCase(
                    str(c.id),
                    ll[0],
                    ll[1],
                    c.people_count,
                    c.urgency_score,
                    c.urgency_level,
                    travel.effective_depth(c.water_level, c.flood_depth_m),
                    c.in_flood_zone,
                    c.summary or "",
                    deadline_s=round(left * 60) if left is not None else None,
                    depth_profile=profiles.get(str(c.id), ()),
                )
            )
    previous = await session.scalar(
        select(DispatchPlan)
        .where(DispatchPlan.disaster_id == disaster.id, DispatchPlan.status == "proposed")
        .order_by(DispatchPlan.created_at.desc())
        .limit(1)
    )
    warm: dict[str, list[str]] = {}
    if previous:
        for a in await session.scalars(
            select(Assignment)
            .where(Assignment.plan_id == previous.id, Assignment.status == "proposed")
            .order_by(Assignment.sequence)
        ):
            warm.setdefault(str(a.team_id), []).append(str(a.case_id))

    # guided local search spends its whole budget, so size the budget to the problem
    limit = min(settings.dispatch_time_limit_s, 0.4 + 0.006 * len(dcases))
    if disaster.status == "replay":
        limit = min(limit, 1.0)
    result = await asyncio.to_thread(dispatch.plan, dteams, dcases, limit, warm or None)
    if result.status == "no_solution" and previous:
        # keep the last good plan and say so, rather than wiping the board
        previous.stats = {**previous.stats, "stale": True}
        await session.commit()
        await events.publish(disaster.id, "plan.stale", {"plan_id": str(previous.id)})
        return previous

    # replace the previous proposal
    old_ids = [
        p
        for p in await session.scalars(
            select(DispatchPlan.id).where(DispatchPlan.disaster_id == disaster.id, DispatchPlan.status == "proposed")
        )
    ]
    if old_ids:
        await session.execute(update(DispatchPlan).where(DispatchPlan.id.in_(old_ids)).values(status="superseded"))
        await session.execute(
            update(Assignment)
            .where(Assignment.plan_id.in_(old_ids), Assignment.status == "proposed")
            .values(status="cancelled")
        )

    by_case = {str(c.id): c for c in cases}
    by_team = {str(t.id): t for t in teams}
    dropped = sorted(
        (
            {"case_id": cid, "reason": why, "urgency": by_case[cid].urgency_score}
            for cid, why in result.dropped.items()
            if cid in by_case
        ),
        key=lambda d: -d["urgency"],
    )[:200]
    plan = DispatchPlan(
        disaster_id=disaster.id,
        created_by="optimizer",
        status="proposed",
        objective_value=result.objective,
        solver_ms=result.solver_ms,
        stats={
            "status": result.status,
            "cases_considered": len(dcases),
            "teams": len(dteams),
            "stops": len(result.stops),
            "people_covered": result.people_covered,
            "critical_covered": result.critical_covered,
            "critical_open": sum(1 for c in cases if c.urgency_level == "critical"),
            "dropped": dropped,
            "stale": False,
            "solver": "or-tools",
        },
    )
    session.add(plan)
    await session.flush()

    avoid_cache: dict[float, list[list[list[float]]]] = {}
    sem = asyncio.Semaphore(4)
    prev_pos = {str(tid): (s[0], s[1]) for tid, s in starts.items()}
    legs: list[tuple[dispatch.Stop, tuple[float, float], tuple[float, float], Team]] = []
    for stop in sorted(result.stops, key=lambda s: (s.team_id, s.sequence)):
        t = by_team[stop.team_id]
        dest = geo.latlng(by_case[stop.case_id].location)
        if dest is None:
            continue
        legs.append((stop, prev_pos[stop.team_id], dest, t))
        prev_pos[stop.team_id] = dest

    async def leg_route(stop: dispatch.Stop, a: tuple[float, float], b: tuple[float, float], t: Team) -> router.Route:
        depth = travel.MAX_DEPTH_M[t.asset_type]
        if depth not in avoid_cache and t.asset_type not in router.DIRECT_ASSETS:
            avoid_cache[depth] = await _avoid_rings(session, disaster.id, depth)
        async with sem:
            return await router.route(t.asset_type, a, b, avoid_cache.get(depth))

    routes = await asyncio.gather(*(leg_route(*leg) for leg in legs))
    for (stop, _a, _b, t), r in zip(legs, routes, strict=True):
        base_seq = starts[t.id][3]
        session.add(
            Assignment(
                case_id=uuid.UUID(stop.case_id),
                team_id=t.id,
                plan_id=plan.id,
                sequence=base_seq + stop.sequence,
                route=geo.line(r.coords),
                route_source=r.source,
                distance_m=r.distance_m,
                travel_s=r.duration_s if r.source in ("valhalla", "osrm") else stop.travel_s,
                eta=now + timedelta(seconds=stop.arrival_s),
                status="proposed",
                reasons=stop.reasons,
            )
        )
    await session.commit()
    log.info(
        "plan.built",
        disaster=str(disaster.id),
        stops=len(result.stops),
        ms=result.solver_ms,
        cases=len(dcases),
        teams=len(dteams),
    )
    await events.publish(disaster.id, "plan.updated", {"plan_id": str(plan.id), "stats": plan.stats})
    if disaster.status == "replay" and (disaster.settings or {}).get("autopilot"):
        await approve(session, plan.id, SYSTEM)
    return plan


async def plan_out(session: AsyncSession, disaster: Disaster) -> PlanOut:
    plan = await session.scalar(
        select(DispatchPlan)
        .where(DispatchPlan.disaster_id == disaster.id, DispatchPlan.status.in_(("proposed", "approved")))
        .order_by(DispatchPlan.created_at.desc())
        .limit(1)
    )
    if plan is None:
        return PlanOut(id=None, status="none", created_at=None, solver_ms=None, stats={}, stops=[], dropped=[])
    rows = await session.scalars(
        select(Assignment)
        .where(Assignment.plan_id == plan.id, Assignment.status.in_(("proposed", "approved")))
        .order_by(Assignment.team_id, Assignment.sequence)
    )
    stops = [
        PlanStop(
            assignment_id=a.id,
            case_id=a.case_id,
            team_id=a.team_id,
            sequence=a.sequence,
            status=a.status,
            eta=a.eta,
            distance_m=a.distance_m,
            travel_s=a.travel_s,
            reasons=a.reasons or [],
            route=geo.line_coords(a.route),
        )
        for a in rows
    ]
    return PlanOut(
        id=plan.id,
        status=plan.status,
        created_at=plan.created_at,
        solver_ms=plan.solver_ms,
        stats={k: v for k, v in plan.stats.items() if k != "dropped"},
        stops=stops,
        dropped=plan.stats.get("dropped", []),
    )


async def _activate(session: AsyncSession, a: Assignment, actor: Actor, now: datetime) -> tuple[Case, Team]:
    case = await session.get(Case, a.case_id, with_for_update=True)
    team = await session.get(Team, a.team_id, with_for_update=True)
    assert case is not None and team is not None
    a.status = "approved"
    a.approved_by = actor.id
    a.approved_at = now
    case.status = "assigned"
    case.current_team_id = team.id
    case.assigned_at = case.assigned_at or now
    case.version += 1
    if team.status in ("available", "returning"):
        team.status = "assigned"
    events.record(
        session,
        case,
        "assigned",
        actor,
        now,
        {
            "team": team.call_sign,
            "team_id": str(team.id),
            "eta": a.eta.isoformat() if a.eta else None,
            "reasons": a.reasons,
            "plan_id": str(a.plan_id) if a.plan_id else None,
        },
    )
    return case, team


async def approve(
    session: AsyncSession, plan_id: uuid.UUID, actor: Actor, assignment_ids: list[uuid.UUID] | None = None
) -> list[Assignment]:
    plan = await session.get(DispatchPlan, plan_id, with_for_update=True)
    if plan is None or plan.status not in ("proposed", "approved"):
        return []
    disaster = await session.get(Disaster, plan.disaster_id)
    assert disaster is not None
    now = await disaster_now(disaster.id, disaster.status)
    q = select(Assignment).where(Assignment.plan_id == plan.id, Assignment.status == "proposed")
    if assignment_ids:
        q = q.where(Assignment.id.in_(assignment_ids))
    chosen = list(await session.scalars(q.order_by(Assignment.sequence)))
    touched: list[tuple[Assignment, Case, Team]] = []
    for a in chosen:
        case = await session.get(Case, a.case_id)
        if case is None or case.status not in DISPATCHABLE:
            a.status = "cancelled"  # someone else got there first
            continue
        c, t = await _activate(session, a, actor, now)
        touched.append((a, c, t))
    remaining = await session.scalar(
        select(func.count())
        .select_from(Assignment)
        .where(Assignment.plan_id == plan.id, Assignment.status == "proposed")
    )
    if not remaining:
        plan.status = "approved"
        plan.approved_by = actor.id
        plan.approved_at = now
    await session.commit()
    await _announce(session, disaster, touched)
    await events.trigger_dispatch(disaster.id, "approved")
    return [a for a, _, _ in touched]


async def assign_manual(session: AsyncSession, case: Case, team: Team, actor: Actor) -> Assignment:
    disaster = await session.get(Disaster, case.disaster_id)
    assert disaster is not None
    now = await disaster_now(disaster.id, disaster.status)
    for old in await session.scalars(
        select(Assignment).where(Assignment.case_id == case.id, Assignment.status.in_(("proposed", *ASSIGNMENT_ACTIVE)))
    ):
        old.status = "cancelled"
    starts = await _team_starts(session, [team], now)
    start = starts.get(team.id)
    dest = geo.latlng(case.location)
    route = None
    if start and dest:
        avoid = (
            []
            if team.asset_type in router.DIRECT_ASSETS
            else await _avoid_rings(session, disaster.id, travel.MAX_DEPTH_M[team.asset_type])
        )
        route = await router.route(team.asset_type, (start[0], start[1]), dest, avoid)
    seq = (start[3] if start else 0) + 1
    a = Assignment(
        case_id=case.id,
        team_id=team.id,
        plan_id=None,
        sequence=seq,
        status="proposed",
        route=geo.line(route.coords) if route else None,
        route_source=route.source if route else None,
        distance_m=route.distance_m if route else None,
        travel_s=route.duration_s if route else None,
        eta=now + timedelta(seconds=(start[2] if start else 0) + (route.duration_s if route else 0)),
        reasons=["Assigned manually by coordinator"],
    )
    session.add(a)
    await session.flush()
    case.status = "queued" if case.status in ("unreachable", "needs_review") else case.status
    c, t = await _activate(session, a, actor, now)
    await session.commit()
    await _announce(session, disaster, [(a, c, t)])
    await events.trigger_dispatch(disaster.id, "manual_assign")
    return a


async def cancel(session: AsyncSession, a: Assignment, actor: Actor, reason: str = "Reassigned") -> None:
    """Undo an approval: the case goes back to the queue and the team is freed if idle."""
    case = await session.get(Case, a.case_id)
    team = await session.get(Team, a.team_id)
    assert case is not None and team is not None
    disaster = await session.get(Disaster, case.disaster_id)
    assert disaster is not None
    now = await disaster_now(disaster.id, disaster.status)
    a.status = "cancelled"
    a.outcome_note = reason
    if case.status in ("assigned", "en_route", "on_scene"):
        case.status = "queued"
        case.current_team_id = None
        case.version += 1
    events.record(session, case, "assignment_cancelled", actor, now, {"team": team.call_sign, "reason": reason})
    await session.flush()
    still = await session.scalar(
        select(func.count())
        .select_from(Assignment)
        .where(Assignment.team_id == team.id, Assignment.status.in_(ASSIGNMENT_ACTIVE))
    )
    if not still and team.status in ("assigned", "en_route", "on_scene"):
        team.status = "available"
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
    await events.publish_team(team.id, "assignment.cancelled", {"assignment_id": str(a.id)})
    await events.trigger_dispatch(disaster.id, "cancelled")


async def _announce(session: AsyncSession, disaster: Disaster, touched: list[tuple[Assignment, Case, Team]]) -> None:
    for a, case, team in touched:
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
        await events.publish(
            disaster.id, "assignment.upsert", assignment_out(a, team.call_sign).model_dump(mode="json")
        )
        await events.publish_team(team.id, "assignment.new", assignment_out(a, team.call_sign).model_dump(mode="json"))
    if touched:
        await events.publish(
            disaster.id, "plan.updated", {"plan_id": str(touched[0][0].plan_id) if touched[0][0].plan_id else None}
        )
    if disaster.status == "replay":
        return
    for a, case, team in touched:
        try:
            await notify.case_assigned(session, case, team, a.eta)
            await notify.push_team(
                session,
                team,
                f"New assignment · {case.urgency_level.capitalize()}",
                f"{case.summary or 'Rescue request'} · {case.locality or ''}".strip(" ·"),
                f"/field/assignment/{a.id}",
            )
        except Exception as e:  # noqa: BLE001 (a failed text must not undo an approved rescue)
            log.warning("notify.assign_failed", error=str(e))
