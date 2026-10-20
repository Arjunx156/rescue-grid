"""Close the loop: tell reporters what is happening, in their language, and buzz the field team.

WhatsApp goes out only when every Cloud API setting is present and the disaster
is live; replays never message anyone. Every attempt is logged in
outbound_messages, sent or not.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.crypto import lookup_hash
from app.core.logging import log
from app.core.redis import rate_limited
from app.core.settings import get_settings
from app.models import Case, Disaster, OutboundMessage, PushSubscription, SosMessage, Team

IST = timedelta(hours=5, minutes=30)

TEXT: dict[str, dict[str, str]] = {
    "ack": {
        "en": "Rescue Grid received your SOS. Tracking code {code}. Follow updates: {url}. Stay on the highest floor and keep your phone charged.",
        "ta": "Rescue Grid உங்கள் அவசர உதவி கோரிக்கையைப் பெற்றது. கண்காணிப்பு எண் {code}. நிலவரம் அறிய: {url}. உயரமான தளத்தில் இருங்கள், கைபேசியை சார்ஜ் செய்து வையுங்கள்.",
        "hi": "Rescue Grid को आपका SOS मिल गया है। ट्रैकिंग कोड {code}। अपडेट के लिए: {url}। सबसे ऊँची मंज़िल पर रहें और फ़ोन चार्ज रखें।",
        "ml": "Rescue Grid നിങ്ങളുടെ SOS സ്വീകരിച്ചു. ട്രാക്കിംഗ് കോഡ് {code}. വിവരങ്ങൾക്ക്: {url}. ഏറ്റവും ഉയർന്ന നിലയിൽ തുടരുക, ഫോൺ ചാർജ് ചെയ്തു വയ്ക്കുക.",
        "te": "Rescue Grid మీ SOS అందుకుంది. ట్రాకింగ్ కోడ్ {code}. అప్‌డేట్‌ల కోసం: {url}. ఎత్తైన అంతస్తులో ఉండండి, ఫోన్ ఛార్జ్ చేసి ఉంచండి.",
    },
    "ask_pin": {
        "en": "Please share your live location pin so the team can find you faster.",
        "ta": "மீட்புக் குழு உங்களை விரைவாகக் கண்டுபிடிக்க, உங்கள் நேரடி இருப்பிடத்தை (location pin) பகிரவும்.",
        "hi": "कृपया अपनी लाइव लोकेशन पिन भेजें ताकि टीम आपको जल्दी ढूंढ सके।",
        "ml": "ടീമിന് നിങ്ങളെ വേഗം കണ്ടെത്താൻ നിങ്ങളുടെ ലൈവ് ലൊക്കേഷൻ പങ്കിടുക.",
        "te": "బృందం మిమ్మల్ని త్వరగా కనుగొనడానికి మీ లైవ్ లొకేషన్ పిన్ పంపండి.",
    },
    "assigned": {
        "en": "Team {team} is on the way for request {code}. Expected around {eta}. Keep your phone on.",
        "ta": "உங்கள் கோரிக்கை {code}க்கு {team} குழு புறப்பட்டுள்ளது. சுமார் {eta}க்கு வந்தடையும். கைபேசியை இயக்கத்தில் வைத்திருங்கள்.",
        "hi": "आपके अनुरोध {code} के लिए टीम {team} रवाना हो गई है। लगभग {eta} तक पहुँचेगी। फ़ोन चालू रखें।",
        "ml": "നിങ്ങളുടെ അഭ്യർത്ഥന {code}-ന് {team} ടീം പുറപ്പെട്ടു. ഏകദേശം {eta}-ന് എത്തും. ഫോൺ ഓണാക്കി വയ്ക്കുക.",
        "te": "మీ అభ్యర్థన {code} కోసం {team} బృందం బయలుదేరింది. సుమారు {eta}కి చేరుకుంటారు. ఫోన్ ఆన్‌లో ఉంచండి.",
    },
    "rescued": {
        "en": "Rescued at {time} by team {team}. Thank you for reporting. Stay safe.",
        "ta": "{time} மணிக்கு {team} குழு மீட்டது. தகவல் தந்ததற்கு நன்றி. பாதுகாப்பாக இருங்கள்.",
        "hi": "{time} पर टीम {team} ने बचा लिया। सूचना देने के लिए धन्यवाद। सुरक्षित रहें।",
        "ml": "{time}-ന് {team} ടീം രക്ഷപ്പെടുത്തി. അറിയിച്ചതിന് നന്ദി. സുരക്ഷിതരായിരിക്കുക.",
        "te": "{time}కి {team} బృందం రక్షించింది. తెలియజేసినందుకు ధన్యవాదాలు. సురక్షితంగా ఉండండి.",
    },
}


def render(template: str, language: str | None, **kw: Any) -> str:
    table = TEXT[template]
    return table.get(language or "en", table["en"]).format(**kw)


def ist_clock(at: datetime) -> str:
    return (at.astimezone(UTC) + IST).strftime("%H:%M")


def tracking_url(code: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/sos/{code}"


async def send_whatsapp(to_e164: str, payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """(status, provider id, error) for one Cloud API message."""
    s = get_settings()
    if not s.whatsapp_enabled or not s.whatsapp_access_token:
        return "skipped", None, "WhatsApp Cloud API not configured"
    url = f"https://graph.facebook.com/{s.whatsapp_api_version}/{s.whatsapp_phone_number_id}/messages"
    body = {"messaging_product": "whatsapp", "to": to_e164.lstrip("+"), **payload}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url, json=body, headers={"Authorization": f"Bearer {s.whatsapp_access_token.get_secret_value()}"}
            )
        if r.status_code >= 300:
            return "failed", None, f"{r.status_code}: {r.text[:300]}"
        return "sent", r.json().get("messages", [{}])[0].get("id"), None
    except httpx.HTTPError as e:
        return "failed", None, str(e)


async def _deliver(
    session: AsyncSession,
    case: Case,
    to_phone: str,
    template: str,
    language: str,
    body: str,
    payload: dict[str, Any] | None = None,
) -> None:
    to_hash = lookup_hash(to_phone)
    already = await session.scalar(
        select(OutboundMessage.id).where(
            OutboundMessage.case_id == case.id,
            OutboundMessage.template == template,
            OutboundMessage.to_phone_hash == to_hash,
        )
    )
    if already:
        return
    status, provider_id, error = await send_whatsapp(to_phone, payload or {"type": "text", "text": {"body": body}})
    session.add(
        OutboundMessage(
            case_id=case.id,
            channel="whatsapp",
            to_phone=to_phone,
            to_phone_hash=to_hash,
            template=template,
            language=language,
            body=body,
            status=status,
            provider_message_id=provider_id,
            error=error,
            sent_at=utcnow() if status == "sent" else None,
        )
    )
    if status == "failed":
        log.warning("notify.failed", template=template, error=error)


async def acknowledge(session: AsyncSession, msg: SosMessage, case: Case, language: str, ask_for_pin: bool) -> None:
    if not msg.sender_phone:
        return
    lang = language if language in TEXT["ack"] else "en"
    body = render("ack", lang, code=msg.tracking_code, url=tracking_url(msg.tracking_code))
    await _deliver(session, case, msg.sender_phone, f"ack:{msg.id}", lang, body)
    if ask_for_pin and not await rate_limited(f"rl:pin:{msg.sender_phone_hash}", 1, 3600):
        text = render("ask_pin", lang)
        interactive = {
            "type": "interactive",
            "interactive": {
                "type": "location_request_message",
                "body": {"text": text},
                "action": {"name": "send_location"},
            },
        }
        await _deliver(session, case, msg.sender_phone, f"ask_pin:{msg.id}", lang, text, interactive)
    await session.commit()


async def _reporters(session: AsyncSession, case: Case) -> list[tuple[str, str]]:
    rows = await session.execute(
        select(SosMessage.sender_phone, SosMessage.channel).where(SosMessage.case_id == case.id)
    )
    seen, out = set(), []
    for phone, channel in rows:
        if phone and channel == "whatsapp" and phone not in seen:
            seen.add(phone)
            out.append((phone, case.language if case.language in TEXT["ack"] else "en"))
    return out


async def case_assigned(session: AsyncSession, case: Case, team: Team, eta: datetime | None) -> None:
    disaster = await session.get(Disaster, case.disaster_id)
    if disaster is None or disaster.status == "replay":
        return
    for phone, lang in await _reporters(session, case):
        body = render(
            "assigned", lang, team=team.call_sign, code=case.tracking_code, eta=ist_clock(eta) if eta else "soon"
        )
        await _deliver(session, case, phone, "assigned", lang, body)
    await session.commit()


async def case_rescued(session: AsyncSession, case: Case, team: Team, at: datetime) -> None:
    disaster = await session.get(Disaster, case.disaster_id)
    if disaster is None or disaster.status == "replay":
        return
    for phone, lang in await _reporters(session, case):
        body = render("rescued", lang, team=team.call_sign, time=ist_clock(at))
        await _deliver(session, case, phone, "rescued", lang, body)
    await session.commit()


def _webpush_sync(sub: PushSubscription, data: dict[str, Any]) -> bool:
    from pywebpush import WebPushException, webpush

    s = get_settings()
    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps(data),
            vapid_private_key=s.vapid_private_key.get_secret_value() if s.vapid_private_key else None,
            vapid_claims={"sub": s.vapid_subject},
            timeout=10,
        )
        return True
    except WebPushException as e:
        gone = e.response is not None and e.response.status_code in (404, 410)
        log.info("push.failed", gone=gone, error=str(e)[:200])
        return not gone


async def push_team(session: AsyncSession, team: Team, title: str, body: str, url: str = "/field") -> None:
    s = get_settings()
    if not team.lead_user_id or not s.vapid_private_key or team.is_virtual:
        return
    subs = list(await session.scalars(select(PushSubscription).where(PushSubscription.user_id == team.lead_user_id)))
    for sub in subs:
        alive = await asyncio.to_thread(_webpush_sync, sub, {"title": title, "body": body, "url": url})
        if not alive:
            await session.delete(sub)
    await session.commit()
