from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.actions import planning
from app.actions.serialize import assignment_out
from app.core.deps import Coordinator, Session, Staff, actor, disaster_or_404
from app.models import Assignment, DispatchPlan, Team
from app.models.tables import ASSIGNMENT_ACTIVE
from app.schemas.api import AssignmentOut, PlanOut

router = APIRouter(prefix="/api/v1", tags=["dispatch"])


@router.get("/dispatch/plan", response_model=PlanOut)
async def get_plan(disaster_id: uuid.UUID, claims: Staff, session: Session) -> PlanOut:
    d = await disaster_or_404(session, claims, disaster_id)
    return await planning.plan_out(session, d)


class ReplanIn(BaseModel):
    disaster_id: uuid.UUID


@router.post("/dispatch/replan", response_model=PlanOut)
async def replan(body: ReplanIn, claims: Coordinator, session: Session) -> PlanOut:
    d = await disaster_or_404(session, claims, body.disaster_id)
    await planning.build(session, d)
    return await planning.plan_out(session, d)


class ApproveIn(BaseModel):
    assignment_ids: list[uuid.UUID] | None = None


class ApproveOut(BaseModel):
    approved: list[AssignmentOut]


@router.post("/dispatch/plan/{plan_id}/approve", response_model=ApproveOut)
async def approve(plan_id: uuid.UUID, body: ApproveIn, claims: Coordinator, session: Session) -> ApproveOut:
    plan = await session.get(DispatchPlan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such plan")
    await disaster_or_404(session, claims, plan.disaster_id)
    if plan.status not in ("proposed", "approved"):
        raise HTTPException(status.HTTP_409_CONFLICT, "A newer plan replaced this one. Review it and approve again.")
    done = await planning.approve(session, plan.id, actor(claims), body.assignment_ids)
    calls = dict(
        list(await session.execute(select(Team.id, Team.call_sign).where(Team.disaster_id == plan.disaster_id)))
    )
    return ApproveOut(approved=[assignment_out(a, calls.get(a.team_id)) for a in done])


@router.get("/disasters/{disaster_id}/assignments", response_model=list[AssignmentOut])
async def active_assignments(disaster_id: uuid.UUID, claims: Staff, session: Session) -> list[AssignmentOut]:
    await disaster_or_404(session, claims, disaster_id)
    rows = await session.execute(
        select(Assignment, Team.call_sign)
        .join(Team, Team.id == Assignment.team_id)
        .where(Team.disaster_id == disaster_id, Assignment.status.in_(ASSIGNMENT_ACTIVE))
        .order_by(Assignment.team_id, Assignment.sequence)
    )
    return [assignment_out(a, cs) for a, cs in rows]
