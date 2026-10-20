from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.actions import audit
from app.actions.serialize import user_out
from app.core.clock import utcnow
from app.core.deps import Admin, Session
from app.core.logging import log
from app.core.security import new_opaque_token, token_digest
from app.core.settings import get_settings
from app.models import Invite, Organization, User, UserSession
from app.schemas.api import InviteIn, UserOut

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
INVITE_DAYS = 7


class AuditOut(BaseModel):
    events: int
    intact: bool
    head: str
    break_at: int | None = None
    reason: str | None = None


@router.get("/audit", response_model=AuditOut)
async def audit_report(disaster_id: uuid.UUID, claims: Admin, session: Session) -> AuditOut:
    """Recompute the disaster's audit chain: any edited or missing event shows where it broke."""
    r = await audit.verify(session, disaster_id)
    b = r.first_break
    return AuditOut(
        events=r.events, intact=r.intact, head=r.head, break_at=b.seq if b else None, reason=b.reason if b else None
    )


@router.get("/users", response_model=list[UserOut])
async def users(claims: Admin, session: Session) -> list[UserOut]:
    orgs = dict(list(await session.execute(select(Organization.id, Organization.name))))
    rows = await session.scalars(select(User).order_by(User.role, User.name))
    return [user_out(u, orgs.get(u.organization_id) if u.organization_id else None) for u in rows]


class UserPatch(BaseModel):
    role: Literal["admin", "coordinator", "viewer", "field_lead"] | None = None
    is_active: bool | None = None
    organization_id: uuid.UUID | None = None


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(user_id: uuid.UUID, body: UserPatch, claims: Admin, session: Session) -> UserOut:
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    if u.id == claims.user_id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot demote or disable yourself")
    if body.role:
        u.role = body.role
    if body.organization_id:
        u.organization_id = body.organization_id
    if body.is_active is not None:
        u.is_active = body.is_active
        if not body.is_active:
            await session.execute(
                update(UserSession)
                .where(UserSession.user_id == u.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
    await session.commit()
    return user_out(u)


@router.delete("/users/{user_id}/sessions", status_code=204)
async def revoke_sessions(user_id: uuid.UUID, claims: Admin, session: Session) -> Response:
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()
    return Response(status_code=204)


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    link: str | None = None


@router.post("/invites", response_model=InviteOut, status_code=201)
async def invite(body: InviteIn, claims: Admin, session: Session) -> InviteOut:
    email = body.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account")
    token = new_opaque_token()
    inv = Invite(
        email=email,
        name=body.name,
        role=body.role,
        organization_id=body.organization_id or claims.org_id,
        token_hash=token_digest(token),
        invited_by=claims.user_id,
        expires_at=utcnow() + timedelta(days=INVITE_DAYS),
    )
    session.add(inv)
    await session.commit()
    link = f"{get_settings().public_base_url.rstrip('/')}/invite/{token}"
    # no mail server in v1: the admin copies the link; it is shown once and stored only as a hash
    log.info("invite.created", email=email, role=body.role)
    return InviteOut(
        id=inv.id, email=email, name=inv.name, role=inv.role, expires_at=inv.expires_at, accepted_at=None, link=link
    )


RESET_HOURS = 24


@router.post("/users/{user_id}/reset-link", response_model=InviteOut, status_code=201)
async def reset_link(user_id: uuid.UUID, claims: Admin, session: Session) -> InviteOut:
    # a one-time link through the invite page; using it sets a new password and signs out every device
    u = await session.get(User, user_id)
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such active user")
    if not u.email:
        raise HTTPException(status.HTTP_409_CONFLICT, "Field teams sign in with a code sent to their phone")
    org_id = u.organization_id or claims.org_id
    if org_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Give this person an organisation first")
    token = new_opaque_token()
    inv = Invite(
        email=u.email,
        name=u.name,
        role=u.role,
        organization_id=org_id,
        token_hash=token_digest(token),
        kind="reset",
        invited_by=claims.user_id,
        expires_at=utcnow() + timedelta(hours=RESET_HOURS),
    )
    session.add(inv)
    await session.commit()
    log.info("password.reset_link", user=str(u.id), by=str(claims.user_id))
    link = f"{get_settings().public_base_url.rstrip('/')}/invite/{token}"
    return InviteOut(
        id=inv.id, email=u.email, name=u.name, role=u.role, expires_at=inv.expires_at, accepted_at=None, link=link
    )


@router.get("/invites", response_model=list[InviteOut])
async def invites(claims: Admin, session: Session) -> list[InviteOut]:
    # reset links are not invitations, so they stay out of the pending list
    rows = await session.scalars(
        select(Invite).where(Invite.kind == "invite").order_by(Invite.created_at.desc()).limit(200)
    )
    return [
        InviteOut(id=i.id, email=i.email, name=i.name, role=i.role, expires_at=i.expires_at, accepted_at=i.accepted_at)
        for i in rows
    ]


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    type: Literal["govt", "ngo", "volunteer"]


@router.get("/organizations", response_model=list[OrgOut])
async def organizations(claims: Admin, session: Session) -> list[OrgOut]:
    return [
        OrgOut(id=o.id, name=o.name, type=o.type)
        for o in await session.scalars(select(Organization).order_by(Organization.name))
    ]


@router.post("/organizations", response_model=OrgOut, status_code=201)
async def create_org(body: OrgIn, claims: Admin, session: Session) -> OrgOut:
    o = Organization(name=body.name, type=body.type)
    session.add(o)
    await session.commit()
    return OrgOut(id=o.id, name=o.name, type=o.type)
