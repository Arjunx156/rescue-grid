"""Background work, all in one process: intake, dispatch, replay, the flood nowcast, and housekeeping.

Run with `python -m app.workers`, or inside the API with WORKERS_INLINE=true for a
single-container deploy. Redis Streams consumer groups make it safe to run
several worker processes side by side.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from redis.exceptions import ResponseError
from sqlalchemy import select, update

from app.actions import intake, nowcast, planning, replay, resolve, stats
from app.core.clock import utcnow
from app.core.db import sessionmaker
from app.core.logging import configure_logging, log
from app.core.redis import STREAM_DISPATCH, STREAM_RAW, redis
from app.core.settings import get_settings
from app.models import Case, Disaster, Extraction, OutboundMessage, SosMessage
from app.services import hydro

CONSUMER = f"{socket.gethostname()}-{os.getpid()}"
INTAKE_GROUP = "resolvers"
DISPATCH_GROUP = "planners"
INTAKE_CONCURRENCY = 4


async def _group(stream: str, group: str) -> None:
    with contextlib.suppress(ResponseError):  # BUSYGROUP: already there
        await redis().xgroup_create(stream, group, id="0", mkstream=True)


async def _resolve_one(entry_id: str, message_id: str, sem: asyncio.Semaphore) -> None:
    async with sem:
        mid = uuid.UUID(message_id)
        async with sessionmaker()() as session:
            try:
                case = await resolve.process(session, mid)
                if case is not None:
                    await stats.publish_counters(session, case.disaster_id)
            except Exception as e:  # noqa: BLE001 (one bad message must not stop the line)
                log.exception("intake.failed", message=message_id, error=str(e)[:300])
                await resolve.mark_failed(session, mid, str(e))
        await redis().xack(STREAM_RAW, INTAKE_GROUP, entry_id)


async def intake_consumer() -> None:
    await _group(STREAM_RAW, INTAKE_GROUP)
    sem = asyncio.Semaphore(INTAKE_CONCURRENCY)
    inflight: set[asyncio.Task[None]] = set()
    last_claim = 0.0
    while True:
        streams: Any = []
        if time.time() - last_claim > 30:
            # pick up entries a crashed worker read but never acknowledged
            last_claim = time.time()
            claim: Any = await redis().xautoclaim(STREAM_RAW, INTAKE_GROUP, CONSUMER, min_idle_time=60_000, count=50)
            claimed = claim[1]
            if claimed:
                streams = [(STREAM_RAW, claimed)]
        if not streams:
            streams = await redis().xreadgroup(INTAKE_GROUP, CONSUMER, {STREAM_RAW: ">"}, count=16, block=2000) or []
        for _, entries in streams:
            for entry_id, fields in entries:
                if not fields or "message_id" not in fields:
                    await redis().xack(STREAM_RAW, INTAKE_GROUP, entry_id)
                    continue
                task = asyncio.create_task(_resolve_one(entry_id, fields["message_id"], sem))
                inflight.add(task)
                task.add_done_callback(inflight.discard)


async def dispatch_consumer() -> None:
    await _group(STREAM_DISPATCH, DISPATCH_GROUP)
    debounce = get_settings().dispatch_debounce_s
    waiting: dict[str, float] = {}
    while True:
        resp: Any = await redis().xreadgroup(DISPATCH_GROUP, CONSUMER, {STREAM_DISPATCH: ">"}, count=100, block=1000)
        for _, entries in resp or []:
            for entry_id, fields in entries:
                waiting.setdefault(fields.get("disaster_id", ""), time.time())
                await redis().xack(STREAM_DISPATCH, DISPATCH_GROUP, entry_id)
        for did, since in list(waiting.items()):
            if time.time() - since < debounce:
                continue
            del waiting[did]
            # one planner per disaster at a time, across all worker processes
            if not await redis().set(f"dispatch:lock:{did}", CONSUMER, nx=True, ex=60):
                waiting[did] = time.time()
                continue
            try:
                async with sessionmaker()() as session:
                    d = await session.get(Disaster, uuid.UUID(did))
                    if d is not None and d.status in ("active", "replay"):
                        await planning.build(session, d)
                        await stats.publish_counters(session, d.id)
            except Exception as e:  # noqa: BLE001
                log.exception("dispatch.failed", disaster=did, error=str(e)[:300])
            finally:
                await redis().delete(f"dispatch:lock:{did}")


async def replay_runner() -> None:
    n = 0
    while True:
        n += 1
        try:
            async with sessionmaker()() as session:
                for d in list(await session.scalars(select(Disaster).where(Disaster.status == "replay"))):
                    if not await redis().set(f"replay:lock:{d.id}", CONSUMER, nx=True, px=2000):
                        continue
                    try:
                        await replay.tick(session, d, n)
                    finally:
                        await redis().delete(f"replay:lock:{d.id}")
        except Exception as e:  # noqa: BLE001
            log.exception("replay.tick_failed", error=str(e)[:300])
        await asyncio.sleep(0.4)


NOWCAST_LEASE_S = 60


async def nowcast_runner() -> None:
    """The water clock for every live disaster. One process owns a disaster's ensemble at a time.
    The owner renews its lease every pass and gives it up on shutdown; if it dies instead, the
    lease lapses within a minute and the next owner rebuilds the ensemble from the reports."""
    hydro.use_threads(get_settings().nowcast_threads)
    held: set[str] = set()
    try:
        while True:
            try:
                async with sessionmaker()() as session:
                    live = select(Disaster).where(Disaster.status.in_(("active", "replay")))
                    for d in list(await session.scalars(live)):
                        lease = f"nowcast:owner:{d.id}"
                        if not await redis().set(lease, CONSUMER, ex=NOWCAST_LEASE_S, nx=True):
                            if await redis().get(lease) != CONSUMER:
                                continue
                            await redis().expire(lease, NOWCAST_LEASE_S)
                        held.add(lease)
                        await nowcast.cycle(session, d)
            except Exception as e:  # noqa: BLE001
                log.exception("nowcast.failed", error=str(e)[:300])
            await asyncio.sleep(3)
    finally:
        with contextlib.suppress(Exception):
            for lease in held:
                if await redis().get(lease) == CONSUMER:
                    await redis().delete(lease)


async def purge_expired() -> int:
    """DPDP Act: personal fields go 90 days after a disaster closes. The operational record stays."""
    cutoff = utcnow() - timedelta(days=get_settings().retention_days)
    async with sessionmaker()() as session:
        due = list(
            await session.scalars(
                select(Disaster).where(
                    Disaster.status == "closed", Disaster.ended_at < cutoff, Disaster.purged_at.is_(None)
                )
            )
        )
        for d in due:
            msg_ids = select(SosMessage.id).where(SosMessage.disaster_id == d.id)
            case_ids = select(Case.id).where(Case.disaster_id == d.id)
            await session.execute(
                update(SosMessage)
                .where(SosMessage.disaster_id == d.id)
                .values(sender_phone=None, sender_name=None, raw_text=None, purged_at=utcnow())
            )
            await session.execute(
                update(Extraction)
                .where(Extraction.sos_message_id.in_(msg_ids))
                .values(contact_name=None, raw_json={}, embedding=None)
            )
            await session.execute(
                update(Case)
                .where(Case.disaster_id == d.id)
                .values(
                    contact_phone=None,
                    contact_name=None,
                    contact_phone_hashes=[],
                    sender_phone_hashes=[],
                    embedding=None,
                )
            )
            await session.execute(
                update(OutboundMessage).where(OutboundMessage.case_id.in_(case_ids)).values(to_phone=None, body="")
            )
            d.purged_at = utcnow()
            log.info("retention.purged", disaster=str(d.id))
        await session.commit()
        return len(due)


async def housekeeping() -> None:
    ticks = 0
    while True:
        ticks += 1
        try:
            await redis().set("worker:heartbeat", str(time.time()), ex=60)
            async with sessionmaker()() as session:
                live = list(await session.scalars(select(Disaster).where(Disaster.status.in_(("active", "replay")))))
                for d in live:
                    # replays run fast, so their waiting time grows fast too
                    if (d.status == "replay" and ticks % 2 == 0) or ticks % 12 == 0:
                        await resolve.rescore_open(session, d)
                    await stats.publish_counters(session, d.id)
                if ticks % 12 == 0:
                    stale = await resolve.requeue_stale(session)
                    if stale:
                        log.info("intake.requeued", count=len(stale))
                        await intake.enqueue(stale)
            if ticks % 17_280 == 1:  # about once a day
                await purge_expired()
        except Exception as e:  # noqa: BLE001
            log.exception("housekeeping.failed", error=str(e)[:300])
        await asyncio.sleep(5)


async def supervised(name: str, loop: Callable[[], Awaitable[None]]) -> None:
    """Restart a loop that dies (Redis restarted, groups lost, network blip) with backoff.
    Every loop re-creates its consumer group on entry, so a restart heals that too."""
    delay = 1.0
    while True:
        started = time.time()
        try:
            await loop()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("worker.crashed", worker=name, error=str(e)[:300])
        delay = 1.0 if time.time() - started > 60 else min(30.0, delay * 2)
        await asyncio.sleep(delay)


async def run_all() -> None:
    log.info("workers.start", consumer=CONSUMER)
    await asyncio.gather(
        supervised("intake", intake_consumer),
        supervised("dispatch", dispatch_consumer),
        supervised("replay", replay_runner),
        supervised("nowcast", nowcast_runner),
        supervised("housekeeping", housekeeping),
    )


def main() -> None:
    configure_logging()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_all())
