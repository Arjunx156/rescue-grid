from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.actions import events, field, geo
from app.actions.serialize import team_out
from app.core.crypto import normalize_phone
from app.core.deps import Principal, Session, Staff, disaster_or_404
from app.models import Assignment, Organization, Team, TeamLocation, User
from app.models.tables import ASSIGNMENT_ACTIVE
from app.schemas.api import LocationIn, TeamIn, TeamOut, TeamPatch

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


class TeamCreate(TeamIn):
    disaster_id: uuid.UUID


async def team_view(session: Session, teams: list[Team], role: str) -> list[TeamOut]:
    if not teams:
        return []
    ids = [t.id for t in teams]
    orgs = dict(list(await session.execute(select(Organization.id, Organization.name))))
    leads = {
        u.id: u
        for u in await session.scalars(
            select(User).where(User.id.in_([t.lead_user_id for t in teams if t.lead_user_id]))
        )
    }
    active: dict[uuid.UUID, Assignment] = {}
    queued: dict[uuid.UUID, int] = {}
    for a in await session.scalars(
        select(Assignment)
        .where(Assignment.team_id.in_(ids), Assignment.status.in_(ASSIGNMENT_ACTIVE))
        .order_by(Assignment.sequence)
    ):
        if a.team_id not in active:
            active[a.team_id] = a
        else:
            queued[a.team_id] = queued.get(a.team_id, 0) + 1
    return [
        team_out(
            t,
            organization=orgs.get(t.organization_id) if t.organization_id else t.notes,
            lead=leads.get(t.lead_user_id) if t.lead_user_id else None,
            active=active.get(t.id),
            queued=queued.get(t.id, 0),
            role=role,
        )
        for t in teams
    ]


@router.get("", response_model=list[TeamOut])
async def list_teams(disaster_id: uuid.UUID, claims: Staff, session: Session) -> list[TeamOut]:
    await disaster_or_404(session, claims, disaster_id)
    teams = list(await session.scalars(select(Team).where(Team.disaster_id == disaster_id).order_by(Team.call_sign)))
    return await team_view(session, teams, claims.role)


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(body: TeamCreate, claims: Principal, session: Session) -> TeamOut:
    if claims.role not in ("admin", "coordinator"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only coordinators register teams")
    await disaster_or_404(session, claims, body.disaster_id)
    lead_id = None
    if body.lead_phone:
        phone = normalize_phone(body.lead_phone)
        if phone is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Lead phone is not valid")
        lead = await session.scalar(select(User).where(User.phone == phone))
        if lead is None:
            lead = User(
                phone=phone,
                name=body.lead_name or body.call_sign,
                role="field_lead",
                organization_id=body.organization_id or claims.org_id,
            )
            session.add(lead)
            await session.flush()
        elif lead.role != "field_lead":
            raise HTTPException(status.HTTP_409_CONFLICT, "That phone belongs to a staff account")
        lead_id = lead.id
    pos = geo.point(body.lat, body.lng) if body.lat is not None and body.lng is not None else None
    t = Team(
        disaster_id=body.disaster_id,
        organization_id=body.organization_id or claims.org_id,
        call_sign=body.call_sign.upper(),
        asset_type=body.asset_type,
        capacity=body.capacity,
        lead_user_id=lead_id,
        status="off_duty",
        current_location=pos,
        base_location=pos,
        base_name=body.base_name,
    )
    session.add(t)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Call sign {body.call_sign.upper()} is taken") from e
    out = (await team_view(session, [t], claims.role))[0]
    await events.publish(t.disaster_id, "team.upsert", out.model_dump(mode="json"))
    return out


async def _team_for(session: Session, claims: Principal, team_id: uuid.UUID) -> Team:
    t = await session.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    if claims.role == "field_lead":
        if t.lead_user_id != claims.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your team")
    elif claims.role in ("admin", "coordinator"):
        await disaster_or_404(session, claims, t.disaster_id)
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this")
    return t


@router.patch("/{team_id}", response_model=TeamOut)
async def patch_team(team_id: uuid.UUID, body: TeamPatch, claims: Principal, session: Session) -> TeamOut:
    t = await _team_for(session, claims, team_id)
    if body.status:
        busy = await session.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(Assignment.team_id == t.id, Assignment.status.in_(ASSIGNMENT_ACTIVE))
        )
        if body.status == "off_duty" and busy:
            raise HTTPException(status.HTTP_409_CONFLICT, "Finish or hand back the current assignment first")
        if not busy:  # mid-task, the task drives the status
            t.status = body.status
    if claims.role != "field_lead":
        if body.capacity:
            t.capacity = body.capacity
        if body.notes is not None:
            t.notes = body.notes
    if body.lat is not None and body.lng is not None:
        t.current_location = geo.point(body.lat, body.lng)
    await session.commit()
    out = (await team_view(session, [t], claims.role))[0]
    await events.publish(t.disaster_id, "team.upsert", out.model_dump(mode="json"))
    if t.status == "available":
        await events.trigger_dispatch(t.disaster_id, "team_available")
    return out


@router.post("/{team_id}/location", status_code=204)
async def post_location(team_id: uuid.UUID, body: LocationIn, claims: Principal, session: Session) -> None:
    t = await _team_for(session, claims, team_id)
    await field.record_location(
        session, t, body.lat, body.lng, speed=body.speed, heading=body.heading, at=body.recorded_at
    )


class TrackPoint(BaseModel):
    lat: float
    lng: float
    at: str


@router.get("/{team_id}/track", response_model=list[TrackPoint])
async def track(team_id: uuid.UUID, claims: Staff, session: Session, limit: int = 200) -> list[TrackPoint]:
    t = await session.get(Team, team_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    await disaster_or_404(session, claims, t.disaster_id)
    rows = await session.scalars(
        select(TeamLocation)
        .where(TeamLocation.team_id == t.id)
        .order_by(TeamLocation.recorded_at.desc())
        .limit(min(limit, 2000))
    )
    out = []
    for r in rows:
        ll = geo.latlng(r.location)
        if ll:
            out.append(TrackPoint(lat=ll[0], lng=ll[1], at=r.recorded_at.isoformat()))
    return out[::-1]
