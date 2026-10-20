"""One raw message -> one located, de-duplicated, scored case. The heart of the pipeline.

understand -> locate -> flood depth -> find candidates in PostGIS -> merge or create
-> score -> publish -> maybe re-plan -> maybe ask the reporter for a pin.

Runs under a per-disaster advisory lock so two reports of one family arriving in
the same second cannot both become new cases.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import events, geo, notify
from app.actions.events import SYSTEM
from app.actions.serialize import case_out
from app.agents import rules
from app.agents.understand import understand
from app.core.clock import disaster_now
from app.core.crypto import normalize_phone, phone_hash
from app.core.logging import log
from app.core.settings import get_settings
from app.llm import embed
from app.models import Case, Disaster, Extraction, FloodZone, ReviewPair, SosMessage
from app.models.tables import TERMINAL_CASE_STATUSES
from app.schemas.extraction import SosExtraction, Understanding
from app.services import dedup, merge, triage
from app.services.geocode import gazetteer
from app.services.merge import LocationFix
from app.services.resolver import locate, review_reasons

# reasons that keep a case out of dispatch until a coordinator looks
BLOCKING = {"location_unknown", "low_confidence_location", "reported_rescued", "reported_false", "possibly_rescued"}
DISPATCHABLE = ("queued", "unreachable")
ACTIVE_FIELD = ("assigned", "en_route", "on_scene")
CANDIDATE_DEG = 0.012  # ~1.3 km box for the index; exact distance is checked in dedup


async def flood_depth(
    session: AsyncSession, disaster_id: uuid.UUID, lat: float, lng: float
) -> tuple[bool, float | None]:
    row = (
        await session.execute(
            select(func.count(), func.max(FloodZone.depth_estimate_m)).where(
                FloodZone.disaster_id == disaster_id, func.ST_Intersects(FloodZone.geom, geo.point(lat, lng))
            )
        )
    ).one()
    count, deepest = row[0], row[1]
    return bool(count), float(deepest) if deepest is not None else None


def case_signals(c: Case) -> dedup.Signals:
    ll = geo.latlng(c.location)
    return dedup.Signals(
        lat=ll[0] if ll else None,
        lng=ll[1] if ll else None,
        location_confidence=c.location_confidence or 0.0,
        phone_hashes=set(c.contact_phone_hashes or []),
        sender_hashes=set(c.sender_phone_hashes or []),
        reported_at=c.first_reported_at,
        last_reported_at=c.last_reported_at,
        contact_name=c.contact_name,
        address=c.address_text,
        people_count=c.people_count,
        vulnerability=c.vulnerability,
        location_text=None,
        embedding=list(c.embedding) if c.embedding is not None else None,
        anchors=set(c.location_anchors or []),
        locality=c.locality,
        water_level=c.water_level,
    )


async def candidates(session: AsyncSession, disaster_id: uuid.UUID, sig: dedup.Signals, at: datetime) -> list[Case]:
    phones = list(sig.phone_hashes | sig.sender_hashes)
    near = []
    if sig.lat is not None and sig.lng is not None:
        near.append(func.ST_DWithin(Case.location, geo.point(sig.lat, sig.lng), CANDIDATE_DEG))
    if phones:
        near += [Case.contact_phone_hashes.overlap(phones), Case.sender_phone_hashes.overlap(phones)]
    if not near:
        return []
    rows = await session.scalars(
        select(Case)
        .where(
            Case.disaster_id == disaster_id,
            Case.status != "duplicate",
            Case.merged_into_id.is_(None),
            Case.last_reported_at >= at - dedup.PHONE_WINDOW,
            or_(*near),
        )
        .limit(60)
    )
    return list(rows)


def clock_minutes(c: Case, now: datetime) -> float | None:
    """Minutes left on the case's water clock at `now`, counted down from when it was issued."""
    clock = c.water_clock or {}
    if clock.get("minutes") is None:
        return None
    elapsed = (now - datetime.fromisoformat(clock["issued_at"])).total_seconds() / 60
    return max(0.0, float(clock["minutes"]) - elapsed)


