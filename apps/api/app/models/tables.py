"""Every table in Rescue Grid. See docs/05-Backend-Schema.md for the reasoning."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedText
from app.models.base import Base, IdMixin, LineString, MultiPolygon, Point, TimestampMixin, tstz

ROLES = ("admin", "coordinator", "field_lead", "viewer")
LANGUAGES = ("en", "ta", "hi", "ml", "te")
CHANNELS = ("whatsapp", "web_form", "csv_import", "helpline", "twitter", "replay")
CASE_STATUSES = (
    "new",
    "needs_review",
    "queued",
    "assigned",
    "en_route",
    "on_scene",
    "rescued",
    "unreachable",
    "duplicate",
    "false_alarm",
    "closed",
)
OPEN_CASE_STATUSES = ("new", "needs_review", "queued", "assigned", "en_route", "on_scene", "unreachable")
TERMINAL_CASE_STATUSES = ("rescued", "duplicate", "false_alarm", "closed")
ASSET_TYPES = ("boat", "truck", "medical", "foot", "helicopter")
TEAM_STATUSES = ("off_duty", "available", "assigned", "en_route", "on_scene", "returning")
ASSIGNMENT_ACTIVE = ("approved", "started", "reached")


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(16))  # govt | ngo | volunteer


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    phone: Mapped[str | None] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    preferred_language: Mapped[str] = mapped_column(String(4), server_default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(tstz())


class UserSession(IdMixin, TimestampMixin, Base):
    """A refresh session. Field devices hold one for days; revoking it logs the device out."""

    __tablename__ = "user_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(String(8))  # staff | field
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(tstz())
    revoked_at: Mapped[datetime | None] = mapped_column(tstz())
    last_used_at: Mapped[datetime | None] = mapped_column(tstz())


class Invite(IdMixin, TimestampMixin, Base):
    __tablename__ = "invites"
    email: Mapped[str] = mapped_column(Text, index=True)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(String(8), server_default="invite")  # invite | reset
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(tstz())
    accepted_at: Mapped[datetime | None] = mapped_column(tstz())


class PushSubscription(IdMixin, TimestampMixin, Base):
    __tablename__ = "push_subscriptions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)


class Disaster(IdMixin, TimestampMixin, Base):
    __tablename__ = "disasters"
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # active | closed | replay
    description: Mapped[str | None] = mapped_column(Text)
    area: Mapped[Any] = mapped_column(MultiPolygon(), nullable=True)
    started_at: Mapped[datetime] = mapped_column(tstz(), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(tstz())
    replay_dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("replay_datasets.id"))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    purged_at: Mapped[datetime | None] = mapped_column(tstz())

    __table_args__ = (Index("ix_disasters_area", "area", postgresql_using="gist"),)


class DisasterOrganization(Base):
    __tablename__ = "disaster_organizations"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    __table_args__ = (PrimaryKeyConstraint("disaster_id", "organization_id"),)


class FloodZone(IdMixin, TimestampMixin, Base):
    __tablename__ = "flood_zones"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[Any] = mapped_column(MultiPolygon())
    depth_estimate_m: Mapped[float | None] = mapped_column(Numeric(4, 2))
    source: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(tstz(), server_default=func.now())

    __table_args__ = (
        Index("ix_flood_zones_geom", "geom", postgresql_using="gist"),
        Index("ix_flood_zones_disaster", "disaster_id"),
    )


class SosMessage(IdMixin, TimestampMixin, Base):
    """Raw intake. Immutable except for processing bookkeeping and the retention purge."""

    __tablename__ = "sos_messages"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str | None] = mapped_column(Text)
    tracking_code: Mapped[str] = mapped_column(String(12), unique=True)
    sender_phone: Mapped[str | None] = mapped_column(EncryptedText())
    sender_phone_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    sender_name: Mapped[str | None] = mapped_column(EncryptedText())
    raw_text: Mapped[str | None] = mapped_column(EncryptedText())
    text_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_location: Mapped[Any] = mapped_column(Point(), nullable=True)
    received_at: Mapped[datetime] = mapped_column(tstz())
    processing_status: Mapped[str] = mapped_column(String(16), server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    purged_at: Mapped[datetime | None] = mapped_column(tstz())

    __table_args__ = (
        UniqueConstraint("channel", "external_id", name="uq_sos_messages_channel_external_id"),
        Index(
            "ix_sos_messages_pending",
            "processing_status",
            postgresql_where=text("processing_status = 'pending'"),
        ),
        Index("ix_sos_messages_case", "case_id"),
        Index("ix_sos_messages_disaster_received", "disaster_id", "received_at"),
    )


class Extraction(IdMixin, TimestampMixin, Base):
    __tablename__ = "extractions"
    sos_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sos_messages.id", ondelete="CASCADE"), unique=True)
    people_count: Mapped[int | None] = mapped_column(Integer)
    vulnerable: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    location_text: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(Text)
    landmarks: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    address: Mapped[str | None] = mapped_column(Text)
    water_level: Mapped[str | None] = mapped_column(String(16))
    water_rising: Mapped[bool | None] = mapped_column(Boolean)
    needs: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    language: Mapped[str | None] = mapped_column(String(8))
    status_update: Mapped[str] = mapped_column(String(16), server_default="none")
    contact_name: Mapped[str | None] = mapped_column(EncryptedText())
    contact_phone_hashes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    summary: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))


class Case(IdMixin, TimestampMixin, Base):
    """One real-world household or location, built from one or more SOS messages."""

    __tablename__ = "cases"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    tracking_code: Mapped[str] = mapped_column(String(12), unique=True)
    location: Mapped[Any] = mapped_column(Point(), nullable=True)
    location_confidence: Mapped[float] = mapped_column(Float, server_default="0")
    location_source: Mapped[str] = mapped_column(String(16), server_default="unknown")
    location_candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    address_text: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(Text)
    people_count: Mapped[int | None] = mapped_column(Integer)
    vulnerability: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    needs: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    water_level: Mapped[str | None] = mapped_column(String(16))
    water_rising: Mapped[bool | None] = mapped_column(Boolean)
    in_flood_zone: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    flood_depth_m: Mapped[float | None] = mapped_column(Float)
    urgency_score: Mapped[int] = mapped_column(Integer, server_default="0")
    urgency_level: Mapped[str] = mapped_column(String(12), server_default="low")
    score_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), server_default="new")
    review_reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"))
    contact_phone: Mapped[str | None] = mapped_column(EncryptedText())
    contact_phone_hashes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    sender_phone_hashes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    location_anchors: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    contact_name: Mapped[str | None] = mapped_column(EncryptedText())
    summary: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))
    first_reported_at: Mapped[datetime] = mapped_column(tstz())
    last_reported_at: Mapped[datetime] = mapped_column(tstz())
    source_count: Mapped[int] = mapped_column(Integer, server_default="1")
    current_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    assigned_at: Mapped[datetime | None] = mapped_column(tstz())
    rescued_at: Mapped[datetime | None] = mapped_column(tstz())
    closed_at: Mapped[datetime | None] = mapped_column(tstz())
    people_rescued: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    # the latest water clock from the flood nowcast (app.services.waterclock), with its issue time
    water_clock: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_cases_location", "location", postgresql_using="gist"),
        Index("ix_cases_queue", "disaster_id", "status", text("urgency_score DESC")),
        Index("ix_cases_disaster_updated", "disaster_id", "updated_at"),
    )


class ReviewPair(IdMixin, TimestampMixin, Base):
    """Two cases that might be the same household; a coordinator decides."""

    __tablename__ = "review_pairs"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    case_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    case_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(12), server_default="open")  # open|merged|dismissed
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(tstz())

    __table_args__ = (
        UniqueConstraint("case_a_id", "case_b_id", name="uq_review_pairs_cases"),
        Index("ix_review_pairs_open", "disaster_id", "status"),
    )


class CaseEvent(Base):
    """Append-only audit log: who changed what, when.

    A trigger chains every row to the one before it in the same disaster (seq, prev_hash,
    hash: SHA-256 over the previous hash and this row) and refuses updates, so an edit is
    impossible and a deletion shows up as a break (app.actions.audit)."""

    __tablename__ = "case_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    actor_type: Mapped[str] = mapped_column(String(8))  # system | user | team
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_label: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(tstz())
    seq: Mapped[int | None] = mapped_column(BigInteger)  # set by the chain trigger
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_case_events_case", "case_id", "created_at"),
        Index("ix_case_events_disaster", "disaster_id", "created_at"),
        Index("ix_case_events_chain", "disaster_id", "seq"),
    )


class AuditHead(Base):
    """The newest link of each disaster's audit chain. Its row lock serializes appends."""

    __tablename__ = "audit_heads"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, server_default="0")
    hash: Mapped[str] = mapped_column(String(64), server_default="")


class OutboundMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "outbound_messages"
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    to_phone: Mapped[str | None] = mapped_column(EncryptedText())
    to_phone_hash: Mapped[str | None] = mapped_column(String(64))
    template: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(4))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), server_default="queued")
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(tstz())


class Team(IdMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    call_sign: Mapped[str] = mapped_column(String(16))
    asset_type: Mapped[str] = mapped_column(String(12))
    capacity: Mapped[int] = mapped_column(Integer)
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), server_default="off_duty")
    current_location: Mapped[Any] = mapped_column(Point(), nullable=True)
    heading: Mapped[float | None] = mapped_column(Float)
    location_updated_at: Mapped[datetime | None] = mapped_column(tstz())
    base_location: Mapped[Any] = mapped_column(Point(), nullable=True)
    base_name: Mapped[str | None] = mapped_column(Text)
    is_virtual: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("disaster_id", "call_sign", name="uq_teams_disaster_call_sign"),
        Index("ix_teams_location", "current_location", postgresql_using="gist"),
        Index("ix_teams_lead", "lead_user_id"),
    )


class TeamLocation(Base):
    __tablename__ = "team_locations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    location: Mapped[Any] = mapped_column(Point())
    recorded_at: Mapped[datetime] = mapped_column(tstz())
    speed: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index("ix_team_locations_team_time", "team_id", text("recorded_at DESC")),
        Index("ix_team_locations_location", "location", postgresql_using="gist"),
    )


