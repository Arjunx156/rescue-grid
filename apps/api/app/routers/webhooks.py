"""Meta WhatsApp Cloud API webhook: inbound SOS messages and location pins."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from app.actions import events, geo, intake
from app.actions.events import Actor
from app.actions.resolve import flood_depth, rescore, settle_status
from app.actions.serialize import case_out
from app.core.clock import disaster_now
from app.core.crypto import normalize_phone, phone_hash
from app.core.deps import Session
from app.core.logging import log
from app.core.settings import get_settings
from app.models import Case, Disaster, SosMessage

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
REPORTER = Actor("system", None, "Reporter (WhatsApp pin)")


@router.get("/whatsapp")
async def verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
) -> Response:
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected.get_secret_value()):
        return Response(challenge, media_type="text/plain")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")


def signature_ok(raw: bytes, header: str | None) -> bool:
    secret = get_settings().whatsapp_app_secret
    if not secret or not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(secret.get_secret_value().encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header.removeprefix("sha256="))


def _text_of(m: dict[str, Any]) -> str | None:
    kind = m.get("type")
    if kind == "text":
        return m.get("text", {}).get("body")
    if kind == "interactive":
        i = m.get("interactive", {})
        return (i.get("button_reply") or i.get("list_reply") or {}).get("title")
    if kind == "button":
        return m.get("button", {}).get("text")
    if kind == "location":
        loc = m["location"]
        return " ".join(x for x in ("Location shared", loc.get("name"), loc.get("address")) if x)
    return None


async def _apply_pin(session: Session, sender: str, lat: float, lng: float) -> Case | None:
    """A pin sent after an SOS (often because we asked) fixes that family's location."""
    msg = await session.scalar(
        select(SosMessage)
        .where(SosMessage.sender_phone_hash == phone_hash(sender), SosMessage.case_id.is_not(None))
        .order_by(SosMessage.received_at.desc())
        .limit(1)
    )
    if msg is None:
        return None
    case = await session.get(Case, msg.case_id)
    if case is None or case.status in ("rescued", "closed", "duplicate", "false_alarm"):
        return None
    d = await session.get(Disaster, case.disaster_id)
    assert d is not None
    now = await disaster_now(d.id, d.status)
    case.location = geo.point(lat, lng)
    case.location_confidence, case.location_source = 0.95, "pin"
    case.in_flood_zone, case.flood_depth_m = await flood_depth(session, case.disaster_id, lat, lng)
    case.review_reasons = sorted(set(case.review_reasons or []) - {"location_unknown", "low_confidence_location"})
    rescore(case, now)
    settle_status(case)
    case.version += 1
    events.record(session, case, "pin_received", REPORTER, now, {"lat": lat, "lng": lng})
    await session.commit()
    await events.publish(
        case.disaster_id,
        "case.upsert",
        {
            "case": case_out(case, "coordinator").model_dump(mode="json"),
            "masked": case_out(case, "viewer").model_dump(mode="json"),
            "created": False,
        },
    )
    await events.trigger_dispatch(case.disaster_id, "pin_received")
    return case


@router.post("/whatsapp")
async def receive(request: Request, session: Session) -> dict[str, int]:
    raw = await request.body()
    if not signature_ok(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
    payload = await request.json()
    ids, pins = [], 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                sender = normalize_phone(m.get("from"))
                text = _text_of(m)
                if not sender or not text:
                    continue
                pin = None
                if m.get("type") == "location":
                    pin = (float(m["location"]["latitude"]), float(m["location"]["longitude"]))
                    if await _apply_pin(session, sender, *pin):
                        pins += 1
                        continue
                d = None
                if pin:
                    d = await session.scalar(
                        select(Disaster)
                        .where(Disaster.status == "active", func.ST_Contains(Disaster.area, geo.point(*pin)))
                        .limit(1)
                    )
                d = d or await session.scalar(
                    select(Disaster).where(Disaster.status == "active").order_by(Disaster.started_at.desc()).limit(1)
                )
                if d is None:
                    log.warning("whatsapp.no_active_disaster")
                    continue
                received = datetime.fromtimestamp(int(m.get("timestamp", 0)) or datetime.now(UTC).timestamp(), UTC)
                msg, created = await intake.ingest(
                    session,
                    intake.Incoming(
                        disaster_id=d.id,
                        channel="whatsapp",
                        text=text,
                        received_at=received,
                        external_id=m.get("id"),
                        sender_phone=sender,
                        sender_name=names.get(m.get("from")),
                        pin=pin,
                        meta={"wa_type": m.get("type")},
                    ),
                )
                if created:
                    ids.append(msg.id)
    await intake.enqueue(ids)
    return {"queued": len(ids), "pins": pins}
