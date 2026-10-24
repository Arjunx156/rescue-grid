"""Request-scoped auth: who is calling, what they may touch, and in which disaster."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.events import Actor
from app.core.db import get_session
from app.core.security import ACCESS_COOKIE, Claims, decode_access_token
from app.models import Disaster, DisasterOrganization, Team, User

Session = Annotated[AsyncSession, Depends(get_session)]
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-requested-with"


def _token(request: Request | WebSocket) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if token := request.cookies.get(ACCESS_COOKIE):
        return token
    if isinstance(request, WebSocket):
        return request.query_params.get("token")
    return None


def claims_from(request: Request | WebSocket) -> Claims | None:
    if isinstance(request, WebSocket) and (ticket := request.query_params.get("ticket")):
        return decode_access_token(ticket, typ="ws")
    token = _token(request)
    return decode_access_token(token) if token else None


async def principal(request: Request) -> Claims:
    claims = claims_from(request)
    if claims is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
    # cookies ride along on cross-site requests; a custom header cannot without CORS approval
    if request.method in UNSAFE and request.cookies.get(ACCESS_COOKIE) and not request.headers.get(CSRF_HEADER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing X-Requested-With header")
    return claims


Principal = Annotated[Claims, Depends(principal)]


def require(*roles: str) -> Callable[[Claims], Coroutine[Any, Any, Claims]]:
    async def dep(claims: Principal) -> Claims:
        if claims.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this")
        return claims

    return dep


Staff = Annotated[Claims, Depends(require("admin", "coordinator", "viewer"))]
Coordinator = Annotated[Claims, Depends(require("admin", "coordinator"))]
Admin = Annotated[Claims, Depends(require("admin"))]
FieldLead = Annotated[Claims, Depends(require("field_lead"))]


async def current_user(session: Session, claims: Principal) -> User:
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def actor(claims: Claims, label: str | None = None) -> Actor:
    return Actor("team" if claims.role == "field_lead" else "user", claims.user_id, label)


async def can_see(session: AsyncSession, claims: Claims, disaster_id: uuid.UUID) -> bool:
    if claims.role == "admin":
        return True
    if claims.role == "field_lead":
        if claims.team_id is None:
            return False
        return bool(
            await session.scalar(select(exists().where(Team.id == claims.team_id, Team.disaster_id == disaster_id)))
        )
    if claims.org_id is None:
        return False
    return bool(
        await session.scalar(
            select(
                exists().where(
                    DisasterOrganization.disaster_id == disaster_id,
                    DisasterOrganization.organization_id == claims.org_id,
                )
            )
        )
    )


async def disaster_or_404(session: AsyncSession, claims: Claims, disaster_id: uuid.UUID) -> Disaster:
    d = await session.get(Disaster, disaster_id)
    if d is None or not await can_see(session, claims, disaster_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such disaster")
    return d
