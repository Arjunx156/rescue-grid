"""The field team's view: one clear next job, its route, and big status buttons."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.actions import field
from app.actions.serialize import assignment_out, case_out
from app.core.deps import FieldLead, Session, actor
from app.models import Assignment, Case, Disaster, Team
from app.routers.teams import team_view
from app.schemas.api import AssignmentOut, AssignmentUpdate, CaseOut, TeamOut

router = APIRouter(prefix="/api/v1/field", tags=["field"])


class Job(BaseModel):
    assignment: AssignmentOut
    case: CaseOut


class FieldNow(BaseModel):
    team: TeamOut | None
    disaster: str | None
    current: Job | None
    next: Job | None


async def _my_team(session: Session, claims: FieldLead) -> Team | None:
    if claims.team_id:
        return await session.get(Team, claims.team_id)
    return await session.scalar(
        select(Team).where(Team.lead_user_id == claims.user_id).order_by(Team.created_at.desc()).limit(1)
    )


async def _job(session: Session, a: Assignment | None, call_sign: str) -> Job | None:
    if a is None:
        return None
    c = await session.get(Case, a.case_id)
    assert c is not None
    return Job(assignment=assignment_out(a, call_sign), case=case_out(c, "field_lead"))


@router.get("/assignments/current", response_model=FieldNow)
async def current(claims: FieldLead, session: Session) -> FieldNow:
    team = await _my_team(session, claims)
    if team is None:
        return FieldNow(team=None, disaster=None, current=None, next=None)
    now, nxt = await field.current(session, team)
    disaster = await session.get(Disaster, team.disaster_id)
    return FieldNow(
        team=(await team_view(session, [team], "field_lead"))[0],
        disaster=disaster.name if disaster else None,
        current=await _job(session, now, team.call_sign),
        next=await _job(session, nxt, team.call_sign),
    )


async def _mine(session: Session, claims: FieldLead, assignment_id: uuid.UUID) -> tuple[Assignment, Team]:
    a = await session.get(Assignment, assignment_id)
    team = await _my_team(session, claims)
    if a is None or team is None or a.team_id != team.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This assignment is not yours")
    return a, team


@router.get("/assignments/{assignment_id}", response_model=Job)
async def get_assignment(assignment_id: uuid.UUID, claims: FieldLead, session: Session) -> Job:
    a, team = await _mine(session, claims, assignment_id)
    job = await _job(session, a, team.call_sign)
    assert job is not None
    return job


@router.patch("/assignments/{assignment_id}", response_model=AssignmentOut)
async def update(
    assignment_id: uuid.UUID, body: AssignmentUpdate, claims: FieldLead, session: Session
) -> AssignmentOut:
    a, team = await _mine(session, claims, assignment_id)
    if a.status in ("cancelled", "completed", "failed"):
        if a.status == body.status:
            return assignment_out(a, team.call_sign)  # a retried tap from the offline queue
        raise HTTPException(status.HTTP_409_CONFLICT, f"This assignment is already {a.status}")
    try:
        a = await field.update(
            session,
            a,
            body.status,
            actor(claims, team.call_sign),
            people_rescued=body.people_rescued,
            note=body.note,
            client_id=body.client_id,
            at=body.at,
        )
    except field.TransitionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return assignment_out(a, team.call_sign)


@router.get("/history", response_model=list[Job])
async def history(claims: FieldLead, session: Session) -> list[Job]:
    team = await _my_team(session, claims)
    if team is None:
        return []
    rows = await session.scalars(
        select(Assignment)
        .where(Assignment.team_id == team.id, Assignment.status.in_(("completed", "failed")))
        .order_by(Assignment.completed_at.desc())
        .limit(100)
    )
    out = []
    for a in rows:
        if job := await _job(session, a, team.call_sign):
            out.append(job)
    return out
