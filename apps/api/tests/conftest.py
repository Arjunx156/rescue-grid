"""Tests run against real Postgres+PostGIS (rescuegrid_test) and Redis db 1: spatial queries,
encryption and streams are exercised for real, not mocked."""

from __future__ import annotations

import os

os.environ.update(
    {
        "ENV": "test",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", "postgresql+asyncpg://rescuegrid:rescuegrid@localhost:5432/rescuegrid_test"
        ),
        "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1"),
        "LLM_PROVIDER": "local",
        "OTP_DEV_ECHO": "true",
        "DEMO_MODE": "true",
        "ROUTER": "estimate",
        "WORKERS_INLINE": "false",
        "DISPATCH_TIME_LIMIT_S": "0.5",
    }
)

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy import text

from app.actions import geo
from app.core.db import sessionmaker
from app.core.redis import redis
from app.core.security import hash_password
from app.main import app
from app.models import Base, Disaster, DisasterOrganization, Organization, Team, User

CHENNAI = {
    "type": "Polygon",
    "coordinates": [[[79.98, 12.82], [80.33, 12.82], [80.33, 13.22], [79.98, 13.22], [79.98, 12.82]]],
}
PASSWORD = "correct horse battery"


@dataclass
class World:
    org: Organization
    other_org: Organization
    disaster: Disaster
    admin: User
    coordinator: User
    viewer: User
    outsider: User
    lead: User
    boat: Team
    truck: Team


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with sessionmaker()() as s:
        await s.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await s.commit()
    await redis().flushdb()
    yield


@pytest.fixture
async def world() -> World:
    async with sessionmaker()() as s:
        org = Organization(name="Chennai District EOC", type="govt")
        other = Organization(name="Elsewhere NGO", type="ngo")
        s.add_all([org, other])
        await s.flush()
        d = Disaster(name="Test flood", status="active", area=geo.multipolygon(CHENNAI))
        s.add(d)
        await s.flush()
        s.add(DisasterOrganization(disaster_id=d.id, organization_id=org.id))
        users = {
            role: User(
                email=f"{role}@test.in",
                name=role.title(),
                role=role,
                organization_id=o.id,
                password_hash=hash_password(PASSWORD),
            )
            for role, o in (("admin", org), ("coordinator", org), ("viewer", org))
        }
        outsider = User(
            email="outsider@test.in",
            name="Outsider",
            role="coordinator",
            organization_id=other.id,
            password_hash=hash_password(PASSWORD),
        )
        lead = User(phone="+919876500001", name="Lead", role="field_lead", organization_id=org.id)
        s.add_all([*users.values(), outsider, lead])
        await s.flush()
        boat = Team(
            disaster_id=d.id,
            call_sign="B-01",
            asset_type="boat",
            capacity=6,
            status="available",
            lead_user_id=lead.id,
            current_location=geo.point(12.99, 80.22),
            base_location=geo.point(12.99, 80.22),
        )
        truck = Team(
            disaster_id=d.id,
            call_sign="T-01",
            asset_type="truck",
            capacity=12,
            status="available",
            current_location=geo.point(12.98, 80.21),
            base_location=geo.point(12.98, 80.21),
        )
        s.add_all([boat, truck])
        await s.commit()
        return World(org, other, d, users["admin"], users["coordinator"], users["viewer"], outsider, lead, boat, truck)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"X-Requested-With": "rescuegrid"}
    )


async def login(c: httpx.AsyncClient, email: str) -> None:
    r = await c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text


async def login_field(c: httpx.AsyncClient, phone: str) -> None:
    r = await c.post("/api/v1/auth/otp/request", json={"phone": phone})
    code = r.json()["dev_code"]
    r = await c.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
