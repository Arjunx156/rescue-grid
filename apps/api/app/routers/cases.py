from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.actions import cases as case_actions
from app.actions import planning
from app.actions.serialize import assignment_out, case_out, event_out, review_pair_out, source_out
from app.core.deps import Coordinator, Session, Staff, actor, disaster_or_404
from app.models import Assignment, Case, CaseEvent, Extraction, ReviewPair, SosMessage, Team
from app.schemas.api import AssignIn, AssignmentOut, CaseDetail, CaseOut, CasePatch, MergeIn

router = APIRouter(prefix="/api/v1", tags=["cases"])


async def _case(session: Session, claims: object, case_id: uuid.UUID) -> Case:
    c = await session.get(Case, case_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such case")
    await disaster_or_404(session, claims, c.disaster_id)  # type: ignore[arg-type]
    return c


@router.get("/cases/{case_id}", response_model=CaseDetail)
async def get_case(case_id: uuid.UUID, claims: Staff, session: Session) -> CaseDetail:
    c = await _case(session, claims, case_id)
    rows = await session.execute(
        select(SosMessage, Extraction)
        .join(Extraction, Extraction.sos_message_id == SosMessage.id, isouter=True)
        .where(SosMessage.case_id == c.id)
        .order_by(SosMessage.received_at)
    )
    sources = [source_out(m, e, claims.role) for m, e in rows]
    evs = await session.scalars(
        select(CaseEvent).where(CaseEvent.case_id == c.id).order_by(CaseEvent.created_at, CaseEvent.id)
    )
    assigns = await session.execute(
        select(Assignment, Team.call_sign)
        .join(Team, Team.id == Assignment.team_id)
        .where(Assignment.case_id == c.id, Assignment.status != "cancelled")
        .order_by(Assignment.created_at.desc())
    )
    pairs = await session.scalars(
        select(ReviewPair).where(
            ReviewPair.status == "open", (ReviewPair.case_a_id == c.id) | (ReviewPair.case_b_id == c.id)
        )
    )
    base = case_out(c, claims.role).model_dump()
    return CaseDetail(
        **base,
        sources=sources,
        events=[event_out(e) for e in evs],
        assignments=[assignment_out(a, cs) for a, cs in assigns],
        review_pairs=[review_pair_out(p) for p in pairs],
    )


@router.patch("/cases/{case_id}", response_model=CaseOut)
async def patch_case(case_id: uuid.UUID, body: CasePatch, claims: Coordinator, session: Session) -> CaseOut:
    c = await _case(session, claims, case_id)
    if (body.lat is None) != (body.lng is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Send both lat and lng")
    try:
        c = await case_actions.patch(session, c, body, actor(claims))
    except case_actions.ConflictError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Someone else just changed this case ({e}). Reload.") from e
    return case_out(c, claims.role)


@router.post("/cases/{case_id}/merge", response_model=CaseOut)
async def merge(case_id: uuid.UUID, body: MergeIn, claims: Coordinator, session: Session) -> CaseOut:
    keep = await _case(session, claims, case_id)
    drop = await _case(session, claims, body.other_case_id)
    try:
        keep = await case_actions.merge_cases(session, keep, drop, actor(claims))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return case_out(keep, claims.role)


@router.post("/cases/{case_id}/unmerge", response_model=CaseOut)
async def unmerge(case_id: uuid.UUID, claims: Coordinator, session: Session) -> CaseOut:
    drop = await _case(session, claims, case_id)
    try:
        drop = await case_actions.unmerge(session, drop, actor(claims))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return case_out(drop, claims.role)


@router.post("/cases/{case_id}/assign", response_model=AssignmentOut)
async def assign(case_id: uuid.UUID, body: AssignIn, claims: Coordinator, session: Session) -> AssignmentOut:
    c = await _case(session, claims, case_id)
    team = await session.get(Team, body.team_id)
    if team is None or team.disaster_id != c.disaster_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team in this disaster")
    if c.status in ("rescued", "closed", "duplicate", "false_alarm"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Case is {c.status.replace('_', ' ')}")
    if c.location is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Set the location before assigning a team")
    a = await planning.assign_manual(session, c, team, actor(claims))
    return assignment_out(a, team.call_sign)


@router.post("/assignments/{assignment_id}/cancel", status_code=204)
async def cancel_assignment(assignment_id: uuid.UUID, claims: Coordinator, session: Session) -> Response:
    a = await session.get(Assignment, assignment_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such assignment")
    await _case(session, claims, a.case_id)
    if a.status not in ("proposed", "approved", "started", "reached"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Assignment is already {a.status}")
    await planning.cancel(session, a, actor(claims), "Cancelled by coordinator")
    return Response(status_code=204)


@router.post("/review-pairs/{pair_id}/dismiss", status_code=204)
async def dismiss_pair(pair_id: uuid.UUID, claims: Coordinator, session: Session) -> Response:
    p = await session.get(ReviewPair, pair_id)
    if p is None or p.status != "open":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No open pair")
    await disaster_or_404(session, claims, p.disaster_id)
    await case_actions.dismiss_pair(session, p, actor(claims))
    return Response(status_code=204)
