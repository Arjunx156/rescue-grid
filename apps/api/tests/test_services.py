from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents import rules
from app.core import crypto
from app.core.settings import Settings, get_settings
from app.services import dedup, dispatch, textnorm, triage
from app.services.geocode import gazetteer, haversine_m

NOW = datetime(2015, 12, 2, 6, 0, tzinfo=UTC)


# --- understanding -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "people", "water", "lang"),
    [
        ("Amma and appa stuck on first floor near Velachery bus depot", 2, "first_floor", "en"),
        ("வேளச்சேரியில் 4 பேர் சிக்கியுள்ளனர். தண்ணீர் கழுத்து வரை", 4, "neck", "ta"),
        ("मुदिचूर में 6 लोग फंसे हैं, पानी कमर तक है", 6, "waist", "hi"),
        ("ముడిచూరులో నలుగురు చిక్కుకున్నారు, నీరు ఛాతీ వరకు ఉంది", 4, "chest", "te"),
        ("sos kotturpuram 10 ppl water 5 feet", 10, "neck", "en"),
    ],
)
def test_reads_headcount_water_and_language(text: str, people: int, water: str, lang: str) -> None:
    e, _ = rules.extract(text)
    assert (e.people_count, e.water_level, e.language) == (people, water, lang)


def test_reads_vulnerability_and_phones_without_inventing() -> None:
    e, phones = rules.extract("2 elderly and a 6 month old baby, father on dialysis. Call 98400 12345")
    assert e.vulnerable.elderly == 2
    assert e.vulnerable.infant == 1
    assert e.vulnerable.medical == ["dialysis"]
    assert phones == ["9840012345"]
    clean, _ = rules.extract("my sister is 8 months pregnant, water waist deep")
    assert clean.vulnerable.infant == 0 and clean.vulnerable.pregnant == 1


def test_status_updates_and_negations() -> None:
    assert rules.extract("Please ignore, they have been rescued by NDRF")[0].status_update == "rescued"
    assert rules.extract("Not yet rescued, water rising")[0].status_update == "none"
    assert rules.extract("Relief camp needs food for 80 people. No rescue needed")[0].needs == ["food"]


def test_phones_never_reach_a_model() -> None:
    assert rules.redact_phones("call 98400 12345 or +91 9123456780") == "call [PHONE_1] or [PHONE_2]"


# --- geocoding -----------------------------------------------------------------------------


def test_spellings_share_one_key() -> None:
    keys = {textnorm.key(s) for s in ("Velachery", "Velacheri", "வேளச்சேரி", "वेलाचेरी", "వేళచేరి")}
    assert len(keys) == 1
    assert textnorm.key("Pillaiyar Kovil") == textnorm.key("Vinayagar Temple")


def test_geocodes_landmark_near_locality_confidently() -> None:
    g = gazetteer(str(get_settings().data_dir))
    r = g.geocode("stuck near Kotturpuram Tree Park, Kotturpuram")
    assert r is not None and r.confidence >= 0.8
    assert r.locality == "Kotturpuram"


def test_vague_location_goes_to_review() -> None:
    g = gazetteer(str(get_settings().data_dir))
    r = g.geocode("help us in Mudichur")
    assert r is not None and r.confidence < get_settings().location_review_threshold
    assert g.geocode("please help near murugan temple") is None


# --- triage --------------------------------------------------------------------------------


def _score(**kw: object) -> triage.TriageResult:
    base = {
        "people_count": 2,
        "vulnerability": {},
        "water_level": "knee",
        "water_rising": False,
        "needs": ["rescue"],
        "first_reported_at": NOW,
    }
    return triage.score(triage.TriageInput(**{**base, **kw}), NOW)  # type: ignore[arg-type]


def test_life_threat_outranks_supplies_and_is_explained() -> None:
    critical = _score(water_level="neck", water_rising=True, vulnerability={"elderly": 2, "medical": ["dialysis"]})
    supplies = _score(needs=["food"], water_level="unknown", people_count=40)
    assert critical.level == "critical"
    assert supplies.score <= 40
    assert sum(f.points for f in critical.breakdown) == critical.score
    assert any(f.key == "medical" and "dialysis" in f.detail for f in critical.breakdown)


def test_water_clock_raises_urgency_and_never_lowers_it() -> None:
    plain = _score()
    soon = _score(minutes_to_danger=25, danger_label="Too deep to stand in")
    later = _score(minutes_to_danger=150, danger_label="Too deep to stand in")
    beyond = _score(minutes_to_danger=None)
    assert soon.score > later.score > plain.score == beyond.score
    clock = next(f for f in soon.breakdown if f.key == "water_clock")
    assert "25 min" in clock.label


def test_waiting_raises_urgency() -> None:
    fresh = _score()
    stale = triage.score(triage.TriageInput(2, {}, "knee", False, ["rescue"], NOW - timedelta(hours=3)), NOW)
    assert stale.score > fresh.score


# --- de-duplication ------------------------------------------------------------------------


def _sig(**kw: object) -> dedup.Signals:
    base = {"lat": 12.98, "lng": 80.22, "location_confidence": 0.85, "phone_hashes": set(), "reported_at": NOW}
    return dedup.Signals(**{**base, **kw})  # type: ignore[arg-type]


