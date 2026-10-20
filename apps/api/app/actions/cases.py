"""Coordinator edits: fix a pin, merge or split duplicates, close or reopen a case."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import events, geo, planning
from app.actions.events import Actor
from app.actions.resolve import flood_depth, rescore, settle_status
from app.actions.serialize import case_out
from app.core.clock import disaster_now
from app.models import Assignment, Case, CaseEvent, Disaster, Extraction, ReviewPair, SosMessage
from app.models.tables import ASSIGNMENT_ACTIVE
from app.schemas.api import CasePatch
from app.services import merge

LOCATION_REASONS = {"location_unknown", "low_confidence_location"}


class ConflictError(Exception):
    """The case changed since the client loaded it."""


async def _publish(c: Case) -> None:
    await events.publish(
        c.disaster_id,
        "case.upsert",
        {
            "case": case_out(c, "coordinator").model_dump(mode="json"),
            "masked": case_out(c, "viewer").model_dump(mode="json"),
            "created": False,
        },
    )


async def _now(session: AsyncSession, c: Case) -> datetime:
    d = await session.get(Disaster, c.disaster_id)
    assert d is not None
    return await disaster_now(d.id, d.status)


async def _cancel_active(session: AsyncSession, c: Case, actor: Actor, reason: str) -> None:
    for a in await session.scalars(
        select(Assignment).where(Assignment.case_id == c.id, Assignment.status.in_(("proposed", *ASSIGNMENT_ACTIVE)))
    ):
        await planning.cancel(session, a, actor, reason)


async def patch(session: AsyncSession, c: Case, body: CasePatch, actor: Actor) -> Case:
    if body.version is not None and body.version != c.version:
        raise ConflictError(f"case is at version {c.version}")
    now = await _now(session, c)
    changes: dict[str, object] = {}
    if body.lat is not None and body.lng is not None:
        old = geo.latlng(c.location)
        c.location = geo.point(body.lat, body.lng)
        c.location_confidence, c.location_source = 1.0, "manual"
        c.location_candidates = []
        c.in_flood_zone, c.flood_depth_m = await flood_depth(session, c.disaster_id, body.lat, body.lng)
        c.review_reasons = sorted(set(c.review_reasons or []) - LOCATION_REASONS)
        changes["location"] = {"from": list(old) if old else None, "to": [body.lat, body.lng]}
    if body.people_count is not None and body.people_count != c.people_count:
        changes["people_count"] = {"from": c.people_count, "to": body.people_count}
        c.people_count = body.people_count
    if body.clear_reasons:
        c.review_reasons = sorted(set(c.review_reasons or []) - set(body.clear_reasons))
        changes["cleared"] = body.clear_reasons
    if body.status and body.status != c.status:
        changes["status"] = {"from": c.status, "to": body.status}
        if body.status in ("false_alarm", "closed", "rescued"):
            await _cancel_active(session, c, actor, f"Case marked {body.status.replace('_', ' ')}")
            c = await session.get(Case, c.id) or c
            c.status = body.status
            c.closed_at = now
            if body.status == "rescued":
                c.rescued_at = c.rescued_at or now
            c.review_reasons = []
        elif body.status == "queued":
            c.status = "queued"
            c.closed_at = None
    if body.note:
        changes["note"] = body.note
    rescore(c, now)
    settle_status(c)
    c.version += 1
    events.record(session, c, "case_edited", actor, now, changes)
    await session.commit()
    await _publish(c)
    if c.status in ("queued", "unreachable"):
        await events.trigger_dispatch(c.disaster_id, "case_edited")
    return c


async def recompute(session: AsyncSession, c: Case) -> None:
    """Rebuild merged fields from the case's own reports (after an unmerge)."""
    rows = list(
        await session.execute(
            select(SosMessage, Extraction)
            .join(Extraction, Extraction.sos_message_id == SosMessage.id)
            .where(SosMessage.case_id == c.id)
        )
    )
    if not rows:
        return
    people, vul, water, needs, phones, senders = None, {}, None, [], set(), set()
    first, last = rows[0][0].received_at, rows[0][0].received_at
    for msg, ex in rows:
        people = merge.merge_people(people, ex.people_count)
        vul = merge.merge_vulnerability(vul, ex.vulnerable)
        water = merge.worse_water(water, ex.water_level)
        needs = merge.merge_needs(needs, ex.needs)
        phones |= set(ex.contact_phone_hashes or [])
        if msg.sender_phone_hash:
            senders.add(msg.sender_phone_hash)
        first, last = min(first, msg.received_at), max(last, msg.received_at)
    c.people_count, c.vulnerability, c.water_level, c.needs = people, vul, water, needs
    c.contact_phone_hashes, c.sender_phone_hashes = sorted(phones), sorted(senders)
    c.first_reported_at, c.last_reported_at, c.source_count = first, last, len(rows)


