"""Locate, de-duplicate and score reports in memory.

The database pipeline does the same steps against PostGIS; this version drives
the evaluation set and the replay benchmark, where thousands of messages must
be resolved in seconds without a database.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.crypto import normalize_phone
from app.schemas.extraction import Understanding
from app.services import dedup, merge, triage
from app.services.floods import FloodMap
from app.services.geocode import Gazetteer, haversine_m
from app.services.merge import LocationFix

REVIEW_THRESHOLD = 0.6


def locate(
    gaz: Gazetteer,
    text: str,
    u: Understanding,
    pin: tuple[float, float] | None,
    bias: tuple[float, float] | None,
) -> LocationFix | None:
    if pin:
        return LocationFix(pin[0], pin[1], 0.95, "pin", "Shared location pin")
    e = u.extraction
    hints = [h for h in (e.locality, *e.landmarks) if h]
    r = gaz.geocode(text, hints=hints, bias=bias)
    if r is None:
        return None
    return LocationFix(
        r.lat, r.lng, r.confidence, "geocoded", r.label, r.locality, [c.as_dict() for c in r.candidates], r.anchors
    )


def phone_keys(u: Understanding, sender_phone: str | None) -> tuple[set[str], set[str]]:
    """(phones written in the text, the sender's phone). Text phones identify the household;
    the sender may be a relative reporting several families, so it is weaker evidence."""
    in_text = {p for p in (normalize_phone(x) for x in u.phones) if p}
    sender = {p for p in [normalize_phone(sender_phone)] if p}
    return in_text, sender


def review_reasons(loc: LocationFix | None, u: Understanding) -> list[str]:
    reasons = []
    if loc is None:
        reasons.append("location_unknown")
    elif loc.confidence < REVIEW_THRESHOLD:
        reasons.append("low_confidence_location")
    if u.fallback_reason:
        reasons.append("manual_reading")
    if u.flags:
        reasons.append("instructions_in_message")  # read by a person; never blocks dispatch
    if u.extraction.status_update in ("rescued", "safe"):
        reasons.append("reported_rescued")
    elif u.extraction.status_update == "false_alarm":
        reasons.append("reported_false")
    return reasons


@dataclass
class SimCase:
    id: str
    first_reported_at: datetime
    last_reported_at: datetime
    location: LocationFix | None
    people: int | None
    vulnerability: dict[str, Any]
    water: str | None
    rising: bool | None
    needs: list[str]
    phones: set[str]
    senders: set[str]
    contact_name: str | None
    address: str | None
    location_text: str | None
    summary: str
    message_ids: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)
    in_flood_zone: bool = False
    flood_depth_m: float | None = None
    score: int = 0
    level: str = "low"
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    status: str = "open"  # open | rescued | closed | duplicate
    anchors: set[str] = field(default_factory=set)
    minutes_to_danger: float | None = None  # from the water clock, when one is running
    danger_label: str | None = None

    def signals(self) -> dedup.Signals:
        loc = self.location
        return dedup.Signals(
            lat=loc.lat if loc else None,
            lng=loc.lng if loc else None,
            location_confidence=loc.confidence if loc else 0.0,
            phone_hashes=self.phones,
            sender_hashes=self.senders,
            reported_at=self.first_reported_at,
            last_reported_at=self.last_reported_at,
            contact_name=self.contact_name,
            address=self.address,
            people_count=self.people,
            vulnerability=self.vulnerability,
            location_text=self.location_text,
            anchors=self.anchors,
            locality=loc.locality if loc else None,
            water_level=self.water,
        )

    def rescore(self, now: datetime) -> None:
        r = triage.score(
            triage.TriageInput(
                people_count=self.people,
                vulnerability=self.vulnerability,
                water_level=self.water,
                water_rising=self.rising,
                needs=self.needs,
                first_reported_at=self.first_reported_at,
                source_count=len(self.message_ids),
                flood_depth_m=self.flood_depth_m,
                in_flood_zone=self.in_flood_zone,
                minutes_to_danger=self.minutes_to_danger,
                danger_label=self.danger_label,
            ),
            now,
        )
        self.score, self.level, self.breakdown = r.score, r.level, r.breakdown_dicts()


@dataclass
class Outcome:
    case: SimCase
    decision: str  # created | merged | review
    verdict: dedup.Verdict | None
    location: LocationFix | None


class Resolver:
    def __init__(self, gaz: Gazetteer, flood: FloodMap | None, bias: tuple[float, float] | None = None):
        self.gaz, self.flood, self.bias = gaz, flood, bias
        self.cases: list[SimCase] = []
        self.review_pairs: list[tuple[str, str, float]] = []
        self._ids = itertools.count(1)

    def _candidates(self, sig: dedup.Signals) -> list[tuple[SimCase, dedup.Signals]]:
        out = []
        for c in self.cases:
            if c.status == "duplicate":
                continue
            if (sig.phone_hashes | sig.sender_hashes) & (c.phones | c.senders):
                out.append((c, c.signals()))
                continue
            if sig.lat is None or c.location is None:
                continue
            if haversine_m(sig.lat, sig.lng, c.location.lat, c.location.lng) <= dedup.SEARCH_RADIUS_M:
                out.append((c, c.signals()))
        return out

    def ingest(
        self,
        msg_id: str,
        u: Understanding,
        text: str,
        pin: tuple[float, float] | None,
        sender_phone: str | None,
        at: datetime,
    ) -> Outcome:
        e = u.extraction
        loc = locate(self.gaz, text, u, pin, self.bias)
        in_text, sender = phone_keys(u, sender_phone)
        sig = dedup.Signals(
            lat=loc.lat if loc else None,
            lng=loc.lng if loc else None,
            location_confidence=loc.confidence if loc else 0.0,
            phone_hashes=in_text,
            sender_hashes=sender,
            reported_at=at,
            contact_name=e.contact_name,
            address=e.address,
            people_count=e.people_count,
            vulnerability=e.vulnerable.model_dump(),
            location_text=e.location_text,
            anchors=set(loc.anchors) if loc else set(),
            locality=loc.locality if loc else None,
            water_level=e.water_level,
        )
        match = dedup.best_match(sig, self._candidates(sig))
        reasons = review_reasons(loc, u)

        if match and match[1].decision == "merge":
            case, verdict = match
            case.message_ids.append(msg_id)
            case.last_reported_at = max(case.last_reported_at, at)
            case.location = merge.better_location(case.location, loc)
            case.people = merge.merge_people(case.people, e.people_count)
            case.vulnerability = merge.merge_vulnerability(case.vulnerability, e.vulnerable.model_dump())
            case.water = merge.worse_water(case.water, e.water_level)
            case.rising = case.rising or e.water_rising
            case.needs = merge.merge_needs(case.needs, e.needs)
            case.phones |= in_text
            case.senders |= sender
            case.contact_name = case.contact_name or e.contact_name
            case.address = case.address or e.address
            case.location_text = case.location_text or e.location_text
            case.anchors |= sig.anchors
            # a clean location from this report clears an earlier location flag
            if case.location and case.location.confidence >= REVIEW_THRESHOLD:
                case.review = [r for r in case.review if r not in ("location_unknown", "low_confidence_location")]
            case.review = list(dict.fromkeys([*case.review, *[r for r in reasons if r.startswith("reported")]]))
            self._flood(case)
            case.rescore(at)
            return Outcome(case, "merged", verdict, loc)

        case = SimCase(
            id=f"c{next(self._ids):05d}",
            first_reported_at=at,
            last_reported_at=at,
            location=loc,
            people=e.people_count,
            vulnerability=e.vulnerable.model_dump(),
            water=e.water_level,
            rising=e.water_rising,
            needs=list(e.needs),
            phones=in_text,
            senders=sender,
            contact_name=e.contact_name,
            address=e.address,
            location_text=e.location_text,
            summary=e.summary,
            message_ids=[msg_id],
            review=reasons,
            anchors=set(sig.anchors),
        )
        decision = "created"
        if match and match[1].decision == "review":
            case.review.append("possible_duplicate")
            self.review_pairs.append((match[0].id, case.id, match[1].score))
            decision = "review"
        self._flood(case)
        case.rescore(at)
        self.cases.append(case)
        return Outcome(case, decision, match[1] if match else None, loc)

    def rescued_nearby(self, rescued: SimCase) -> list[SimCase]:
        """Open cases that may be the family just rescued: flag them before a second boat goes."""
        if rescued.location is None:
            return []
        base = rescued.signals()
        hits = []
        for c in self.open_cases():
            if c.id == rescued.id or c.location is None:
                continue
            d = haversine_m(c.location.lat, c.location.lng, rescued.location.lat, rescued.location.lng)
            if d <= dedup.RESCUED_NEARBY_M and dedup.compare(c.signals(), base).score >= dedup.RESCUED_NEARBY_SCORE:
                c.review = list(dict.fromkeys([*c.review, "possibly_rescued"]))
                hits.append(c)
        return hits

    def _flood(self, case: SimCase) -> None:
        if self.flood and case.location:
            case.in_flood_zone, case.flood_depth_m = self.flood.depth_at(case.location.lat, case.location.lng)

    def open_cases(self) -> list[SimCase]:
        return [c for c in self.cases if c.status == "open"]