def rescore(c: Case, now: datetime) -> triage.TriageResult:
    r = triage.score(
        triage.TriageInput(
            people_count=c.people_count,
            vulnerability=c.vulnerability,
            water_level=c.water_level,
            water_rising=c.water_rising,
            needs=list(c.needs or []),
            first_reported_at=c.first_reported_at,
            source_count=c.source_count,
            flood_depth_m=c.flood_depth_m,
            in_flood_zone=c.in_flood_zone,
            minutes_to_danger=clock_minutes(c, now),
            danger_label=(c.water_clock or {}).get("danger_label"),
        ),
        now,
    )
    c.urgency_score, c.urgency_level, c.score_breakdown = r.score, r.level, r.breakdown_dicts()
    return r


def settle_status(c: Case) -> None:
    """Open cases sit in review while something blocks dispatch, otherwise in the queue."""
    if c.status in ACTIVE_FIELD or c.status in TERMINAL_CASE_STATUSES:
        return
    if set(c.review_reasons or []) & BLOCKING:
        c.status = "needs_review"
    elif c.status in ("new", "needs_review"):
        c.status = "queued"


def apply_location(c: Case, loc: LocationFix | None) -> None:
    current = None
    if c.location is not None:
        ll = geo.latlng(c.location)
        if ll:
            current = LocationFix(ll[0], ll[1], c.location_confidence, c.location_source)
    best = merge.better_location(current, loc)
    if best is None or best is current:
        return
    c.location = geo.point(best.lat, best.lng)
    c.location_confidence = best.confidence
    c.location_source = best.source
    c.location_candidates = best.candidates
    c.address_text = best.label or c.address_text
    c.locality = best.locality or c.locality
    c.location_anchors = sorted(set(c.location_anchors or []) | set(best.anchors))


async def _understand_cached(session: AsyncSession, msg: SosMessage) -> Understanding:
    """A replay sends the same text again and again; never pay a model twice for it."""
    settings = get_settings()
    text = msg.raw_text or ""
    if settings.llm_provider != "local" and msg.text_hash:
        cached = await session.scalar(
            select(Extraction)
            .join(SosMessage, Extraction.sos_message_id == SosMessage.id)
            .where(SosMessage.text_hash == msg.text_hash, Extraction.model == settings.llm_model)
            .limit(1)
        )
        if cached:
            e = SosExtraction.model_validate({**cached.raw_json, "contact_name": cached.contact_name})
            return Understanding(extraction=e, phones=rules.phones(text), provider=cached.provider, model=cached.model)
    return await understand(text)


