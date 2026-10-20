"""Public endpoints: report an emergency, follow its status. No account, no personal data back."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.actions import geo, intake
from app.core.clock import disaster_now, utcnow
from app.core.deps import Session
from app.core.redis import rate_limited
from app.models import Assignment, Case, Disaster, SosMessage, Team
from app.models.tables import ASSIGNMENT_ACTIVE
from app.schemas.api import PublicState, PublicStatus, SosIn

router = APIRouter(prefix="/api/v1/sos", tags=["public"])

NEED_WORDS = {
    "rescue": "Rescue",
    "medical": "Medical help",
    "food": "Food",
    "water": "Drinking water",
    "boat": "Boat",
    "evacuation": "Evacuation",
    "power": "Power or phone charge",
}


class SosContext(BaseModel):
    available: bool
    disaster_id: uuid.UUID | None = None
    name: str | None = None
    center: list[float] | None = None
    bbox: list[float] | None = None


class SosCreated(BaseModel):
    tracking_code: str
    status_url: str
    received_at: datetime


async def _live_disaster(session: Session, lat: float | None = None, lng: float | None = None) -> Disaster | None:
    q = select(Disaster).where(Disaster.status == "active").order_by(Disaster.started_at.desc())
    if lat is not None and lng is not None:
        inside = await session.scalar(q.where(func.ST_Contains(Disaster.area, geo.point(lat, lng))).limit(1))
        if inside:
            return inside
    return await session.scalar(q.limit(1))


@router.get("/context", response_model=SosContext)
async def context(session: Session) -> SosContext:
    d = await _live_disaster(session)
    if d is None:
        return SosContext(available=False)
    c = geo.center(d.area)
    return SosContext(
        available=True, disaster_id=d.id, name=d.name, center=list(c) if c else None, bbox=geo.bbox(d.area)
    )


@router.post("", response_model=SosCreated, status_code=201)
async def report(body: SosIn, request: Request, session: Session) -> SosCreated:
    ip = request.client.host if request.client else "unknown"
    if body.website:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not send")  # a bot filled the hidden field
    if await rate_limited(f"rl:sos:{ip}", 10, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many reports from this connection. Call 112.")
    d = await _live_disaster(session, body.lat, body.lng)
    if d is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "No emergency is being coordinated here right now. Call 112."
        )
    parts = [body.text.strip()]
    if body.people:
        parts.append(f"{body.people} people")
    if body.needs:
        parts.append("Needs: " + ", ".join(NEED_WORDS.get(n, n) for n in body.needs))
    if body.name:
        parts.append(f"Contact {body.name}")
    if body.phone:
        parts.append(body.phone)
    received = await disaster_now(d.id, d.status)
    msg, _ = await intake.ingest(
        session,
        intake.Incoming(
            disaster_id=d.id,
            channel="web_form",
            text=". ".join(parts),
            received_at=received,
            sender_phone=body.phone,
            sender_name=body.name,
            pin=(body.lat, body.lng) if body.lat is not None and body.lng is not None else None,
            meta={"form": True, "language": body.language, "people": body.people, "needs": body.needs},
        ),
    )
    await intake.enqueue([msg.id])
    return SosCreated(tracking_code=msg.tracking_code, status_url=f"/sos/{msg.tracking_code}", received_at=received)


STATUS: dict[str, PublicState] = {
    "new": "received",
    "needs_review": "reviewing",
    "queued": "queued",
    "assigned": "assigned",
    "en_route": "en_route",
    "on_scene": "on_scene",
    "rescued": "rescued",
    "closed": "closed",
    "false_alarm": "closed",
    "unreachable": "unreachable",
    "duplicate": "queued",
}


@router.get("/{code}", response_model=PublicStatus)
async def track(code: str, request: Request, session: Session) -> PublicStatus:
    ip = request.client.host if request.client else "unknown"
    if await rate_limited(f"rl:track:{ip}", 120, 600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many lookups")
    code = code.strip().upper()
    msg = await session.scalar(select(SosMessage).where(SosMessage.tracking_code == code))
    case = None
    if msg is None:
        case = await session.scalar(select(Case).where(Case.tracking_code == code))
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No request with this code")
        received_at = case.first_reported_at
        disaster_id = case.disaster_id
    else:
        received_at, disaster_id = msg.received_at, msg.disaster_id
        if msg.case_id:
            case = await session.get(Case, msg.case_id)
    for _ in range(5):  # merged into the family's main case
        if case is None or case.merged_into_id is None:
            break
        case = await session.get(Case, case.merged_into_id)
    disaster = await session.get(Disaster, disaster_id)
    steps = [{"key": "received", "at": received_at}]
    team, eta = None, None
    state: PublicState = "received"
    if case is not None:
        state = STATUS.get(case.status, "queued")
        steps.append({"key": "located", "at": case.created_at})
        if case.assigned_at:
            steps.append({"key": "assigned", "at": case.assigned_at})
        row = (
            await session.execute(
                select(Assignment, Team.call_sign)
                .join(Team, Team.id == Assignment.team_id)
                .where(Assignment.case_id == case.id, Assignment.status.in_((*ASSIGNMENT_ACTIVE, "completed")))
                .order_by(Assignment.created_at.desc())
                .limit(1)
            )
        ).first()
        if row:
            a, team = row
            eta = a.eta if a.status in ASSIGNMENT_ACTIVE else None
            if a.started_at:
                steps.append({"key": "en_route", "at": a.started_at})
            if a.reached_at:
                steps.append({"key": "on_scene", "at": a.reached_at})
        if case.rescued_at:
            steps.append({"key": "rescued", "at": case.rescued_at})
    updated = max((s["at"] for s in steps if s["at"]), default=utcnow())
    return PublicStatus(
        tracking_code=code,
        status=state,
        steps=steps,
        team_call_sign=team,
        eta=eta,  # type: ignore[arg-type]
        updated_at=updated,
        disaster=disaster.name if disaster else "",
    )
