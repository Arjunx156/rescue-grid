"""Live updates. One Redis Pub/Sub channel per disaster, masked per connection by role."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from urllib.parse import urlsplit

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from redis.asyncio.client import PubSub

from app.actions.events import dumps
from app.actions.serialize import SEES_PERSONAL
from app.actions.stats import counters
from app.core.clock import utcnow
from app.core.db import sessionmaker
from app.core.deps import can_see, claims_from
from app.core.logging import log
from app.core.redis import disaster_channel, redis, team_channel
from app.core.settings import get_settings

router = APIRouter()
PING_S = 25


def _trusted_origin(ws: WebSocket) -> bool:
    """Browsers always send Origin; refuse pages on other sites riding the session cookie."""
    origin = ws.headers.get("origin")
    if origin is None:
        return True  # not a browser, so there is no ambient cookie to abuse
    s = get_settings()
    allowed = {o.rstrip("/") for o in s.cors_origins} | {s.public_base_url.rstrip("/")}
    return origin.rstrip("/") in allowed or urlsplit(origin).netloc == ws.headers.get("host")


def _for_role(raw: str, personal: bool) -> str:
    """Viewers get the masked copy of a case; everyone else the full one."""
    if personal or '"masked"' not in raw:
        return raw
    msg = orjson.loads(raw)
    data = msg.get("data") or {}
    if "masked" in data:
        if "case" in data:
            data["case"] = data["masked"]
        elif "cases" in data:
            data["cases"] = data["masked"]
        data.pop("masked", None)
    return dumps(msg)


async def _pump(ws: WebSocket, pubsub: PubSub, personal: bool) -> None:
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        await ws.send_text(_for_role(message["data"], personal))


async def _ping(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(PING_S)
        await ws.send_text(dumps({"type": "ping", "at": utcnow()}))


async def _serve(ws: WebSocket, channels: list[str], personal: bool, hello: dict[str, object]) -> None:
    pubsub = redis().pubsub()
    await pubsub.subscribe(*channels)
    await ws.send_text(dumps(hello))
    tasks = [asyncio.create_task(_pump(ws, pubsub, personal)), asyncio.create_task(_ping(ws))]

    async def drain() -> None:
        # the client sends nothing meaningful; reading notices the disconnect
        while True:
            await ws.receive_text()

    tasks.append(asyncio.create_task(drain()))
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if (exc := t.exception()) and not isinstance(exc, WebSocketDisconnect):
                log.info("ws.closed", error=str(exc)[:200])
    finally:
        for t in tasks:
            t.cancel()
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe()
            await pubsub.aclose()


@router.websocket("/ws/disasters/{disaster_id}")
async def disaster_ws(ws: WebSocket, disaster_id: uuid.UUID) -> None:
    if not _trusted_origin(ws):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown origin")
        return
    claims = claims_from(ws)
    if claims is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Sign in")
        return
    async with sessionmaker()() as session:
        if not await can_see(session, claims, disaster_id):
            await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="No access")
            return
        snapshot = (await counters(session, disaster_id)).model_dump()
    await ws.accept()
    channels = [disaster_channel(disaster_id)]
    if claims.role == "field_lead" and claims.team_id:
        channels = [team_channel(claims.team_id)]  # field crews only hear about their own jobs
    await _serve(
        ws,
        channels,
        claims.role in SEES_PERSONAL,
        {"type": "hello", "data": {"counters": snapshot, "role": claims.role}, "at": utcnow()},
    )


@router.websocket("/ws/field")
async def field_ws(ws: WebSocket) -> None:
    if not _trusted_origin(ws):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown origin")
        return
    claims = claims_from(ws)
    if claims is None or claims.role != "field_lead" or claims.team_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Field team sign-in required")
        return
    await ws.accept()
    await _serve(
        ws,
        [team_channel(claims.team_id)],
        True,
        {"type": "hello", "data": {"team_id": str(claims.team_id)}, "at": utcnow()},
    )