async def process(session: AsyncSession, message_id: uuid.UUID) -> Case | None:
    msg = await session.get(SosMessage, message_id, with_for_update=True)
    if msg is None or msg.processing_status == "processed":
        return None
    disaster = await session.get(Disaster, msg.disaster_id)
    if disaster is None:
        return None
    msg.attempts += 1
    text_in = msg.raw_text or ""
    u = await _understand_cached(session, msg)
    e = u.extraction
    vectors = await embed([rules.redact_phones(text_in)])
    extraction = await session.scalar(select(Extraction).where(Extraction.sos_message_id == msg.id))
    if extraction is None:
        extraction = Extraction(sos_message_id=msg.id)
        session.add(extraction)
    extraction.people_count = e.people_count
    extraction.vulnerable = e.vulnerable.model_dump()
    extraction.location_text, extraction.locality, extraction.landmarks = e.location_text, e.locality, e.landmarks
    extraction.address, extraction.water_level, extraction.water_rising = e.address, e.water_level, e.water_rising
    extraction.needs, extraction.language, extraction.status_update = list(e.needs), e.language, e.status_update
    extraction.contact_name = e.contact_name
    extraction.contact_phone_hashes = [h for h in (phone_hash(p) for p in u.phones) if h]
    extraction.summary, extraction.provider, extraction.model = e.summary, u.provider, u.model
    extraction.confidence, extraction.latency_ms = e.confidence, u.latency_ms
    extraction.raw_json = e.model_dump(exclude={"contact_name"})
    extraction.embedding = vectors[0] if vectors else None

    # serialize resolution per disaster: concurrent duplicates must see each other
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(disaster.id)))))
    now = await disaster_now(disaster.id, disaster.status)
    at = msg.received_at
    pin = geo.latlng(msg.raw_location)
    center = geo.center(disaster.area)
    loc = locate(gazetteer(str(get_settings().data_dir)), text_in, u, pin, center)
    in_zone, depth = (await flood_depth(session, disaster.id, loc.lat, loc.lng)) if loc else (False, None)
    text_phones = set(extraction.contact_phone_hashes)
    sender = {msg.sender_phone_hash} if msg.sender_phone_hash else set()
    sig = dedup.Signals(
        lat=loc.lat if loc else None,
        lng=loc.lng if loc else None,
        location_confidence=loc.confidence if loc else 0.0,
        phone_hashes=text_phones,
        sender_hashes=sender,
        reported_at=at,
        contact_name=e.contact_name,
        address=e.address,
        people_count=e.people_count,
        vulnerability=e.vulnerable.model_dump(),
        location_text=e.location_text,
        embedding=extraction.embedding,
        anchors=set(loc.anchors) if loc else set(),
        locality=loc.locality if loc else None,
        water_level=e.water_level,
    )
    pool = await candidates(session, disaster.id, sig, at)
    match = dedup.best_match(sig, [(c, case_signals(c)) for c in pool])
    reasons = review_reasons(loc, u)
    contact = [p for p in (normalize_phone(x) for x in rules.phones(text_in)) if p]

    if match and match[1].decision == "merge":
        case, verdict = match
        was_level = case.urgency_level
        case.source_count += 1
        case.first_reported_at = min(case.first_reported_at, at)
        case.last_reported_at = max(case.last_reported_at, at)
        apply_location(case, loc)
        case.people_count = merge.merge_people(case.people_count, e.people_count)
        case.vulnerability = merge.merge_vulnerability(case.vulnerability, e.vulnerable.model_dump())
        case.water_level = merge.worse_water(case.water_level, e.water_level)
        case.water_rising = bool(case.water_rising or e.water_rising)
        case.needs = merge.merge_needs(case.needs, e.needs)
        case.contact_phone_hashes = sorted(set(case.contact_phone_hashes or []) | text_phones)
        case.sender_phone_hashes = sorted(set(case.sender_phone_hashes or []) | sender)
        case.contact_phone = case.contact_phone or (contact[0] if contact else None)
        case.contact_name = case.contact_name or e.contact_name
        if in_zone and loc:
            case.in_flood_zone, case.flood_depth_m = in_zone, depth
        new_reasons = set(case.review_reasons or [])
        if case.location_confidence >= get_settings().location_review_threshold:
            new_reasons -= {"location_unknown", "low_confidence_location"}
        sticky = ("manual_reading", "instructions_in_message")
        new_reasons |= {r for r in reasons if r.startswith("reported") or r in sticky}
        if e.status_update == "none" and case.status in ("rescued", "closed"):
            new_reasons.add("reported_after_rescue")
        case.review_reasons = sorted(new_reasons)
        case.version += 1
        events.record(
            session,
            case,
            "report_merged",
            SYSTEM,
            now,
            {
                "message_id": str(msg.id),
                "channel": msg.channel,
                "score": verdict.score,
                "reasons": [r["detail"] for r in verdict.reasons if r["weight"] > 0],
            },
        )
        created = False
    else:
        was_level = None
        case = Case(
            id=uuid.uuid4(),
            disaster_id=disaster.id,
            tracking_code=msg.tracking_code,
            people_count=e.people_count,
            vulnerability=e.vulnerable.model_dump(),
            needs=list(e.needs),
            water_level=e.water_level,
            water_rising=e.water_rising,
            in_flood_zone=in_zone,
            flood_depth_m=depth,
            status="new",
            review_reasons=reasons,
            contact_phone=contact[0] if contact else None,
            contact_phone_hashes=sorted(text_phones),
            sender_phone_hashes=sorted(sender),
            contact_name=e.contact_name,
            summary=e.summary,
            language=e.language,
            first_reported_at=at,
            last_reported_at=at,
            source_count=1,
            embedding=extraction.embedding,
            location_confidence=0.0,
            location_source="unknown",
        )
        apply_location(case, loc)
        session.add(case)
        await session.flush()
        if match and match[1].decision == "review":
            case.review_reasons = sorted({*case.review_reasons, "possible_duplicate"})
            a, b = sorted([match[0].id, case.id], key=str)
            session.add(
                ReviewPair(
                    disaster_id=disaster.id, case_a_id=a, case_b_id=b, score=match[1].score, reasons=match[1].reasons
                )
            )
        events.record(
            session,
            case,
            "case_created",
            SYSTEM,
            now,
            {
                "message_id": str(msg.id),
                "channel": msg.channel,
                "extraction": {
                    "provider": u.provider,
                    "model": u.model,
                    "fallback": u.fallback_reason,
                    "dropped_claims": u.dropped_claims,
                    "instructions": u.flags,
                },
                "location": {"label": loc.label, "confidence": loc.confidence, "source": loc.source} if loc else None,
            },
        )
        created = True

    if not case.summary or (e.summary and case.source_count > 1 and len(e.summary) > len(case.summary)):
        case.summary = e.summary or case.summary
    rescore(case, now)
    settle_status(case)
    msg.case_id = case.id
    msg.processing_status = "processed"
    msg.error = None
    await session.commit()

    await events.publish(
        disaster.id,
        "case.upsert",
        {
            "case": case_out(case, "coordinator").model_dump(mode="json"),
            "masked": case_out(case, "viewer").model_dump(mode="json"),
            "created": created,
        },
    )
    if case.urgency_level == "critical" and was_level != "critical":
        await events.publish(
            disaster.id,
            "toast",
            {
                "kind": "critical",
                "case_id": str(case.id),
                "text": f"New critical case · {rules_summary(case)}",
            },
        )
    if case.status in DISPATCHABLE:
        await events.trigger_dispatch(disaster.id, "case_created" if created else "case_updated")
    if msg.channel == "whatsapp" and disaster.status != "replay":
        await notify.acknowledge(session, msg, case, e.language, ask_for_pin=not loc or loc.confidence < 0.6)
    log.info(
        "resolve.done",
        message=str(msg.id),
        case=str(case.id),
        created=created,
        score=case.urgency_score,
        status=case.status,
    )
    return case


