from __future__ import annotations

import hashlib
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.settings import get_settings

_hasher = PasswordHasher()
ALGO = "HS256"
ACCESS_COOKIE = "rg_at"
REFRESH_COOKIE = "rg_rt"
ROLE_COOKIE = "rg_role"
WS_TICKET_S = 60


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


@dataclass(frozen=True)
class Claims:
    user_id: uuid.UUID
    role: str
    org_id: uuid.UUID | None
    session_id: uuid.UUID
    team_id: uuid.UUID | None


def issue_access_token(claims: Claims, now: datetime | None = None) -> str:
    return _encode(claims, "access", timedelta(minutes=get_settings().jwt_expires_min), now)


def issue_ws_ticket(claims: Claims) -> str:
    """A short-lived token for the socket URL, for when the API is on another site and the cookie cannot follow."""
    return _encode(claims, "ws", timedelta(seconds=WS_TICKET_S))


def _encode(claims: Claims, typ: str, ttl: timedelta, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(claims.user_id),
        "role": claims.role,
        "org": str(claims.org_id) if claims.org_id else None,
        "sid": str(claims.session_id),
        "team": str(claims.team_id) if claims.team_id else None,
        "typ": typ,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, get_settings().jwt_secret.get_secret_value(), algorithm=ALGO)


def decode_access_token(token: str, typ: str = "access") -> Claims | None:
    try:
        data = jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    if data.get("typ") != typ:
        return None
    return Claims(
        user_id=uuid.UUID(data["sub"]),
        role=data["role"],
        org_id=uuid.UUID(data["org"]) if data.get("org") else None,
        session_id=uuid.UUID(data["sid"]),
        team_id=uuid.UUID(data["team"]) if data.get("team") else None,
    )


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O/1/I/L: read aloud over a phone


def new_tracking_code() -> str:
    return "RG-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))
