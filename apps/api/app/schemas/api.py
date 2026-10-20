"""Response and request shapes. The web app's types are generated from these (just types)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class Factor(BaseModel):
    key: str
    label: str
    points: int
    detail: str = ""


class LocationCandidate(BaseModel):
    lat: float
    lng: float
    label: str
    confidence: float


class WaterClockOut(BaseModel):
    """Minutes are counted from issued_at, on the disaster's clock; the client counts down."""

    issued_at: datetime
    depth_m: float
    danger_m: float
    danger_label: str
    minutes: float | None
    early: float | None
    late: float | None
    rise_cm_h: float


class CaseOut(BaseModel):
    id: uuid.UUID
    disaster_id: uuid.UUID
    tracking_code: str
    status: str
    urgency_score: int
    urgency_level: str
    score_breakdown: list[Factor]
    lat: float | None
    lng: float | None
    location_confidence: float
    location_source: str
    address_text: str | None
    locality: str | None
    location_candidates: list[LocationCandidate]
    people_count: int | None
    vulnerability: dict[str, Any]
    needs: list[str]
    water_level: str | None
    water_rising: bool | None
    in_flood_zone: bool
    flood_depth_m: float | None
    summary: str | None
    language: str | None
    source_count: int
    review_reasons: list[str]
    contact_name: str | None
    contact_phone: str | None
    first_reported_at: datetime
    last_reported_at: datetime
    assigned_at: datetime | None
    rescued_at: datetime | None
    people_rescued: int | None
    current_team_id: uuid.UUID | None
    merged_into_id: uuid.UUID | None
    updated_at: datetime | None
    version: int
    water_clock: WaterClockOut | None = None


class SourceOut(BaseModel):
    id: uuid.UUID
    channel: str
    tracking_code: str
    received_at: datetime
    text: str | None
    sender: str | None
    pin: list[float] | None
    language: str | None
    summary: str | None
    provider: str | None
    model: str | None
    confidence: float | None


class EventOut(BaseModel):
    id: int
    event_type: str
    actor_type: str
    actor_label: str | None
    payload: dict[str, Any]
    created_at: datetime


class AssignmentOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    team_id: uuid.UUID
    team_call_sign: str | None = None
    plan_id: uuid.UUID | None
    sequence: int
    status: str
    eta: datetime | None
    distance_m: int | None
    travel_s: int | None
    reasons: list[str]
    route: list[list[float]] | None
    route_source: str | None
    approved_at: datetime | None
    started_at: datetime | None
    reached_at: datetime | None
    completed_at: datetime | None
    outcome_people_rescued: int | None
    outcome_note: str | None


class ReviewPairOut(BaseModel):
    id: uuid.UUID
    case_a_id: uuid.UUID
    case_b_id: uuid.UUID
    score: float
    reasons: list[dict[str, Any]]
    status: str
    created_at: datetime


class CaseDetail(CaseOut):
    sources: list[SourceOut]
    events: list[EventOut]
    assignments: list[AssignmentOut]
    review_pairs: list[ReviewPairOut]


class TeamOut(BaseModel):
    id: uuid.UUID
    disaster_id: uuid.UUID
    call_sign: str
    asset_type: str
    capacity: int
    status: str
    lat: float | None
    lng: float | None
    heading: float | None
    location_updated_at: datetime | None
    base_name: str | None
    base_lat: float | None
    base_lng: float | None
    organization: str | None
    lead_name: str | None
    lead_phone: str | None
    is_virtual: bool
    active_assignment_id: uuid.UUID | None = None
    active_case_id: uuid.UUID | None = None
    queued: int = 0


class FloodZoneOut(BaseModel):
    id: uuid.UUID
    name: str | None
    depth_estimate_m: float | None
    source: str
    geometry: dict[str, Any]


class DisasterOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    description: str | None
    started_at: datetime
    ended_at: datetime | None
    center: list[float] | None
    bbox: list[float] | None
    area: dict[str, Any] | None
    settings: dict[str, Any]
    replay_dataset_id: uuid.UUID | None
    now: datetime


