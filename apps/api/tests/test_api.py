"""Journeys through the real API, database and Redis, with the workers' steps called inline."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import NoReturn

from sqlalchemy import select
from starlette.websockets import WebSocket

from app.actions import planning, resolve
from app.core.db import sessionmaker
from app.core.deps import claims_from
from app.core.settings import get_settings
from app.models import Assignment, Case, Disaster, OutboundMessage, SosMessage, Team
from app.routers.ws import _trusted_origin
from tests.conftest import World, client, login, login_field

SOS_TEXT = "Amma and appa stuck on first floor, water rising, near Kotturpuram Tree Park, Kotturpuram. appa on dialysis"


async def _run_pipeline() -> list[Case]:
    async with sessionmaker()() as s:
        ids = list(
            await s.scalars(
                select(SosMessage.id).where(SosMessage.processing_status == "pending").order_by(SosMessage.received_at)
            )
        )
    cases = []
    for mid in ids:
        async with sessionmaker()() as s:
            if c := await resolve.process(s, mid):
                cases.append(c)
    return cases


async def _plan(disaster_id: uuid.UUID) -> None:
    async with sessionmaker()() as s:
        d = await s.get(Disaster, disaster_id)
        assert d is not None
        await planning.build(s, d)


async def test_health() -> None:
    async with client() as c:
        r = await c.get("/health")
    assert r.json()["database"] == "ok" and r.json()["redis"] == "ok"


async def test_sos_to_rescue_end_to_end(world: World) -> None:
    async with client() as public:
        r = await public.post("/api/v1/sos", json={"text": SOS_TEXT, "phone": "98400 12345", "people": 2})
        assert r.status_code == 201, r.text
        code = r.json()["tracking_code"]
        assert (await public.get(f"/api/v1/sos/{code}")).json()["status"] == "received"

    [case] = await _run_pipeline()
    assert case.urgency_level in ("critical", "high")
    assert case.location_confidence >= 0.8 and case.status == "queued"

    async with sessionmaker()() as s:
        truck = await s.get(Team, world.truck.id)
        assert truck is not None
        truck.status = "off_duty"  # leave the lead's boat as the only team on duty
        await s.commit()
    await _plan(world.disaster.id)
    async with client() as coord:
        await login(coord, world.coordinator.email or "")
        plan = (await coord.get("/api/v1/dispatch/plan", params={"disaster_id": str(world.disaster.id)})).json()
        stop = next(s for s in plan["stops"] if s["case_id"] == str(case.id))
        assert stop["reasons"]
        r = await coord.post(
            f"/api/v1/dispatch/plan/{plan['id']}/approve", json={"assignment_ids": [stop["assignment_id"]]}
        )
        assert r.status_code == 200 and len(r.json()["approved"]) == 1

    async with client() as crew:
        await login_field(crew, world.lead.phone or "")
        now = (await crew.get("/api/v1/field/assignments/current")).json()
        assert now["current"]["case"]["id"] == str(case.id)
        assert now["current"]["case"]["contact_phone"] == "+919840012345"  # crews may call the family
        aid = now["current"]["assignment"]["id"]
        for status in ("started", "reached"):
            assert (await crew.patch(f"/api/v1/field/assignments/{aid}", json={"status": status})).status_code == 200
        r = await crew.patch(
            f"/api/v1/field/assignments/{aid}", json={"status": "completed", "people_rescued": 2, "client_id": "tap-1"}
        )
        assert r.status_code == 200
        # the offline queue retrying the same tap changes nothing
        again = await crew.patch(
            f"/api/v1/field/assignments/{aid}", json={"status": "completed", "people_rescued": 2, "client_id": "tap-1"}
        )
        assert again.status_code == 200

    async with client() as public:
        body = (await public.get(f"/api/v1/sos/{code}")).json()
    assert body["status"] == "rescued"
    assert [s["key"] for s in body["steps"]][-1] == "rescued"
    assert "phone" not in json.dumps(body).lower()


async def test_a_disaster_with_plans_and_assignments_can_be_deleted(world: World) -> None:
    # replays are deleted and rebuilt on restart; plans, assignments and merges must not block that
    async with client() as public:
        await public.post("/api/v1/sos", json={"text": SOS_TEXT, "people": 2})
    [case] = await _run_pipeline()
    await _plan(world.disaster.id)
    async with sessionmaker()() as s:
        assert await s.scalar(select(Assignment.plan_id).where(Assignment.case_id == case.id)) is not None
        d = await s.get(Disaster, world.disaster.id)
        await s.delete(d)
        await s.commit()
        assert await s.get(Disaster, world.disaster.id) is None


async def test_duplicates_merge_into_one_case(world: World) -> None:
    async with client() as public:
        for text in (
            "SOS 4 people stuck at Kotturpuram near Kotturpuram Tree Park, water chest level, call 98400 55555",
            "My relatives at Kotturpuram Tree Park Kotturpuram, family of 4, chest deep water. 9840055555",
        ):
            assert (await public.post("/api/v1/sos", json={"text": text})).status_code == 201
    await _run_pipeline()
    async with sessionmaker()() as s:
        cases = list(await s.scalars(select(Case).where(Case.status != "duplicate")))
    assert len(cases) == 1 and cases[0].source_count == 2


async def test_low_confidence_location_waits_for_review_then_dispatches(world: World) -> None:
    async with client() as public:
        await public.post("/api/v1/sos", json={"text": "3 people stuck in Mudichur, water waist deep"})
    [case] = await _run_pipeline()
    assert case.status == "needs_review" and "low_confidence_location" in case.review_reasons
    async with client() as coord:
        await login(coord, world.coordinator.email or "")
        review = (await coord.get("/api/v1/review", params={"disaster_id": str(world.disaster.id)})).json()
        assert [c["id"] for c in review["cases"]] == [str(case.id)]
        r = await coord.patch(
            f"/api/v1/cases/{case.id}", json={"lat": 12.9155, "lng": 80.0700, "version": case.version}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "queued" and r.json()["location_source"] == "manual"
        stale = await coord.patch(f"/api/v1/cases/{case.id}", json={"people_count": 4, "version": case.version})
        assert stale.status_code == 409


async def test_roles_and_scopes(world: World) -> None:
    did = str(world.disaster.id)
    async with client() as anon:
        assert (await anon.get(f"/api/v1/disasters/{did}/cases")).status_code == 401
    async with client() as outsider:
        await login(outsider, world.outsider.email or "")
        assert (await outsider.get(f"/api/v1/disasters/{did}/cases")).status_code == 404
    async with client() as viewer:
        await login(viewer, world.viewer.email or "")
        assert (await viewer.get(f"/api/v1/disasters/{did}/cases")).status_code == 200
        r = await viewer.post("/api/v1/dispatch/replan", json={"disaster_id": did})
        assert r.status_code == 403
    async with client() as crew:
        await login_field(crew, world.lead.phone or "")
        assert (await crew.get(f"/api/v1/disasters/{did}/cases")).status_code == 403


async def test_viewers_never_see_phones_or_diagnoses(world: World) -> None:
    async with client() as public:
        await public.post("/api/v1/sos", json={"text": SOS_TEXT + " call 98400 77777"})
    [case] = await _run_pipeline()
    async with client() as viewer:
        await login(viewer, world.viewer.email or "")
        data = (await viewer.get(f"/api/v1/cases/{case.id}")).json()
    assert data["vulnerability"]["medical"] == ["restricted"]
    assert "98400" not in json.dumps(data)
    assert all(s["text"] is None for s in data["sources"])
    async with sessionmaker()() as s:
        raw = (await s.execute(select(SosMessage.raw_text).where(SosMessage.case_id == case.id))).scalar()
        stored = await s.scalar(select(SosMessage).where(SosMessage.case_id == case.id))
    assert raw and "dialysis" in raw  # decrypted for the app
    assert stored is not None


async def test_refresh_rotates_and_a_dead_session_clears_cookies(world: World) -> None:
    async with client() as coord:
        await login(coord, world.coordinator.email or "")
        old = coord.cookies.get("rg_rt")
        assert (await coord.post("/api/v1/auth/refresh")).status_code == 200
        assert coord.cookies.get("rg_rt") != old
    async with client() as stale:
        r = await stale.post("/api/v1/auth/refresh", headers={"Cookie": f"rg_rt={old}"})
    assert r.status_code == 401
    cleared = r.headers.get_list("set-cookie")
    assert any(c.startswith("rg_role=") and "Max-Age=0" in c for c in cleared)


def test_websockets_refuse_other_sites() -> None:
    def socket(origin: str | None) -> WebSocket:
        headers = [(b"host", b"rescue.example")] + ([(b"origin", origin.encode())] if origin else [])
        return WebSocket({"type": "websocket", "headers": headers, "path": "/ws/field"}, _never, _never)

    assert not _trusted_origin(socket("https://evil.example"))
    assert _trusted_origin(socket("http://localhost:3100"))  # the dev web app
    assert _trusted_origin(socket("https://rescue.example"))  # same host behind the proxy
    assert _trusted_origin(socket(None))  # not a browser, no ambient cookie


async def test_ws_ticket_opens_a_socket_but_not_the_api(world: World) -> None:
    async with client() as c:
        await login(c, world.coordinator.email or "")
        r = await c.post("/api/v1/auth/ws-ticket")
        assert r.status_code == 200, r.text
        ticket = r.json()["ticket"]
    sock = WebSocket(
        {"type": "websocket", "headers": [], "path": "/ws/field", "query_string": f"ticket={ticket}".encode()},
        _never,
        _never,
    )
    claims = claims_from(sock)
    assert claims is not None and claims.user_id == world.coordinator.id
    async with client() as c:
        r = await c.get("/api/v1/auth/me", headers={"authorization": f"Bearer {ticket}"})
        assert r.status_code == 401  # a socket ticket is not a session


async def _never(*_: object) -> NoReturn:
    raise AssertionError("the origin check must not touch the connection")


async def test_admin_reset_link_sets_a_new_password_and_ends_old_sessions(world: World) -> None:
    async with client() as old_device:
        await login(old_device, world.coordinator.email or "")
        async with client() as admin:
            await login(admin, world.admin.email or "")
            r = await admin.post(f"/api/v1/admin/users/{world.coordinator.id}/reset-link")
            assert r.status_code == 201, r.text
            token = r.json()["link"].rsplit("/", 1)[1]
            crew = await admin.post(f"/api/v1/admin/users/{world.lead.id}/reset-link")
            assert crew.status_code == 409  # field leads sign in by phone code
        async with client() as anyone:
            info = (await anyone.get(f"/api/v1/auth/invite/{token}")).json()
            assert info["reset"] is True and info["email"] == world.coordinator.email
            r = await anyone.post(
                "/api/v1/auth/invite/accept", json={"token": token, "password": "a brand new passphrase"}
            )
            assert r.status_code == 200, r.text
            again = await anyone.post(
                "/api/v1/auth/invite/accept", json={"token": token, "password": "another one here"}
            )
            assert again.status_code == 404
        assert (await old_device.post("/api/v1/auth/refresh")).status_code == 401
    async with client() as fresh:
        r = await fresh.post(
            "/api/v1/auth/login", json={"email": world.coordinator.email, "password": "a brand new passphrase"}
        )
        assert r.status_code == 200


async def test_csrf_header_required_for_cookie_writes(world: World) -> None:
    async with client() as coord:
        await login(coord, world.coordinator.email or "")
        r = await coord.post(
            "/api/v1/dispatch/replan", json={"disaster_id": str(world.disaster.id)}, headers={"X-Requested-With": ""}
        )
    assert r.status_code == 403


async def test_whatsapp_webhook_checks_signature_and_ingests(world: World, monkeypatch: object) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_app_secret", type(settings.jwt_secret)("app-secret"))  # type: ignore[attr-defined]
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "919840011111", "profile": {"name": "Priya"}}],
                            "messages": [
                                {
                                    "from": "919840011111",
                                    "id": "wamid.1",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "5 people on terrace at Kotturpuram near Kotturpuram Tree Park"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    good = "sha256=" + hmac.new(b"app-secret", raw, hashlib.sha256).hexdigest()
    async with client() as c:
        bad = await c.post("/api/v1/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": "sha256=00"})
        assert bad.status_code == 401
        ok = await c.post("/api/v1/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": good})
        assert ok.json() == {"queued": 1, "pins": 0}
        again = await c.post("/api/v1/webhooks/whatsapp", content=raw, headers={"x-hub-signature-256": good})
        assert again.json()["queued"] == 0  # Meta retries are idempotent
    [case] = await _run_pipeline()
    async with sessionmaker()() as s:
        sent = list(await s.scalars(select(OutboundMessage).where(OutboundMessage.case_id == case.id)))
    # without Cloud API credentials every reply is logged as skipped, never silently dropped
    assert sent and all(m.status == "skipped" for m in sent)


async def test_demo_login_and_public_context(world: World) -> None:
    async with client() as c:
        ctx = (await c.get("/api/v1/sos/context")).json()
        assert ctx["available"] and ctx["name"] == "Test flood"
        r = await c.post("/api/v1/auth/demo", json={"role": "coordinator"})
        assert r.status_code == 503  # demo accounts are not seeded in tests
