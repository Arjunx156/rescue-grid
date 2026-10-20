"""The audit log is a hash chain: no event can be edited, and a missing one is found."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.actions import audit, events
from app.actions.events import SYSTEM
from app.core.clock import utcnow
from app.core.db import sessionmaker
from app.models import Case
from tests.conftest import World, client, login
from tests.test_api import SOS_TEXT, _run_pipeline


async def _case_with_history(world: World) -> Case:
    async with client() as public:
        r = await public.post("/api/v1/sos", json={"text": SOS_TEXT, "phone": "98400 12345", "people": 2})
        assert r.status_code == 201, r.text
    [case] = await _run_pipeline()
    async with sessionmaker()() as s:
        c = await s.get(Case, case.id)
        assert c is not None
        for i in range(3):
            events.record(s, c, "note", SYSTEM, utcnow(), {"n": i})
        await s.commit()
    return case


async def test_chain_is_intact_and_cannot_be_edited(world: World) -> None:
    await _case_with_history(world)
    async with sessionmaker()() as s:
        report = await audit.verify(s, world.disaster.id)
        assert report.intact and report.events >= 4 and report.first_break is None
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("UPDATE case_events SET payload = '{\"n\": 99}' WHERE event_type = 'note'"))
        await s.rollback()


async def test_a_deleted_event_breaks_the_chain_where_it_was(world: World) -> None:
    await _case_with_history(world)
    async with sessionmaker()() as s:
        await s.execute(text("DELETE FROM case_events WHERE seq = 2"))
        await s.commit()
        report = await audit.verify(s, world.disaster.id)
    assert not report.intact
    assert report.first_break is not None and report.first_break.seq == 3
    assert "missing" in report.first_break.reason


async def test_only_admins_read_the_audit_report(world: World) -> None:
    await _case_with_history(world)
    async with client() as c:
        await login(c, world.coordinator.email or "")
        assert (await c.get(f"/api/v1/admin/audit?disaster_id={world.disaster.id}")).status_code == 403
    async with client() as c:
        await login(c, world.admin.email or "")
        r = await c.get(f"/api/v1/admin/audit?disaster_id={world.disaster.id}")
        assert r.status_code == 200, r.text
        assert r.json()["intact"] is True and len(r.json()["head"]) == 64