async def merge_cases(session: AsyncSession, keep: Case, drop: Case, actor: Actor) -> Case:
    if keep.id == drop.id or keep.disaster_id != drop.disaster_id:
        raise ValueError("can only merge two different cases of one disaster")
    now = await _now(session, keep)
    moved = [m for m in await session.scalars(select(SosMessage.id).where(SosMessage.case_id == drop.id))]
    await _cancel_active(session, drop, actor, f"Merged into {keep.tracking_code}")
    drop = await session.get(Case, drop.id) or drop
    await session.execute(update(SosMessage).where(SosMessage.case_id == drop.id).values(case_id=keep.id))
    keep.people_count = merge.merge_people(keep.people_count, drop.people_count)
    keep.vulnerability = merge.merge_vulnerability(keep.vulnerability, drop.vulnerability)
    keep.water_level = merge.worse_water(keep.water_level, drop.water_level)
    keep.water_rising = bool(keep.water_rising or drop.water_rising)
    keep.needs = merge.merge_needs(keep.needs, drop.needs)
    keep.contact_phone_hashes = sorted(set(keep.contact_phone_hashes or []) | set(drop.contact_phone_hashes or []))
    keep.sender_phone_hashes = sorted(set(keep.sender_phone_hashes or []) | set(drop.sender_phone_hashes or []))
    keep.contact_phone = keep.contact_phone or drop.contact_phone
    keep.contact_name = keep.contact_name or drop.contact_name
    keep.first_reported_at = min(keep.first_reported_at, drop.first_reported_at)
    keep.last_reported_at = max(keep.last_reported_at, drop.last_reported_at)
    keep.source_count += drop.source_count
    if drop.location_confidence > keep.location_confidence and drop.location is not None:
        keep.location, keep.location_confidence = drop.location, drop.location_confidence
        keep.location_source, keep.address_text = drop.location_source, drop.address_text
    keep.review_reasons = sorted(set(keep.review_reasons or []) - {"possible_duplicate"})
    drop.status, drop.merged_into_id, drop.review_reasons = "duplicate", keep.id, []
    for p in await session.scalars(
        select(ReviewPair).where(
            ReviewPair.status == "open",
            ((ReviewPair.case_a_id == drop.id) | (ReviewPair.case_b_id == drop.id)),
        )
    ):
        p.status, p.resolved_by, p.resolved_at = "merged", actor.id, now
    rescore(keep, now)
    settle_status(keep)
    keep.version += 1
    drop.version += 1
    events.record(
        session,
        keep,
        "merged",
        actor,
        now,
        {
            "absorbed": str(drop.id),
            "absorbed_code": drop.tracking_code,
            "messages": [str(m) for m in moved],
        },
    )
    events.record(session, drop, "merged_into", actor, now, {"into": str(keep.id), "into_code": keep.tracking_code})
    await session.commit()
    await _publish(keep)
    await _publish(drop)
    await events.trigger_dispatch(keep.disaster_id, "merged")
    return keep


async def unmerge(session: AsyncSession, drop: Case, actor: Actor) -> Case:
    """Undo a merge: give the absorbed case back its own reports."""
    if drop.status != "duplicate" or drop.merged_into_id is None:
        raise ValueError("case is not merged")
    keep = await session.get(Case, drop.merged_into_id)
    assert keep is not None
    now = await _now(session, keep)
    event = await session.scalar(
        select(CaseEvent)
        .where(
            CaseEvent.case_id == keep.id,
            CaseEvent.event_type == "merged",
            CaseEvent.payload["absorbed"].astext == str(drop.id),
        )
        .order_by(CaseEvent.created_at.desc())
        .limit(1)
    )
    moved = [uuid.UUID(m) for m in (event.payload.get("messages", []) if event else [])]
    if moved:
        await session.execute(update(SosMessage).where(SosMessage.id.in_(moved)).values(case_id=drop.id))
    drop.status, drop.merged_into_id = "queued", None
    await session.flush()
    await recompute(session, keep)
    await recompute(session, drop)
    for c in (keep, drop):
        rescore(c, now)
        settle_status(c)
        c.version += 1
    events.record(session, keep, "unmerged", actor, now, {"released": str(drop.id)})
    events.record(session, drop, "unmerged", actor, now, {"from": str(keep.id)})
    await session.commit()
    await _publish(keep)
    await _publish(drop)
    await events.trigger_dispatch(keep.disaster_id, "unmerged")
    return drop


async def dismiss_pair(session: AsyncSession, pair: ReviewPair, actor: Actor) -> None:
    now = await _now(session, await session.get(Case, pair.case_a_id))  # type: ignore[arg-type]
    pair.status, pair.resolved_by, pair.resolved_at = "dismissed", actor.id, now
    for cid in (pair.case_a_id, pair.case_b_id):
        c = await session.get(Case, cid)
        if c is None:
            continue
        others = await session.scalar(
            select(ReviewPair.id)
            .where(
                ReviewPair.status == "open",
                ReviewPair.id != pair.id,
                (ReviewPair.case_a_id == cid) | (ReviewPair.case_b_id == cid),
            )
            .limit(1)
        )
        if not others:
            c.review_reasons = sorted(set(c.review_reasons or []) - {"possible_duplicate"})
            settle_status(c)
            c.version += 1
        events.record(session, c, "duplicate_dismissed", actor, now, {"pair": str(pair.id)})
    await session.commit()
    for cid in (pair.case_a_id, pair.case_b_id):
        if c := await session.get(Case, cid):
            await _publish(c)
