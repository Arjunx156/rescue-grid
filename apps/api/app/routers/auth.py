from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, update

from app.actions.notify import send_whatsapp
from app.actions.serialize import user_out
from app.core.clock import utcnow
from app.core.crypto import normalize_phone, phone_hash
from app.core.deps import CurrentUser, Principal, Session
from app.core.logging import log
from app.core.redis import rate_limited, redis
from app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    ROLE_COOKIE,
    Claims,
    hash_password,
    issue_access_token,
    new_opaque_token,
    new_otp,
    token_digest,
    verify_password,
)
from app.core.settings import get_settings
from app.models import Invite, Organization, PushSubscription, Team, User, UserSession
from app.schemas.api import (
    AcceptInviteIn,
    LoginIn,
    OtpRequestIn,
    OtpVerifyIn,
    PushSubscriptionIn,
    SettingsPatch,
    UserOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
OTP_TTL_S = 600
OTP_ATTEMPTS = 5
DEMO_USERS = {
    "coordinator": "coordinator@demo.rescuegrid.in",
    "admin": "admin@demo.rescuegrid.in",
    "viewer": "viewer@demo.rescuegrid.in",
    "field_lead": "+910000000701",
}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _team_of(session: Session, user: User) -> uuid.UUID | None:
    if user.role != "field_lead":
        return None
    return await session.scalar(
        select(Team.id).where(Team.lead_user_id == user.id).order_by(Team.created_at.desc()).limit(1)
    )


async def _start_session(session: Session, response: Response, request: Request, user: User, kind: str) -> UserOut:
    s = get_settings()
    lifetime = timedelta(days=s.field_session_days) if kind == "field" else timedelta(hours=s.staff_session_hours)
    refresh = new_opaque_token()
    us = UserSession(
        user_id=user.id,
        refresh_hash=token_digest(refresh),
        kind=kind,
        user_agent=(request.headers.get("user-agent") or "")[:300],
        expires_at=utcnow() + lifetime,
    )
    session.add(us)
    user.last_login_at = utcnow()
    await session.flush()
    team_id = await _team_of(session, user)
    _set_cookies(response, Claims(user.id, user.role, user.organization_id, us.id, team_id), refresh, lifetime)
    await session.commit()
    org = await session.get(Organization, user.organization_id) if user.organization_id else None
    return user_out(user, org.name if org else None, team_id)


def _set_cookies(response: Response, claims: Claims, refresh: str, lifetime: timedelta) -> None:
    s = get_settings()
    common = {"secure": s.cookie_secure, "samesite": "lax", "domain": s.cookie_domain}
    response.set_cookie(
        ACCESS_COOKIE, issue_access_token(claims), httponly=True, path="/", max_age=s.jwt_expires_min * 60, **common
    )  # type: ignore[arg-type]
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, path="/api/v1/auth", max_age=int(lifetime.total_seconds()), **common
    )  # type: ignore[arg-type]
    # not a secret: lets the web app route a signed-in user before any API call
    response.set_cookie(
        ROLE_COOKIE, claims.role, httponly=False, path="/", max_age=int(lifetime.total_seconds()), **common
    )  # type: ignore[arg-type]


def _clear_cookies(response: Response) -> None:
    s = get_settings()
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, "/api/v1/auth"), (ROLE_COOKIE, "/")):
        response.delete_cookie(name, path=path, domain=s.cookie_domain)