class PlanStop(BaseModel):
    assignment_id: uuid.UUID
    case_id: uuid.UUID
    team_id: uuid.UUID
    sequence: int
    status: str
    eta: datetime | None
    distance_m: int | None
    travel_s: int | None
    reasons: list[str]
    route: list[list[float]] | None


class PlanOut(BaseModel):
    id: uuid.UUID | None
    status: str
    created_at: datetime | None
    solver_ms: int | None
    stats: dict[str, Any]
    stops: list[PlanStop]
    dropped: list[dict[str, Any]]


class Counters(BaseModel):
    open: int
    critical: int
    needs_review: int
    assigned: int
    rescued: int
    people_rescued: int
    teams_active: int
    teams_on_duty: int
    messages: int


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    role: str
    organization_id: uuid.UUID | None
    organization: str | None = None
    preferred_language: str
    is_active: bool
    team_id: uuid.UUID | None = None
    last_login_at: datetime | None = None


PublicState = Literal[
    "received", "reviewing", "queued", "assigned", "en_route", "on_scene", "rescued", "closed", "unreachable"
]


class PublicStatus(BaseModel):
    tracking_code: str
    status: PublicState
    steps: list[dict[str, Any]]
    team_call_sign: str | None
    eta: datetime | None
    updated_at: datetime
    disaster: str


# --- requests ---------------------------------------------------------------


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


class OtpVerifyIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class InviteIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "coordinator", "viewer"]
    organization_id: uuid.UUID | None = None


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class SosIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    phone: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, max_length=120)
    people: int | None = Field(default=None, ge=1, le=200)
    needs: list[str] = Field(default_factory=list, max_length=8)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    language: str | None = Field(default=None, max_length=5)
    website: str | None = Field(default=None, description="honeypot: must stay empty")


class ManualIntakeIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    phone: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class CasePatch(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    people_count: int | None = Field(default=None, ge=1, le=500)
    status: Literal["queued", "false_alarm", "closed", "rescued"] | None = None
    note: str | None = Field(default=None, max_length=500)
    clear_reasons: list[str] | None = None
    version: int | None = None


class MergeIn(BaseModel):
    other_case_id: uuid.UUID


class AssignIn(BaseModel):
    team_id: uuid.UUID


class TeamIn(BaseModel):
    call_sign: str = Field(min_length=1, max_length=16)
    asset_type: Literal["boat", "truck", "medical", "foot", "helicopter"]
    capacity: int = Field(ge=1, le=100)
    lead_phone: str | None = Field(default=None, max_length=20)
    lead_name: str | None = Field(default=None, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    base_name: str | None = Field(default=None, max_length=120)
    organization_id: uuid.UUID | None = None


class TeamPatch(BaseModel):
    status: Literal["off_duty", "available"] | None = None
    capacity: int | None = Field(default=None, ge=1, le=100)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = Field(default=None, max_length=500)


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    speed: float | None = Field(default=None, ge=0, le=500)
    heading: float | None = Field(default=None, ge=0, le=360)
    recorded_at: datetime | None = None


class AssignmentUpdate(BaseModel):
    status: Literal["started", "reached", "completed", "failed"]
    people_rescued: int | None = Field(default=None, ge=0, le=500)
    note: str | None = Field(default=None, max_length=500)
    client_id: str | None = Field(default=None, max_length=64, description="idempotency key from the offline queue")
    at: datetime | None = None


class DisasterIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    area: dict[str, Any] | None = None


class DisasterPatch(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    status: Literal["active", "closed"] | None = None
    area: dict[str, Any] | None = None


class FloodZoneIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    depth_estimate_m: float | None = Field(default=None, ge=0, le=20)
    source: str = Field(default="Drawn by coordinator", max_length=200)
    geometry: dict[str, Any]


class ReplayStartIn(BaseModel):
    dataset: str = Field(default="chennai-2015", pattern=r"^[a-z0-9-]{1,64}$")
    speed: float = Field(default=60, ge=1, le=600)
    autopilot: bool = True


class ReplaySpeedIn(BaseModel):
    speed: float = Field(ge=1, le=600)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: dict[str, str]


class SettingsPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    preferred_language: Literal["en", "ta", "hi", "ml", "te"] | None = None