class DispatchPlan(IdMixin, TimestampMixin, Base):
    __tablename__ = "dispatch_plans"
    disaster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("disasters.id", ondelete="CASCADE"))
    created_by: Mapped[str] = mapped_column(Text)  # "optimizer" or a user id
    status: Mapped[str] = mapped_column(String(12))  # proposed | approved | superseded
    objective_value: Mapped[float | None] = mapped_column(Float)
    solver_ms: Mapped[int | None] = mapped_column(Integer)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(tstz())

    __table_args__ = (Index("ix_dispatch_plans_disaster", "disaster_id", "status"),)


class Assignment(IdMixin, TimestampMixin, Base):
    __tablename__ = "assignments"
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dispatch_plans.id", ondelete="SET NULL"))
    sequence: Mapped[int] = mapped_column(Integer)
    route: Mapped[Any] = mapped_column(LineString(), nullable=True)
    route_source: Mapped[str | None] = mapped_column(String(12))
    distance_m: Mapped[int | None] = mapped_column(Integer)
    travel_s: Mapped[int | None] = mapped_column(Integer)
    eta: Mapped[datetime | None] = mapped_column(tstz())
    status: Mapped[str] = mapped_column(String(12))
    reasons: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(tstz())
    started_at: Mapped[datetime | None] = mapped_column(tstz())
    reached_at: Mapped[datetime | None] = mapped_column(tstz())
    completed_at: Mapped[datetime | None] = mapped_column(tstz())
    outcome_people_rescued: Mapped[int | None] = mapped_column(Integer)
    outcome_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_assignments_case", "case_id"),
        Index("ix_assignments_team_status", "team_id", "status"),
        Index("ix_assignments_plan", "plan_id"),
    )


class ReplayDataset(IdMixin, TimestampMixin, Base):
    __tablename__ = "replay_datasets"
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    message_count: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(tstz())
    ends_at: Mapped[datetime] = mapped_column(tstz())
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
