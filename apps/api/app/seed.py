"""Demo data: organisations, accounts, a live drill with flood zones, teams and a flood model. Safe to rerun.

uv run python -m app.seed            # add what is missing
uv run python -m app.seed --reset    # dev only: empty the database and Redis first
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.actions import geo, intake, replay
from app.core.clock import utcnow
from app.core.db import engine, sessionmaker
from app.core.logging import configure_logging, log
from app.core.redis import redis
from app.core.security import hash_password
from app.core.settings import get_settings
from app.models import Base, Disaster, DisasterOrganization, FloodZone, Organization, Team, User

ORGS = [("Greater Chennai Corporation EOC", "govt"), ("Tamil Nadu SDRF", "govt"), ("Chennai Volunteers Network", "ngo")]
DRILL = "Chennai monsoon drill"
DRILL_TEAMS = [
    ("B-01", "boat", 8, "+910000000701", "Velachery boat crew"),
    ("B-02", "boat", 8, "+910000000702", "Saidapet boat crew"),
    ("B-03", "boat", 6, "+910000000703", "Mudichur fishermen"),
    ("B-04", "boat", 6, "+910000000704", "Kotturpuram fishermen"),
    ("T-01", "truck", 12, "+910000000711", "Guindy fire and rescue"),
    ("T-02", "truck", 12, "+910000000712", "Tambaram fire and rescue"),
    ("M-01", "medical", 4, "+910000000721", "Medical team, Adyar"),
    ("H-01", "helicopter", 4, None, "IAF Arakkonam"),
]
SEED_MESSAGES = 60


async def upsert_user(
    session, email: str | None, phone: str | None, name: str, role: str, org_id, password: str | None
) -> User:  # type: ignore[no-untyped-def]
    q = select(User).where(User.email == email) if email else select(User).where(User.phone == phone)
    user = await session.scalar(q)
    if user is None:
        user = User(
            email=email,
            phone=phone,
            name=name,
            role=role,
            organization_id=org_id,
            password_hash=hash_password(password) if password else None,
        )
        session.add(user)
        await session.flush()
    return user


def drill_flood_model(now: datetime) -> dict | None:
    """The 2015 forecast, timed so the drill's "now" is the moment its seeded reports come from."""
    rows = [m for m in replay.messages("chennai-2015") if m["truth"]["kind"] == "sos"][:SEED_MESSAGES]
    meta = replay.meta("chennai-2015")
    if not rows:
        return None
    at = (datetime.fromisoformat(rows[-1]["t"]) - datetime.fromisoformat(meta["starts_at"])).total_seconds() / 60
    return replay.flood_model("chennai-2015", now - timedelta(minutes=at))


async def reset() -> None:
    if get_settings().env == "prod":
        raise SystemExit("refusing to reset a production database")
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await redis().flushdb()


async def main() -> None:
    configure_logging()
    if "--reset" in sys.argv:
        await reset()
    password = os.environ.get("SEED_PASSWORD", "rescuegrid-demo")
    async with sessionmaker()() as s:
        orgs = {}
        for name, kind in ORGS:
            org = await s.scalar(select(Organization).where(Organization.name == name))
            if org is None:
                org = Organization(name=name, type=kind)
                s.add(org)
                await s.flush()
            orgs[name] = org
        eoc = orgs[ORGS[0][0]]
        await upsert_user(s, "admin@demo.rescuegrid.in", None, "Divya Raman", "admin", eoc.id, password)
        await upsert_user(
            s, "coordinator@demo.rescuegrid.in", None, "Karthik Subramanian", "coordinator", eoc.id, password
        )
        await upsert_user(s, "viewer@demo.rescuegrid.in", None, "Press desk", "viewer", eoc.id, password)

        drill = await s.scalar(select(Disaster).where(Disaster.name == DRILL))
        if drill is None:
            meta = replay.meta("chennai-2015")
            drill = Disaster(
                name=DRILL,
                status="active",
                area=geo.multipolygon(meta["area"]),
                started_at=utcnow() - timedelta(hours=3),
                description="A live drill on the 2015 flood footprint. Report an SOS to see it arrive.",
                settings={"flood_model": model} if (model := drill_flood_model(utcnow())) else {},
            )
            s.add(drill)
            await s.flush()
            for org in orgs.values():
                s.add(DisasterOrganization(disaster_id=drill.id, organization_id=org.id))
            zones = json.loads(
                (get_settings().data_dir / "replay" / "chennai-2015" / "flood_zones.geojson").read_text(
                    encoding="utf-8"
                )
            )
            for f in zones["features"]:
                s.add(
                    FloodZone(
                        disaster_id=drill.id,
                        name=f["properties"]["name"],
                        geom=geo.multipolygon(f["geometry"]),
                        depth_estimate_m=f["properties"]["depth_m"],
                        source=f["properties"]["source"],
                    )
                )
            bases = meta["teams"]
            sdrf = orgs["Tamil Nadu SDRF"]
            for i, (call, asset, cap, phone, label) in enumerate(DRILL_TEAMS):
                lead = await upsert_user(s, None, phone, label, "field_lead", sdrf.id, None) if phone else None
                base = bases[(i * 3) % len(bases)]
                s.add(
                    Team(
                        disaster_id=drill.id,
                        organization_id=sdrf.id,
                        call_sign=call,
                        asset_type=asset,
                        capacity=cap,
                        lead_user_id=lead.id if lead else None,
                        status="available" if asset != "helicopter" else "off_duty",
                        current_location=geo.point(base["lat"], base["lng"]),
                        base_location=geo.point(base["lat"], base["lng"]),
                        base_name=base["base_name"],
                        location_updated_at=utcnow(),
                    )
                )
            await replay.ensure_dataset(s, "chennai-2015")
            await s.commit()

            # a live board needs traffic: the opening hours of the replay, shifted to the last two hours
            rows = [m for m in replay.messages("chennai-2015") if m["truth"]["kind"] == "sos"][:SEED_MESSAGES]
            ids = []
            for i, m in enumerate(rows):
                msg, created = await intake.ingest(
                    s,
                    intake.Incoming(
                        disaster_id=drill.id,
                        channel=m["channel"] if m["channel"] != "twitter" else "web_form",
                        text=m["text"],
                        received_at=utcnow() - timedelta(minutes=120 - i * 2),
                        external_id=f"seed:{m['id']}" if m["channel"] in ("whatsapp", "csv_import") else None,
                        pin=tuple(m["pin"]) if m.get("pin") else None,  # type: ignore[arg-type]
                        meta={"seeded": True},
                    ),
                )
                if created:
                    ids.append(msg.id)
            await intake.enqueue(ids)
            log.info("seed.drill", disaster=str(drill.id), messages=len(ids))
        elif "flood_model" not in (drill.settings or {}) and (model := drill_flood_model(utcnow())):
            # a drill seeded before the water clock existed gets one now
            drill.settings = {**(drill.settings or {}), "flood_model": model}
            log.info("seed.drill_flood_model", disaster=str(drill.id))
        await s.commit()
    print("seeded: admin@ / coordinator@ / viewer@demo.rescuegrid.in, field lead +910000000701")


if __name__ == "__main__":
    asyncio.run(main())
