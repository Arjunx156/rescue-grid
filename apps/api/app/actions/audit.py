"""Check a disaster's audit chain: every event intact, none missing, none added out of turn.

The database chains each case event to the one before it and refuses edits (see the
audit chain migration). Here the chain is recomputed from the stored rows in one
query, so a deleted, reordered or forged event shows up as the first link that fails.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditHead

CHAIN = text(
    """
    SELECT seq, hash, prev_hash,
           case_event_digest(prev_hash, e) AS recomputed,
           lag(hash) OVER (ORDER BY seq) AS before
    FROM case_events e
    WHERE disaster_id = :disaster
    ORDER BY seq
    """
)


@dataclass(frozen=True)
class Break:
    seq: int
    reason: str


@dataclass(frozen=True)
class Report:
    events: int
    intact: bool
    head: str
    first_break: Break | None


async def verify(session: AsyncSession, disaster_id: uuid.UUID) -> Report:
    rows = list(await session.execute(CHAIN, {"disaster": disaster_id}))
    head = await session.get(AuditHead, disaster_id)
    expected = 0
    for seq, digest, prev, recomputed, before in rows:
        expected += 1
        if seq != expected:
            return _broken(rows, head, Break(seq, f"event {expected} is missing"))
        if prev != (before or ""):
            return _broken(rows, head, Break(seq, "does not follow the event before it"))
        if digest != recomputed:
            return _broken(rows, head, Break(seq, "was changed after it was written"))
    if head is not None and head.seq != expected:
        return _broken(rows, head, Break(expected + 1, f"events after {expected} are missing"))
    return Report(len(rows), True, head.hash if head else "", None)


def _broken(rows: list, head: AuditHead | None, why: Break) -> Report:
    return Report(len(rows), False, head.hash if head else "", why)
