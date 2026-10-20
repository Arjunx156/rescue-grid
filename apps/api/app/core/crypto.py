"""Field-level encryption for personal data (DPDP Act 2023).

Ciphertext lives in the column; a keyed hash beside it supports equality lookups
(same phone across reports) without decrypting anything.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.settings import get_settings


@lru_cache
def _fernet() -> MultiFernet:
    keys = get_settings().data_encryption_keys.get_secret_value().split(",")
    return MultiFernet([Fernet(k.strip().encode()) for k in keys if k.strip()])


def encrypt(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if token is None:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # a purged or foreign value; never crash a read path over it
        return None


def normalize_phone(raw: str | None) -> str | None:
    """Best-effort E.164 for Indian numbers; returns None when there is no plausible number."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if 8 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def lookup_hash(value: str | None) -> str | None:
    if not value:
        return None
    key = get_settings().data_hash_key.get_secret_value().encode()
    return hmac.new(key, value.strip().lower().encode(), hashlib.sha256).hexdigest()


def phone_hash(raw: str | None) -> str | None:
    return lookup_hash(normalize_phone(raw))


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return f"{phone[:3]}•••••{phone[-3:]}" if len(phone) > 6 else "•••"


class EncryptedText(TypeDecorator[str]):
    """Text column that is encrypted at rest and plain in Python."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        return encrypt(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        return decrypt(value)