def _session_ended(detail: str) -> JSONResponse:
    # a raised HTTPException drops headers set on the injected response, so build the 401 here
    response = JSONResponse({"detail": detail}, status_code=status.HTTP_401_UNAUTHORIZED)
    _clear_cookies(response)
    return response


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, session: Session) -> UserOut:
    if await rate_limited(f"rl:login:{_client_ip(request)}", 20, 600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait a few minutes.")
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is wrong")
    if user.role == "field_lead":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Field teams sign in with their phone")
    return await _start_session(session, response, request, user, "staff")


class OtpSent(BaseModel):
    sent: bool
    channel: str
    dev_code: str | None = None


@router.post("/otp/request", response_model=OtpSent)
async def otp_request(body: OtpRequestIn, request: Request, session: Session) -> OtpSent:
    phone = normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That does not look like a phone number")
    key = phone_hash(phone)
    if await rate_limited(f"rl:otp:{key}", 3, 600) or await rate_limited(f"rl:otp-ip:{_client_ip(request)}", 20, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many codes requested. Try again in 10 minutes.")
    user = await session.scalar(select(User).where(User.phone == phone, User.is_active.is_(True)))
    settings = get_settings()
    # same answer whether or not the number exists, so the endpoint cannot be used to find team phones
    if user is None or user.role != "field_lead":
        return OtpSent(sent=True, channel="whatsapp")
    code = new_otp()
    await redis().hset(f"otp:{key}", mapping={"digest": token_digest(code), "tries": 0})
    await redis().expire(f"otp:{key}", OTP_TTL_S)
    status_, _, error = await send_whatsapp(
        phone,
        {
            "type": "text",
            "text": {"body": f"Your Rescue Grid sign-in code is {code}. It expires in 10 minutes. Do not share it."},
        },
    )
    if status_ != "sent":
        log.info("otp.not_sent", reason=error)
    return OtpSent(sent=True, channel="whatsapp", dev_code=code if settings.otp_dev_echo else None)


@router.post("/otp/verify", response_model=UserOut)
async def otp_verify(body: OtpVerifyIn, request: Request, response: Response, session: Session) -> UserOut:
    phone = normalize_phone(body.phone)
    key = f"otp:{phone_hash(phone)}"
    stored = await redis().hgetall(key)
    if not stored:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code expired. Request a new one.")
    if int(stored.get("tries", 0)) >= OTP_ATTEMPTS:
        await redis().delete(key)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many wrong codes. Request a new one.")
    if stored["digest"] != token_digest(body.code):
        await redis().hincrby(key, "tries", 1)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code is not right")
    await redis().delete(key)
    user = await session.scalar(select(User).where(User.phone == phone, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No active team account for this phone")
    return await _start_session(session, response, request, user, "field")


@router.post("/refresh", response_model=UserOut)
async def refresh(request: Request, response: Response, session: Session) -> UserOut | JSONResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        return _session_ended("Session ended")
    us = await session.scalar(select(UserSession).where(UserSession.refresh_hash == token_digest(token)))
    if us is None or us.revoked_at or us.expires_at < utcnow():
        return _session_ended("Session ended")
    user = await session.get(User, us.user_id)
    if user is None or not user.is_active:
        return _session_ended("Account disabled")
    new = new_opaque_token()  # rotate on every use
    us.refresh_hash = token_digest(new)
    us.last_used_at = utcnow()
    team_id = await _team_of(session, user)
    _set_cookies(
        response, Claims(user.id, user.role, user.organization_id, us.id, team_id), new, us.expires_at - utcnow()
    )
    await session.commit()
    org = await session.get(Organization, user.organization_id) if user.organization_id else None
    return user_out(user, org.name if org else None, team_id)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, session: Session) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        await session.execute(
            update(UserSession).where(UserSession.refresh_hash == token_digest(token)).values(revoked_at=utcnow())
        )
        await session.commit()
    _clear_cookies(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser, claims: Principal, session: Session) -> UserOut:
    org = await session.get(Organization, user.organization_id) if user.organization_id else None
    return user_out(user, org.name if org else None, claims.team_id)


@router.patch("/me", response_model=UserOut)
async def update_me(body: SettingsPatch, user: CurrentUser, claims: Principal, session: Session) -> UserOut:
    if body.name:
        user.name = body.name
    if body.preferred_language:
        user.preferred_language = body.preferred_language
    await session.commit()
    org = await session.get(Organization, user.organization_id) if user.organization_id else None
    return user_out(user, org.name if org else None, claims.team_id)


@router.post("/me/push", status_code=204)
async def subscribe_push(body: PushSubscriptionIn, user: CurrentUser, session: Session) -> Response:
    existing = await session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if existing is None:
        session.add(
            PushSubscription(
                user_id=user.id,
                endpoint=body.endpoint,
                p256dh=body.keys.get("p256dh", ""),
                auth=body.keys.get("auth", ""),
            )
        )
    else:
        existing.user_id = user.id
    await session.commit()
    return Response(status_code=204)


@router.get("/push-key")
async def push_key() -> dict[str, str]:
    return {"key": get_settings().vapid_public_key}


class AuthOptions(BaseModel):
    demo: bool
    otp_via_whatsapp: bool


@router.get("/options", response_model=AuthOptions)
async def options() -> AuthOptions:
    s = get_settings()
    return AuthOptions(demo=s.demo_mode, otp_via_whatsapp=s.whatsapp_enabled)


class DemoIn(BaseModel):
    role: Literal["coordinator", "admin", "viewer", "field_lead"] = "coordinator"


@router.post("/demo", response_model=UserOut)
async def demo(body: DemoIn, request: Request, response: Response, session: Session) -> UserOut:
    if not get_settings().demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    ident = DEMO_USERS[body.role]
    q = (
        select(User).where(User.phone == ident)
        if body.role == "field_lead"
        else select(User).where(User.email == ident)
    )
    user = await session.scalar(q)
    if user is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Demo accounts are not seeded. Run just seed.")
    return await _start_session(session, response, request, user, "field" if body.role == "field_lead" else "staff")


class InviteInfo(BaseModel):
    email: str
    name: str
    role: str
    organization: str | None
    reset: bool = False


async def _open_invite(session: Session, token: str) -> Invite:
    inv = await session.scalar(select(Invite).where(Invite.token_hash == token_digest(token)))
    if inv is None or inv.accepted_at or inv.expires_at < utcnow():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link has expired or was already used")
    return inv


@router.get("/invite/{token}", response_model=InviteInfo)
async def invite_info(token: str, session: Session) -> InviteInfo:
    inv = await _open_invite(session, token)
    org = await session.get(Organization, inv.organization_id)
    return InviteInfo(
        email=inv.email, name=inv.name, role=inv.role, organization=org.name if org else None, reset=inv.kind == "reset"
    )


@router.post("/invite/accept", response_model=UserOut)
async def accept_invite(body: AcceptInviteIn, request: Request, response: Response, session: Session) -> UserOut:
    inv = await _open_invite(session, body.token)
    existing = await session.scalar(select(User).where(User.email == inv.email))
    if inv.kind == "reset":
        if existing is None or not existing.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "This account is no longer active")
        user = existing
        user.password_hash = hash_password(body.password)
        # a new password ends every other session, wherever it was
        await session.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    else:
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        user = User(
            email=inv.email,
            name=inv.name,
            role=inv.role,
            organization_id=inv.organization_id,
            password_hash=hash_password(body.password),
        )
        session.add(user)
    inv.accepted_at = utcnow()
    # one link used retires every other open link for the same person
    await session.execute(
        update(Invite)
        .where(Invite.email == inv.email, Invite.accepted_at.is_(None), Invite.id != inv.id)
        .values(expires_at=utcnow())
    )
    await session.flush()
    log.info("invite.accepted", kind=inv.kind, user=str(user.id))
    return await _start_session(session, response, request, user, "staff")