def test_same_contact_number_merges() -> None:
    v = dedup.compare(_sig(phone_hashes={"a"}, lng=80.225), _sig(phone_hashes={"a"}))
    assert v.decision == "merge"


def test_two_families_behind_one_temple_stay_apart() -> None:
    a = _sig(phone_hashes={"a"}, address="No. 12, 3rd Street", anchors={"Ganesh Temple|temple"})
    b = _sig(phone_hashes={"b"}, address="No. 40, 3rd Street", anchors={"Ganesh Temple|temple"})
    assert dedup.compare(a, b).decision == "separate"


def test_reports_far_apart_in_time_never_merge() -> None:
    old = _sig(reported_at=NOW - timedelta(hours=20))
    assert dedup.compare(_sig(), old).decision == "separate"


# --- dispatch ------------------------------------------------------------------------------


def test_trucks_never_sent_into_deep_water_and_critical_goes_first() -> None:
    teams = [
        dispatch.DTeam("truck", "T-1", "truck", 10, 12.98, 80.22),
        dispatch.DTeam("boat", "B-1", "boat", 6, 12.99, 80.23),
    ]
    cases = [
        dispatch.DCase("deep", 12.985, 80.225, 3, 85, "critical", 1.6, True),
        dispatch.DCase("dry", 12.975, 80.215, 2, 30, "low", 0.2, False),
    ]
    plan = dispatch.plan(teams, cases, time_limit_s=0.5)
    by_case = {s.case_id: s for s in plan.stops}
    assert by_case["deep"].team_id == "boat"
    assert by_case["dry"].team_id == "truck"
    assert by_case["deep"].reasons


def test_the_boat_goes_first_where_the_water_arrives_first() -> None:
    teams = [dispatch.DTeam("boat", "B-1", "boat", 6, 12.98, 80.22)]
    near = dispatch.DCase("near", 12.983, 80.222, 3, 60, "high", 1.0, True)
    # a little farther, same urgency today, but the water reaches this family's line in 20 minutes;
    # visiting the near family first would get there at about 30
    racing = dispatch.DCase("racing", 12.99, 80.229, 3, 60, "high", 1.0, True, deadline_s=20 * 60)
    plan = dispatch.plan(teams, [near, racing], time_limit_s=0.5)
    order = [s.case_id for s in sorted(plan.stops, key=lambda s: s.sequence)]
    assert order[0] == "racing"
    first = next(s for s in plan.stops if s.case_id == "racing")
    assert any("water" in r.lower() for r in first.reasons)
    assert first.margin_s is not None and first.margin_s > 0


def test_trucks_are_judged_on_the_water_when_they_arrive() -> None:
    teams = [
        dispatch.DTeam("truck", "T-1", "truck", 10, 12.98, 80.22),
        dispatch.DTeam("boat", "B-1", "boat", 6, 12.90, 80.15),
    ]
    # knee-deep now, but the forecast puts it at 1.2 m within ten minutes; the truck needs about nine
    rising = dispatch.DCase(
        "rising", 12.99, 80.23, 3, 55, "high", 0.5, True, depth_profile=((0, 0.5), (600, 1.2), (3600, 1.4))
    )
    plan = dispatch.plan(teams, [rising], time_limit_s=0.5)
    assert [s.team_id for s in plan.stops] == ["boat"]


def test_dispatch_scales_to_the_trd_target() -> None:
    import random
    import time

    rng = random.Random(1)
    teams = [
        dispatch.DTeam(
            f"t{i}", f"X{i}", rng.choice(["boat", "truck"]), 6, 12.95 + rng.random() / 8, 80.15 + rng.random() / 8
        )
        for i in range(50)
    ]
    cases = [
        dispatch.DCase(
            f"c{i}",
            12.95 + rng.random() / 8,
            80.15 + rng.random() / 8,
            rng.randint(1, 8),
            rng.randint(10, 95),
            rng.choice(["critical", "high", "medium", "low"]),
            rng.choice([None, 0.4, 1.2]),
            rng.random() < 0.5,
        )
        for i in range(500)
    ]
    started = time.perf_counter()
    plan = dispatch.plan(teams, cases, time_limit_s=3.0)
    assert time.perf_counter() - started < 5.0
    assert plan.status == "ok" and plan.stops


# --- personal data ---------------------------------------------------------------------------


def test_encryption_round_trips_and_hash_is_stable() -> None:
    token = crypto.encrypt("+919840012345")
    assert token and "9840012345" not in token
    assert crypto.decrypt(token) == "+919840012345"
    assert crypto.phone_hash("98400 12345") == crypto.phone_hash("+91-98400-12345")
    assert crypto.mask_phone("+919840012345") == "+91•••••345"


def test_haversine_sanity() -> None:
    assert abs(float(haversine_m(13.0, 80.0, 13.0, 80.01)) - 1084) < 5


def test_hosted_postgres_urls_work_with_asyncpg() -> None:
    url = "postgresql://u:p@ep-x.neon.tech/rescuegrid?sslmode=require&channel_binding=require"
    assert Settings(database_url=url).database_url == "postgresql+asyncpg://u:p@ep-x.neon.tech/rescuegrid?ssl=require"
