from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.actions import events, geo
from app.actions.serialize import case_out, disaster_out, flood_zone_out, review_pair_out
from app.actions.stats import counters
from app.core.clock import disaster_now, utcnow
from app.core.deps import Coordinator, Principal, Session, Staff, disaster_or_404
from app.models import Case, Disaster, DisasterOrganization, FloodZone, ReviewPair
from app.schemas.api import (
    CaseOut,
    Counters,
    DisasterIn,
    DisasterOut,
    DisasterPatch,
    FloodZoneIn,
    FloodZoneOut,
    ReviewPairOut,
)

router = APIRouter(prefix="/api/v1", tags=["disasters"])

LEVEL_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
OPEN = ("new", "needs_review", "queued", "assigned", "en_route", "on_scene", "unreachable")


@router.get("/disasters", response_model=list[DisasterOut])
async def list_disasters(claims: Principal, session: Session) -> list[DisasterOut]:
    q = select(Disaster).order_by((Disaster.status == "closed").asc(), Disaster.started_at.desc())
    if claims.role != "admin":
        if claims.org_id is None:
            return []
        q = q.join(DisasterOrganization, DisasterOrganization.disaster_id == Disaster.id).where(
            DisasterOrganization.organization_id == claims.org_id
        )
    out = []
    for d in await session.scalars(q):
        out.append(disaster_out(d, await disaster_now(d.id, d.status)))
    return out


@router.post("/disasters", response_model=DisasterOut, status_code=201)
async def create_disaster(body: DisasterIn, claims: Coordinator, session: Session) -> DisasterOut:
    if claims.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins create disasters")
    d = Disaster(
        name=body.name,
        description=body.description,
        status="active",
        area=geo.multipolygon(body.area) if body.area else None,
    )
    session.add(d)
    await session.flush()
    if claims.org_id:
        session.add(DisasterOrganization(disaster_id=d.id, organization_id=claims.org_id))
    await session.commit()
    return disaster_out(d, utcnow())


@router.get("/disasters/{disaster_id}", response_model=DisasterOut)
async def get_disaster(disaster_id: uuid.UUID, claims: Principal, session: Session) -> DisasterOut:
    d = await disaster_or_404(session, claims, disaster_id)
    return disaster_out(d, await disaster_now(d.id, d.status))


@router.patch("/disasters/{disaster_id}", response_model=DisasterOut)
async def patch_disaster(
    disaster_id: uuid.UUID, body: DisasterPatch, claims: Coordinator, session: Session
) -> DisasterOut:
    d = await disaster_or_404(session, claims, disaster_id)
    if claims.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins change a disaster")
    if body.name:
        d.name = body.name
    if body.description is not None:
        d.description = body.description
    if body.area:
        d.area = geo.multipolygon(body.area)
    if body.status and body.status != d.status and d.status != "replay":
        d.status = body.status
        d.ended_at = utcnow() if body.status == "closed" else None
    await session.commit()
    out = disaster_out(d, await disaster_now(d.id, d.status))
    await events.publish(d.id, "disaster.updated", out.model_dump(mode="json"))
    return out


@router.get("/disasters/{disaster_id}/counters", response_model=Counters)
async def get_counters(disaster_id: uuid.UUID, claims: Principal, session: Session) -> Counters:
    await disaster_or_404(session, claims, disaster_id)
    return await counters(session, disaster_id)


