"""ORM rows -> API shapes, with role-based masking of personal data in one place."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.actions import geo
from app.core.crypto import mask_phone
from app.models import Assignment, Case, CaseEvent, Disaster, FloodZone, ReviewPair, SosMessage, Team, User
from app.schemas.api import (
    AssignmentOut,
    CaseOut,
    DisasterOut,
    EventOut,
    FloodZoneOut,
    ReviewPairOut,
    SourceOut,
    TeamOut,
    UserOut,
    WaterClockOut,
)

# viewers (press, partner agencies) see the operational picture, never phones or diagnoses
SEES_PERSONAL = {"admin", "coordinator", "field_lead"}


def _mask_breakdown(breakdown: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**f, "detail": "Restricted"} if f.get("key") == "medical" else f for f in breakdown]


def plain_summary(c: Case) -> str:
    """Summary without medical detail, built from fields rather than free text."""
    v = c.vulnerability or {}
    who = f"{c.people_count} people" if c.people_count else "Headcount unknown"
    tags = [f"{v[k]} {k}" for k in ("elderly", "child", "infant", "pregnant", "disabled") if v.get(k)]
    if v.get("medical"):
        tags.append("medical need")
    parts = [who + (f" incl. {', '.join(tags)}" if tags else "")]
    if c.water_level and c.water_level != "unknown":
        parts.append(f"water {c.water_level.replace('_', ' ')}" + (", rising" if c.water_rising else ""))
    return " · ".join(parts)


def case_out(c: Case, role: str) -> CaseOut:
    personal = role in SEES_PERSONAL
    ll = geo.latlng(c.location)
    vulnerability = dict(c.vulnerability or {})
    if not personal and vulnerability.get("medical"):
        vulnerability["medical"] = ["restricted"]
    return CaseOut(
        id=c.id,
        disaster_id=c.disaster_id,
        tracking_code=c.tracking_code,
        status=c.status,
        urgency_score=c.urgency_score,
        urgency_level=c.urgency_level,
        score_breakdown=c.score_breakdown if personal else _mask_breakdown(c.score_breakdown),  # type: ignore[arg-type]
        lat=ll[0] if ll else None,
        lng=ll[1] if ll else None,
        location_confidence=round(c.location_confidence or 0, 2),
        location_source=c.location_source,
        address_text=c.address_text,
        locality=c.locality,
        location_candidates=c.location_candidates or [],  # type: ignore[arg-type]
        people_count=c.people_count,
        vulnerability=vulnerability,
        needs=list(c.needs or []),
        water_level=c.water_level,
        water_rising=c.water_rising,
        in_flood_zone=c.in_flood_zone,
        flood_depth_m=c.flood_depth_m,
        summary=c.summary if personal else plain_summary(c),
        language=c.language,
        source_count=c.source_count,
        review_reasons=list(c.review_reasons or []),
        contact_name=c.contact_name if personal else None,
        contact_phone=c.contact_phone if personal else mask_phone(c.contact_phone),
        first_reported_at=c.first_reported_at,
        last_reported_at=c.last_reported_at,
        assigned_at=c.assigned_at,
        rescued_at=c.rescued_at,
        people_rescued=c.people_rescued,
        current_team_id=c.current_team_id,
        merged_into_id=c.merged_into_id,
        updated_at=c.updated_at,
        version=c.version,
        water_clock=WaterClockOut.model_validate(c.water_clock) if c.water_clock else None,
    )


def source_out(m: SosMessage, extraction: Any, role: str) -> SourceOut:
    personal = role in SEES_PERSONAL
    pin = geo.latlng(m.raw_location)
    return SourceOut(
        id=m.id,
        channel=m.channel,
        tracking_code=m.tracking_code,
        received_at=m.received_at,
        text=m.raw_text if personal else None,
        sender=m.sender_phone if personal else mask_phone(m.sender_phone),
        pin=list(pin) if pin else None,
        language=extraction.language if extraction else None,
        summary=extraction.summary if extraction and personal else None,
        provider=extraction.provider if extraction else None,
        model=extraction.model if extraction else None,
        confidence=extraction.confidence if extraction else None,
    )


def event_out(e: CaseEvent) -> EventOut:
    return EventOut(
        id=e.id,
        event_type=e.event_type,
        actor_type=e.actor_type,
        actor_label=e.actor_label,
        payload=e.payload,
        created_at=e.created_at,
    )


def assignment_out(a: Assignment, call_sign: str | None = None) -> AssignmentOut:
    return AssignmentOut(
        id=a.id,
        case_id=a.case_id,
        team_id=a.team_id,
        team_call_sign=call_sign,
        plan_id=a.plan_id,
        sequence=a.sequence,
        status=a.status,
        eta=a.eta,
        distance_m=a.distance_m,
        travel_s=a.travel_s,
        reasons=a.reasons or [],
        route=geo.line_coords(a.route),
        route_source=a.route_source,
        approved_at=a.approved_at,
        started_at=a.started_at,
        reached_at=a.reached_at,
        completed_at=a.completed_at,
        outcome_people_rescued=a.outcome_people_rescued,
        outcome_note=a.outcome_note,
    )


def review_pair_out(p: ReviewPair) -> ReviewPairOut:
    return ReviewPairOut(
        id=p.id,
        case_a_id=p.case_a_id,
        case_b_id=p.case_b_id,
        score=p.score,
        reasons=p.reasons,
        status=p.status,
        created_at=p.created_at,
    )


def team_out(
    t: Team,
    *,
    organization: str | None = None,
    lead: User | None = None,
    active: Assignment | None = None,
    queued: int = 0,
    role: str = "coordinator",
) -> TeamOut:
    ll = geo.latlng(t.current_location)
    base = geo.latlng(t.base_location)
    return TeamOut(
        id=t.id,
        disaster_id=t.disaster_id,
        call_sign=t.call_sign,
        asset_type=t.asset_type,
        capacity=t.capacity,
        status=t.status,
        lat=ll[0] if ll else None,
        lng=ll[1] if ll else None,
        heading=t.heading,
        location_updated_at=t.location_updated_at,
        base_name=t.base_name,
        base_lat=base[0] if base else None,
        base_lng=base[1] if base else None,
        organization=organization,
        lead_name=lead.name if lead else None,
        lead_phone=(lead.phone if role in SEES_PERSONAL else mask_phone(lead.phone)) if lead else None,
        is_virtual=t.is_virtual,
        active_assignment_id=active.id if active else None,
        active_case_id=active.case_id if active else None,
        queued=queued,
    )


def disaster_out(d: Disaster, now: datetime) -> DisasterOut:
    c = geo.center(d.area)
    return DisasterOut(
        id=d.id,
        name=d.name,
        status=d.status,
        description=d.description,
        started_at=d.started_at,
        ended_at=d.ended_at,
        center=[c[0], c[1]] if c else None,
        bbox=geo.bbox(d.area),
        area=geo.geojson(d.area),
        settings=d.settings or {},
        replay_dataset_id=d.replay_dataset_id,
        now=now,
    )


def flood_zone_out(z: FloodZone) -> FloodZoneOut:
    return FloodZoneOut(
        id=z.id,
        name=z.name,
        depth_estimate_m=float(z.depth_estimate_m) if z.depth_estimate_m is not None else None,
        source=z.source,
        geometry=geo.geojson(z.geom) or {},
    )


def user_out(u: User, organization: str | None = None, team_id: Any = None) -> UserOut:
    return UserOut(
        id=u.id,
        name=u.name,
        email=u.email,
        phone=u.phone,
        role=u.role,
        organization_id=u.organization_id,
        organization=organization,
        preferred_language=u.preferred_language,
        is_active=u.is_active,
        team_id=team_id,
        last_login_at=u.last_login_at,
    )
