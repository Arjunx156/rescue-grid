"""Audit log rows and live fan-out. Every state change goes through here."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.logging import log
from app.core.redis import STREAM_DISPATCH, STREAM_MAXLEN, disaster_channel, redis, team_channel
from app.models import Case, CaseEvent


@dataclass(frozen=True)
class Actor:
    type: str  # system | user | team
    id: uuid.UUID | None = None
    label: str | None = None


SYSTEM = Actor("system", None, "Rescue Grid")


def dumps(obj: Any) -> str:
    return orjson.dumps(obj, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_UUID).decode()


def record(
    session: AsyncSession,
    case: Case,
    event_type: str,
    actor: Actor,
    at: datetime,
    payload: dict[str, Any] | None = None,
) -> CaseEvent:
    ev = CaseEvent(
        case_id=case.id,
        disaster_id=case.disaster_id,
        actor_type=actor.type,
        actor_id=actor.id,
        actor_label=actor.label,
        event_type=event_type,
        payload=payload or {},
        created_at=at,
    )
    session.add(ev)
    return ev


async def publish(disaster_id: uuid.UUID | str, kind: str, data: Any) -> None:
    """Best effort: a dead Redis must never fail the write that already committed."""
    try:
        await redis().publish(disaster_channel(disaster_id), dumps({"type": kind, "data": data, "at": utcnow()}))
    except Exception as e:  # noqa: BLE001 (the database is the source of truth; clients resync)
        log.warning("publish.failed", kind=kind, error=str(e))


async def publish_team(team_id: uuid.UUID | str, kind: str, data: Any) -> None:
    try:
        await redis().publish(team_channel(team_id), dumps({"type": kind, "data": data, "at": utcnow()}))
    except Exception as e:  # noqa: BLE001
        log.warning("publish.failed", kind=kind, error=str(e))


async def trigger_dispatch(disaster_id: uuid.UUID | str, reason: str) -> None:
    try:
        await redis().xadd(
            STREAM_DISPATCH,
            {"disaster_id": str(disaster_id), "reason": reason},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("dispatch.trigger_failed", error=str(e))
