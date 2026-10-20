"""Every channel lands here: store the raw message, give the reporter a code, queue it.

Idempotent on (channel, external_id), so a WhatsApp retry or a re-uploaded CSV
never creates a second message.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import geo
from app.agents.rules import normalize
from app.core.crypto import lookup_hash, normalize_phone, phone_hash
from app.core.logging import log
from app.core.redis import STREAM_MAXLEN, STREAM_RAW, redis
from app.core.security import new_tracking_code
from app.models import SosMessage


@dataclass
class Incoming:
    disaster_id: uuid.UUID
    channel: str
    text: str
    received_at: datetime
    external_id: str | None = None
    sender_phone: str | None = None
    sender_name: str | None = None
    pin: tuple[float, float] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


async def ingest(session: AsyncSession, inc: Incoming) -> tuple[SosMessage, bool]:
    """(message, created). Commits; the caller enqueues with `enqueue` after."""
    if inc.external_id:
        existing = await session.scalar(
            select(SosMessage).where(SosMessage.channel == inc.channel, SosMessage.external_id == inc.external_id)
        )
        if existing:
            return existing, False
    phone = normalize_phone(inc.sender_phone)
    for _ in range(5):
        msg = SosMessage(
            disaster_id=inc.disaster_id,
            channel=inc.channel,
            external_id=inc.external_id,
            tracking_code=new_tracking_code(),
            sender_phone=phone,
            sender_phone_hash=phone_hash(phone),
            sender_name=inc.sender_name,
            raw_text=inc.text,
            text_hash=lookup_hash(normalize(inc.text)),
            raw_location=geo.point(*inc.pin) if inc.pin else None,
            received_at=inc.received_at,
            meta=inc.meta,
        )
        try:
            async with session.begin_nested():
                session.add(msg)
            await session.commit()
            return msg, True
        except IntegrityError as e:
            await session.rollback()
            if inc.external_id and "external_id" in str(e.orig):
                existing = await session.scalar(
                    select(SosMessage).where(
                        SosMessage.channel == inc.channel, SosMessage.external_id == inc.external_id
                    )
                )
                if existing:
                    return existing, False
            # otherwise a tracking-code collision (1 in ~28 million): draw again
    raise RuntimeError("could not allocate a tracking code")


async def enqueue(message_ids: list[uuid.UUID]) -> None:
    if not message_ids:
        return
    pipe = redis().pipeline(transaction=False)
    for mid in message_ids:
        pipe.xadd(STREAM_RAW, {"message_id": str(mid)}, maxlen=STREAM_MAXLEN, approximate=True)
    try:
        await pipe.execute()
    except Exception as e:  # noqa: BLE001 (the sweeper re-queues pending rows from Postgres)
        log.warning("intake.enqueue_failed", count=len(message_ids), error=str(e))