@router.get("/disasters/{disaster_id}/cases", response_model=list[CaseOut])
async def list_cases(
    disaster_id: uuid.UUID,
    claims: Staff,
    session: Session,
    status_: Annotated[str | None, Query(alias="status", description="comma separated, or 'open' / 'all'")] = "open",
    min_score: int = 0,
    level: str | None = None,
    bbox: Annotated[str | None, Query(description="minLng,minLat,maxLng,maxLat")] = None,
    q: str | None = None,
    limit: Annotated[int, Query(le=5000)] = 3000,
) -> list[CaseOut]:
    await disaster_or_404(session, claims, disaster_id)
    stmt = select(Case).where(Case.disaster_id == disaster_id, Case.urgency_score >= min_score)
    if status_ == "open":
        stmt = stmt.where(Case.status.in_(OPEN))
    elif status_ and status_ != "all":
        stmt = stmt.where(Case.status.in_(status_.split(",")))
    else:
        stmt = stmt.where(Case.status != "duplicate")
    if level:
        stmt = stmt.where(Case.urgency_level.in_(level.split(",")))
    if bbox:
        try:
            x1, y1, x2, y2 = (float(v) for v in bbox.split(","))
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bbox is minLng,minLat,maxLng,maxLat") from e
        stmt = stmt.where(func.ST_Intersects(Case.location, func.ST_MakeEnvelope(x1, y1, x2, y2, 4326)))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Case.tracking_code.ilike(like),
                Case.locality.ilike(like),
                Case.address_text.ilike(like),
                Case.summary.ilike(like),
            )
        )
    stmt = stmt.order_by(Case.urgency_score.desc(), Case.first_reported_at.asc()).limit(limit)
    return [case_out(c, claims.role) for c in await session.scalars(stmt)]


class ReviewOut(BaseModel):
    cases: list[CaseOut]
    pairs: list[ReviewPairOut]
    pair_cases: list[CaseOut]


@router.get("/review", response_model=ReviewOut)
async def review(disaster_id: uuid.UUID, claims: Staff, session: Session) -> ReviewOut:
    await disaster_or_404(session, claims, disaster_id)
    cases = list(
        await session.scalars(
            select(Case)
            .where(
                Case.disaster_id == disaster_id,
                Case.status.in_(OPEN),
                func.cardinality(Case.review_reasons) > 0,
            )
            .order_by(Case.urgency_score.desc())
            .limit(500)
        )
    )
    pairs = list(
        await session.scalars(
            select(ReviewPair)
            .where(ReviewPair.disaster_id == disaster_id, ReviewPair.status == "open")
            .order_by(ReviewPair.score.desc())
            .limit(200)
        )
    )
    ids = {p.case_a_id for p in pairs} | {p.case_b_id for p in pairs}
    pair_cases = list(await session.scalars(select(Case).where(Case.id.in_(ids)))) if ids else []
    live = {c.id for c in pair_cases if c.status not in ("duplicate", "closed", "false_alarm")}
    pairs = [p for p in pairs if p.case_a_id in live and p.case_b_id in live]
    return ReviewOut(
        cases=[case_out(c, claims.role) for c in cases],
        pairs=[review_pair_out(p) for p in pairs],
        pair_cases=[case_out(c, claims.role) for c in pair_cases],
    )


@router.get("/disasters/{disaster_id}/flood-zones", response_model=list[FloodZoneOut])
async def flood_zones(disaster_id: uuid.UUID, claims: Principal, session: Session) -> list[FloodZoneOut]:
    await disaster_or_404(session, claims, disaster_id)
    rows = await session.scalars(
        select(FloodZone)
        .where(FloodZone.disaster_id == disaster_id)
        .order_by(FloodZone.depth_estimate_m.desc().nulls_last())
    )
    return [flood_zone_out(z) for z in rows]


@router.post("/disasters/{disaster_id}/flood-zones", response_model=FloodZoneOut, status_code=201)
async def add_flood_zone(
    disaster_id: uuid.UUID, body: FloodZoneIn, claims: Coordinator, session: Session
) -> FloodZoneOut:
    await disaster_or_404(session, claims, disaster_id)
    try:
        geom = geo.multipolygon(body.geometry)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Bad geometry: {e}") from e
    z = FloodZone(
        disaster_id=disaster_id, name=body.name, geom=geom, depth_estimate_m=body.depth_estimate_m, source=body.source
    )
    session.add(z)
    await session.commit()
    out = flood_zone_out(z)
    await events.publish(disaster_id, "flood_zones.updated", {})
    await events.trigger_dispatch(disaster_id, "flood_zones")
    return out


@router.delete("/flood-zones/{zone_id}", status_code=204)
async def delete_flood_zone(zone_id: uuid.UUID, claims: Coordinator, session: Session) -> Response:
    z = await session.get(FloodZone, zone_id)
    if z is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such zone")
    await disaster_or_404(session, claims, z.disaster_id)
    disaster_id = z.disaster_id
    await session.delete(z)
    await session.commit()
    await events.publish(disaster_id, "flood_zones.updated", {})
    return Response(status_code=204)