def rules_summary(c: Case) -> str:
    where = c.locality or c.address_text or "location pending"
    return f"{c.summary or ''} · {where}".strip(" ·")


async def mark_failed(session: AsyncSession, message_id: uuid.UUID, error: str) -> None:
    await session.rollback()
    msg = await session.get(SosMessage, message_id)
    if msg is None:
        return
    msg.attempts += 1
    msg.error = error[:500]
    if msg.attempts >= 3:
        msg.processing_status = "failed"
    await session.commit()


async def requeue_stale(session: AsyncSession, older_than: timedelta = timedelta(minutes=2)) -> list[uuid.UUID]:
    """Pending rows that never made it through the stream (Redis down, worker crash)."""
    rows = await session.scalars(
        select(SosMessage.id)
        .where(
            SosMessage.processing_status == "pending",
            SosMessage.created_at < func.now() - text(f"interval '{int(older_than.total_seconds())} seconds'"),
            SosMessage.attempts < 3,
        )
        .limit(500)
    )
    return list(rows)


async def rescore_open(session: AsyncSession, disaster: Disaster) -> int:
    """Waiting time raises urgency; refresh scores so the queue reflects it."""
    now = await disaster_now(disaster.id, disaster.status)
    rows = list(
        await session.scalars(
            select(Case).where(
                Case.disaster_id == disaster.id, Case.status.in_(("queued", "needs_review", "unreachable"))
            )
        )
    )
    changed = []
    for c in rows:
        before = (c.urgency_score, c.urgency_level)
        rescore(c, now)
        if (c.urgency_score, c.urgency_level) != before:
            changed.append(c)
    await session.commit()
    if changed:
        await events.publish(
            disaster.id,
            "cases.upsert",
            {
                "cases": [case_out(c, "coordinator").model_dump(mode="json") for c in changed],
                "masked": [case_out(c, "viewer").model_dump(mode="json") for c in changed],
            },
        )
    return len(changed)
