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
    settings = get_settings()
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(claims.user_id),
        "role": claims.role,
        "org": str(claims.org_id) if claims.org_id else None,
        "sid": str(claims.session_id),
        "team": str(claims.team_id) if claims.team_id else None,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expires_min)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGO)


def decode_access_token(token: str) -> Claims | None:
    try:
        data = jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    if data.get("typ") != "access":
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
