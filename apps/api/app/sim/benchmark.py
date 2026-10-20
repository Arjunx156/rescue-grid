"""Rescue Grid against first-come-first-served, on the same replay, teams and ground truth.

A discrete-event simulation. Every policy sees the same messages at the same
times and commands the same fleet moving at the same flood-aware speeds, through
the same simulated flood (app.sim.flood): a truck that arrives where the water
has risen past its axles turns back. A rescue counts only when a team reaches
the right household while people are still there, and the headline asks the
question that matters: did a team get there before the water reached the
family's danger line? The differences under test are the ones the PRD claims:

- Rescue Grid de-duplicates, scores urgency and plans multi-stop routes with
  OR-Tools; a coordinator works its review inbox (fixing pins by phone, closing
  families reported safe) and approves each plan after a short delay.
- With the water clock, Rescue Grid also runs the flood ensemble, feeds it
  every located report as a gauge reading, and plans against the forecast: a
  deadline where the water will reach a family's line, and reach judged on the
  depth when a team arrives. Without it (the ablation), the same pipeline ranks
  on reported water alone.
- The baseline answers messages in arrival order, each with the nearest free
  team that can reach it, chasing duplicates and stale reports as they come.

    uv run python -m app.sim.benchmark [--dataset chennai-2015]
"""

from __future__ import annotations

import argparse
import heapq
import itertools
import json
import statistics
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.agents import rules
from app.core.settings import get_settings
from app.schemas.extraction import Understanding
from app.services import dispatch, travel, triage, waterclock
from app.services.floods import FloodMap
from app.services.geocode import gazetteer, haversine_m
from app.services.hydro import Forcing, Grid
from app.services.merge import LocationFix
from app.services.resolver import REVIEW_THRESHOLD, Resolver, SimCase

STEP = timedelta(minutes=1)
TAIL = timedelta(hours=12)  # keep working after the last message arrives
REVIEW_EVERY = timedelta(seconds=90)  # one coordinator, one inbox item every 90 s
APPROVE_AFTER = timedelta(minutes=1)
PLAN_EVERY = timedelta(minutes=3)
CALLBACK_DELAY = timedelta(minutes=20)  # baseline volunteers phone back to find vague addresses
UNLOAD = timedelta(minutes=10)
GIVE_UP_M = 2500.0
NOWCAST_EVERY = timedelta(minutes=30)
ROAD = ("truck", "medical", "foot")
POLICIES = ("rescue_grid", "rescue_grid_static", "fcfs")
LABELS = {
    "rescue_grid": "Rescue Grid",
    "rescue_grid_static": "Rescue Grid without the water clock",
    "fcfs": "First come, first served",
}


@dataclass
class House:
    id: str
    lat: float
    lng: float
    people: int
    score: int
    critical: bool
    first_t: datetime
    self_rescued_t: datetime | None
    rescued_t: datetime | None = None
    rescued_by: str | None = None
    assigned_t: datetime | None = None
    danger_t: datetime | None = None  # when the water truly reached this family's danger line


@dataclass
class Target:
    key: str  # case id or message id
    lat: float
    lng: float
    house: str | None  # who is really there, if anyone
    people: int


@dataclass
class Crew:
    id: str
    call_sign: str
    asset: str
    capacity: int
    lat: float
    lng: float
    base: tuple[float, float]
    free_at: datetime
    tracks: list[list[Any]] = field(default_factory=list)


def _secs(asset: str, a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(travel.travel_seconds(asset, float(haversine_m(a[0], a[1], b[0], b[1]))))


class Water:
    """The simulated flood the households live in: depth anywhere, any time."""

    def __init__(self, grid: Grid, base: Path, start: datetime):
        w = np.load(base / "water.npz")
        self.grid, self.start = grid, start
        self.frames, self.step_m, self.every_min = w["frames"], float(w["step_m"]), float(w["every_min"])

    def depth(self, lat: float, lng: float, t: datetime) -> float:
        cell = self.grid.cell(lat, lng)
        if cell is None:
            return 0.0
        k = min(max(0.0, (t - self.start).total_seconds() / 60 / self.every_min), self.frames.shape[0] - 1.0)
        lo = int(k)
        hi = min(lo + 1, self.frames.shape[0] - 1)
        a, b = float(self.frames[lo][cell]), float(self.frames[hi][cell])
        return (a + (b - a) * (k - lo)) * self.step_m


class World:
    """Shared physics: crews move, arrive, find people or nobody, and go home to unload."""

    def __init__(self, crews: list[Crew], houses: dict[str, House], flood: FloodMap, water: Water):
        self.crews = {c.id: c for c in crews}
        self.houses = houses
        self.flood = flood
        self.water = water
        self.events: list[dict[str, Any]] = []
        self.queue: list[tuple[datetime, int, str, int, list[Target]]] = []
        self._seq = itertools.count()
        self.wasted = 0
        self.wasted_by: Counter[str] = Counter()

    def idle(self, now: datetime) -> list[Crew]:
        return [c for c in self.crews.values() if c.free_at <= now]

    def send(self, crew: Crew, targets: list[Target], now: datetime) -> None:
        pos, t = (crew.lat, crew.lng), now
        for i, tg in enumerate(targets):
            dest = (tg.lat, tg.lng)
            dt = timedelta(seconds=_secs(crew.asset, pos, dest))
            crew.tracks.append([_iso(t), _iso(t + dt), *_r(pos), *_r(dest), "travel"])
            t += dt
            heapq.heappush(self.queue, (t, next(self._seq), crew.id, i, targets))
            t += timedelta(seconds=travel.service_seconds(crew.asset, tg.people))
            pos = dest
            if tg.house and (h := self.houses.get(tg.house)) and h.assigned_t is None:
                h.assigned_t = now
            self.events.append({"t": _iso(now), "kind": "assign", "team": crew.id, "house": tg.house})
        back = timedelta(seconds=_secs(crew.asset, pos, crew.base))
        crew.tracks.append([_iso(t), _iso(t + back), *_r(pos), *_r(crew.base), "return"])
        crew.free_at = t + back + UNLOAD
        crew.lat, crew.lng = crew.base

    def arrivals(self, now: datetime) -> list[tuple[Crew, Target, bool]]:
        """Process arrivals due by now, in time order: (crew, target, people found)."""
        out = []
        while self.queue and self.queue[0][0] <= now:
            at, _, crew_id, i, targets = heapq.heappop(self.queue)
            crew, tg = self.crews[crew_id], targets[i]
            h = self.houses.get(tg.house) if tg.house else None
            found, why = False, "nobody there"
            if crew.asset in ROAD and self.water.depth(tg.lat, tg.lng, at) > travel.MAX_DEPTH_M[crew.asset]:
                why = "too deep to reach"  # the water rose while they drove
            elif h is not None:
                err = float(haversine_m(tg.lat, tg.lng, h.lat, h.lng))
                search = timedelta(minutes=min(45.0, err / 80))  # a wrong pin costs a search
                if h.rescued_t is not None and h.rescued_t <= at:
                    why = "already rescued"
                elif h.self_rescued_t is not None and h.self_rescued_t <= at:
                    why = "left on their own"
                elif err > GIVE_UP_M:
                    why = "wrong location"
                else:
                    h.rescued_t, h.rescued_by = at + search, crew.id
                    found = True
            if not found:
                self.wasted += 1
                self.wasted_by[why] += 1
            self.events.append(
                {
                    "t": _iso(at),
                    "kind": "rescue" if found else "wasted",
                    "team": crew.id,
                    "house": tg.house,
                    **({} if found else {"why": why}),
                }
            )
            out.append((crew, tg, found))
        return out


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _r(p: tuple[float, float]) -> list[float]:
    return [round(p[0], 5), round(p[1], 5)]


def _metrics(houses: dict[str, House], world: World, start: datetime) -> dict[str, Any]:
    hs = list(houses.values())
    crit = [h for h in hs if h.critical]

    def within(h: House, hours: float) -> bool:
        return h.rescued_t is not None and h.rescued_t - h.first_t <= timedelta(hours=hours)

    assigned = [(h.assigned_t - h.first_t).total_seconds() / 60 for h in hs if h.assigned_t]
    rescued = [(h.rescued_t - h.first_t).total_seconds() / 60 for h in hs if h.rescued_t]
    crit_assigned = [(h.assigned_t - h.first_t).total_seconds() / 60 for h in crit if h.assigned_t]
    at_risk = [h for h in hs if h.danger_t]
    before = [h for h in at_risk if h.rescued_t and h.danger_t and h.rescued_t <= h.danger_t]
    hourly = []
    end = max((h.rescued_t for h in hs if h.rescued_t), default=start)
    t = start
    while t <= end + timedelta(hours=1):
        hourly.append(
            {
                "t": _iso(t),
                "critical_reached": sum(1 for h in crit if h.rescued_t and h.rescued_t <= t),
                "people": sum(h.people for h in hs if h.rescued_t and h.rescued_t <= t),
            }
        )
        t += timedelta(hours=1)
    return {
        "households": len(hs),
        "at_risk": len(at_risk),
        "reached_before_water": len(before),
        "water_first": len(at_risk) - len(before),
        "people_before_water": sum(h.people for h in before),
        "critical_total": len(crit),
        "critical_reached_3h": sum(within(h, 3) for h in crit),
        "critical_reached_3h_pct": round(sum(within(h, 3) for h in crit) / max(1, len(crit)), 3),
        "households_reached": sum(1 for h in hs if h.rescued_t),
        "households_reached_6h": sum(within(h, 6) for h in hs),
        "people_rescued": sum(h.people for h in hs if h.rescued_t and h.rescued_by),
        "median_minutes_to_assign": round(statistics.median(assigned), 1) if assigned else None,
        "median_minutes_to_assign_critical": round(statistics.median(crit_assigned), 1) if crit_assigned else None,
        "median_minutes_to_rescue": round(statistics.median(rescued), 1) if rescued else None,
        "wasted_trips": world.wasted,
        "wasted_by": dict(world.wasted_by),
        "hourly": hourly,
    }


def _understand(text: str) -> Understanding:
    e, phones = rules.extract(text)
    return Understanding(extraction=e, phones=phones, provider="local", model="rules-v1")


def _house_of(case: SimCase, truth: dict[str, dict[str, Any]]) -> str | None:
    votes = Counter(truth[m]["household"] for m in case.message_ids if truth[m].get("household"))
    return votes.most_common(1)[0][0] if votes else None


def run_rescue_grid(
    msgs: list[dict[str, Any]],
    crews: list[Crew],
    houses: dict[str, House],
    flood: FloodMap,
    water: Water,
    start: datetime,
    end: datetime,
    data_dir: str,
    nowcast: waterclock.Nowcast | None,
) -> tuple[World, dict[str, Any]]:
    world = World(crews, houses, flood, water)
    res = Resolver(gazetteer(data_dir), flood, (13.0, 80.2))
    next_nowcast, cycles = start, 0

    def minute(t: datetime) -> float:
        return (t - start).total_seconds() / 60

    truth = {m["id"]: m["truth"] for m in msgs}
    reviewed_at = start
    next_plan = start
    pending: list[tuple[datetime, list[tuple[str, list[str]]]]] = []  # approval queue
    in_flight: set[str] = set()
    dirty = False
    it = iter(msgs)
    nxt = next(it, None)
    now = start
    while now <= end:
        while nxt and datetime.fromisoformat(nxt["t"]) <= now:
            u = _understand(nxt["text"])
            at = datetime.fromisoformat(nxt["t"])
            out = res.ingest(
                nxt["id"], u, nxt["text"], tuple(nxt["pin"]) if nxt["pin"] else None, nxt["sender_phone"], at
            )
            loc = out.location
            if nowcast and loc and loc.confidence >= REVIEW_THRESHOLD:
                nowcast.report(waterclock.observation(loc.lat, loc.lng, u.extraction.water_level, minute(at)))
            dirty = True
            nxt = next(it, None)

        if nowcast and now >= next_nowcast and res.open_cases():
            nowcast.cycle(minute(now))
            cycles += 1
            next_nowcast = now + NOWCAST_EVERY
            dirty = True

        # the coordinator works the review inbox, most urgent first
        while reviewed_at + REVIEW_EVERY <= now:
            reviewed_at += REVIEW_EVERY
            inbox = [c for c in res.cases if c.status == "open" and c.review]
            if not inbox:
                break
            c = max(inbox, key=lambda x: x.score)
            house = _house_of(c, truth)
            h = houses.get(house) if house else None
            if "reported_rescued" in c.review:
                # an update with no family behind it ("ignore, they are safe") is closed on reading
                if h is None or (h.self_rescued_t and h.self_rescued_t <= now):
                    c.status = "closed"
                c.review.remove("reported_rescued")
            if "possibly_rescued" in c.review:
                if h and h.rescued_t and h.rescued_t <= now:
                    c.status = "closed"  # the coordinator checks with the crew: same family
                c.review.remove("possibly_rescued")
            if {"location_unknown", "low_confidence_location"} & set(c.review):
                if h is not None:  # a phone call pins the family
                    c.location = LocationFix(h.lat, h.lng, 1.0, "manual")
                    c.in_flood_zone, c.flood_depth_m = flood.depth_at(h.lat, h.lng)
                c.review = [r for r in c.review if r not in ("location_unknown", "low_confidence_location")]
            if "possible_duplicate" in c.review:
                c.review.remove("possible_duplicate")
                for a, b, _ in res.review_pairs:
                    if c.id in (a, b):
                        other = next((x for x in res.cases if x.id == (b if a == c.id else a)), None)
                        if other and other.status == "open" and _house_of(other, truth) == house:
                            other.status = "duplicate"
                            c.message_ids += other.message_ids
            c.review = [r for r in c.review if r not in ("manual_reading", "instructions_in_message")]
            dirty = True

        # arrivals: rescued cases close; a house already gone closes every case pointing at it
        for _crew, tg, found in world.arrivals(now):
            case = next((x for x in res.cases if x.id == tg.key), None)
            if case:
                case.status = "rescued"
                if found:
                    res.rescued_nearby(case)
            in_flight.discard(tg.key)
            dirty = True

        # approved plans go out
        while pending and pending[0][0] <= now:
            _, approved = pending.pop(0)
            for crew_id, case_ids in approved:
                crew = world.crews[crew_id]
                if crew.free_at > now:
                    continue
                targets = []
                for cid in case_ids:
                    c = next((x for x in res.cases if x.id == cid), None)
                    if c and c.status == "open" and c.location and cid not in in_flight:
                        targets.append(Target(cid, c.location.lat, c.location.lng, _house_of(c, truth), c.people or 2))
                        in_flight.add(cid)
                if targets:
                    world.send(crew, targets, now)

        if now >= next_plan and dirty and not pending:
            idle = world.idle(now)
            ready = [
                c
                for c in res.cases
                if c.status == "open"
                and c.location
                and c.id not in in_flight
                and c.location.confidence >= REVIEW_THRESHOLD
                and not {"reported_rescued", "possibly_rescued", "location_unknown", "low_confidence_location"}
                & set(c.review)
                and set(c.needs or ["rescue"]) & {"rescue", "evacuation", "boat", "medical"}
            ]
            if idle and ready:
                profiles: dict[str, tuple[tuple[int, float], ...]] = {}
                for c in ready:
                    loc = c.location
                    assert loc is not None
                    if nowcast:
                        clock = nowcast.clock(minute(now), loc.lat, loc.lng, c.water, c.vulnerability)
                        c.minutes_to_danger = clock.minutes if clock else None
                        c.danger_label = clock.danger_label if clock else None
                        profiles[c.id] = nowcast.profile(minute(now), loc.lat, loc.lng)
                    c.rescore(now)
                dcases = []
                for c in ready:
                    loc = c.location
                    assert loc is not None
                    depth = travel.effective_depth(c.water, c.flood_depth_m)
                    deadline = round(c.minutes_to_danger * 60) if c.minutes_to_danger is not None else None
                    dcases.append(
                        dispatch.DCase(
                            c.id,
                            loc.lat,
                            loc.lng,
                            c.people,
                            c.score,
                            c.level,
                            depth,
                            c.in_flood_zone,
                            deadline_s=deadline,
                            depth_profile=profiles.get(c.id, ()),
                        )
                    )
                dteams = [dispatch.DTeam(cr.id, cr.call_sign, cr.asset, cr.capacity, cr.lat, cr.lng) for cr in idle]
                plan = dispatch.plan(dteams, dcases, time_limit_s=0.15)
                routes: dict[str, list[str]] = {}
                for s in sorted(plan.stops, key=lambda s: (s.team_id, s.sequence)):
                    routes.setdefault(s.team_id, []).append(s.case_id)
                if routes:
                    pending.append((now + APPROVE_AFTER, list(routes.items())))
            dirty = False
            next_plan = now + PLAN_EVERY
        now += STEP
    extra: dict[str, Any] = {"cases": len([c for c in res.cases if c.status != "duplicate"])}
    if nowcast:
        extra["nowcast"] = {"cycles": cycles, "reports_used": nowcast.reports_used}
    return world, extra


def run_fcfs(
    msgs: list[dict[str, Any]],
    crews: list[Crew],
    houses: dict[str, House],
    flood: FloodMap,
    water: Water,
    start: datetime,
    end: datetime,
    data_dir: str,
) -> World:
    world = World(crews, houses, flood, water)
    gaz = gazetteer(data_dir)
    requests: list[tuple[datetime, Target, float | None, bool]] = []
    for m in msgs:
        if m["truth"]["kind"] != "sos":
            continue  # a dispatcher reading "safe now" or "food needed" would not send a boat either
        t = datetime.fromisoformat(m["t"])
        u = _understand(m["text"])
        if m["pin"]:
            lat, lng = m["pin"]
        else:
            r = gaz.geocode(m["text"], bias=(13.0, 80.2))
            if r is None:
                # no usable address: a volunteer calls back and gets it right, eventually
                t += CALLBACK_DELAY
                lat, lng = m["truth"]["lat"], m["truth"]["lng"]
            else:
                lat, lng = r.lat, r.lng
        in_zone, depth = flood.depth_at(lat, lng)
        requests.append(
            (
                t,
                Target(m["id"], lat, lng, m["truth"]["household"], u.extraction.people_count or 2),
                travel.effective_depth(u.extraction.water_level, depth),
                in_zone,
            )
        )
    requests.sort(key=lambda r: r[0])
    served = 0
    now = start
    while now <= end:
        world.arrivals(now)
        idle = world.idle(now)
        while idle and served < len(requests) and requests[served][0] <= now:
            _, tg, depth, in_zone = requests[served]
            able = [c for c in idle if travel.can_reach(c.asset, depth, in_zone).ok]
            if able:
                crew = min(able, key=lambda c: _secs(c.asset, (c.lat, c.lng), (tg.lat, tg.lng)))
                world.send(crew, [tg], now)
                idle.remove(crew)
                served += 1
            elif not any(travel.can_reach(c.asset, depth, in_zone).ok for c in world.crews.values()):
                served += 1  # nobody in the fleet could ever reach it
            else:
                break  # first come, first served: wait for a capable team
        now += STEP
    return world


def _load(dataset: str) -> dict[str, Any]:
    settings = get_settings()
    base = settings.data_dir / "replay" / dataset
    meta = json.loads((base / "dataset.json").read_text(encoding="utf-8"))
    msgs = [json.loads(x) for x in (base / "messages.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    msgs.sort(key=lambda m: m["t"])
    start = datetime.fromisoformat(meta["starts_at"])
    return {
        "base": base,
        "meta": meta,
        "msgs": msgs,
        "flood": FloodMap.load(base / "flood_zones.geojson"),
        "start": start,
        "end": datetime.fromisoformat(meta["ends_at"]) + TAIL,
    }


def _houses(meta: dict[str, Any], flood: FloodMap) -> dict[str, House]:
    out = {}
    for h in meta["households"]:
        t0 = datetime.fromisoformat(h["first_report"])
        in_zone, depth = flood.depth_at(h["lat"], h["lng"])
        vul = {k: h[k] for k in ("elderly", "child", "infant", "pregnant", "disabled")} | {"medical": h["medical"]}
        r = triage.score(
            triage.TriageInput(h["people"], vul, h["water"], h["rising"], ["rescue"], t0, 1, depth, in_zone), t0
        )
        out[h["id"]] = House(
            h["id"],
            h["lat"],
            h["lng"],
            h["people"],
            r.score,
            r.level == "critical",
            t0,
            datetime.fromisoformat(h["self_rescued_at"]) if h.get("self_rescued_at") else None,
            danger_t=datetime.fromisoformat(h["danger_at"]) if h.get("danger_at") else None,
        )
    return out


def _crews(meta: dict[str, Any], start: datetime) -> list[Crew]:
    return [
        Crew(f"t{i}", t["call_sign"], t["asset_type"], t["capacity"], t["lat"], t["lng"], (t["lat"], t["lng"]), start)
        for i, t in enumerate(meta["teams"])
    ]


def simulate(policy: str, dataset: str) -> dict[str, Any]:
    """One policy on the replay, start to finish. Runs in its own process."""
    started = time.perf_counter()
    d = _load(dataset)
    data_dir = get_settings().data_dir
    grid = Grid.load(data_dir / "geo" / "terrain.npz")
    water = Water(grid, d["base"], d["start"])
    houses, crews = _houses(d["meta"], d["flood"]), _crews(d["meta"], d["start"])
    extra: dict[str, Any] = {}
    if policy == "fcfs":
        world = run_fcfs(d["msgs"], crews, houses, d["flood"], water, d["start"], d["end"], str(data_dir))
    else:
        nowcast = None
        if policy == "rescue_grid":
            f = json.loads((d["base"] / "forcing.json").read_text(encoding="utf-8"))
            nowcast = waterclock.Nowcast(
                grid, Forcing.from_dict(f["forecast"]), f["spinup_min"], sea_level_m=f["sea_level_m"]
            )
        world, extra = run_rescue_grid(
            d["msgs"], crews, houses, d["flood"], water, d["start"], d["end"], str(data_dir), nowcast
        )
    return {
        "label": LABELS[policy],
        "metrics": _metrics(houses, world, d["start"]) | extra,
        "events": world.events,
        "tracks": {c.id: c.tracks for c in world.crews.values()},
        "outcomes": {h.id: _iso(h.rescued_t) for h in houses.values() if h.rescued_t},
        "runtime_ms": int((time.perf_counter() - started) * 1000),
    }


def build(dataset: str = "chennai-2015") -> dict[str, Any]:
    started = time.perf_counter()
    d = _load(dataset)
    with ProcessPoolExecutor(max_workers=len(POLICIES)) as pool:
        runs = dict(zip(POLICIES, pool.map(simulate, POLICIES, [dataset] * len(POLICIES)), strict=True))
    rg, static, fc = (runs[p]["metrics"] for p in POLICIES)
    houses = _houses(d["meta"], d["flood"])
    base_crit = fc["critical_reached_3h"] or 1
    return {
        "dataset": dataset,
        "name": d["meta"]["name"],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "starts_at": d["meta"]["starts_at"],
        "ends_at": _iso(d["end"]),
        "assumptions": {
            "coordinator_review_seconds": REVIEW_EVERY.total_seconds(),
            "approval_delay_minutes": APPROVE_AFTER.total_seconds() / 60,
            "replan_minutes": PLAN_EVERY.total_seconds() / 60,
            "nowcast_minutes": NOWCAST_EVERY.total_seconds() / 60,
            "baseline_callback_minutes": CALLBACK_DELAY.total_seconds() / 60,
            "unload_minutes": UNLOAD.total_seconds() / 60,
            "critical_means": "triage score of the true household at first report >= 70",
            "at_risk_means": "the simulated water reached the family's danger line after their first report",
        },
        "teams": [
            {
                "id": c.id,
                "call_sign": c.call_sign,
                "asset_type": c.asset,
                "capacity": c.capacity,
                "lat": c.lat,
                "lng": c.lng,
            }
            for c in _crews(d["meta"], d["start"])
        ],
        "households": [
            {
                "id": h.id,
                "lat": round(h.lat, 5),
                "lng": round(h.lng, 5),
                "people": h.people,
                "score": h.score,
                "critical": h.critical,
                "first_t": _iso(h.first_t),
                "danger_t": _iso(h.danger_t) if h.danger_t else None,
            }
            for h in houses.values()
        ],
        "comparison": {
            "critical_reached_3h_gain_pct": round(
                100 * (rg["critical_reached_3h"] - fc["critical_reached_3h"]) / base_crit, 1
            ),
            "wasted_trips_avoided": fc["wasted_trips"] - rg["wasted_trips"],
            "reached_before_water": {p: runs[p]["metrics"]["reached_before_water"] for p in POLICIES},
            "water_clock_gain": rg["reached_before_water"] - static["reached_before_water"],
        },
        "policies": runs,
        "runtime_ms": {p: runs[p]["runtime_ms"] for p in POLICIES}
        | {"total": int((time.perf_counter() - started) * 1000)},
    }


def output_path(dataset: str) -> Path:
    return get_settings().data_dir / "replay" / dataset / "benchmark.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="chennai-2015")
    args = parser.parse_args()
    report = build(args.dataset)
    output_path(args.dataset).write_text(json.dumps(report, separators=(",", ":")), encoding="utf-8")
    metrics = [report["policies"][p]["metrics"] for p in POLICIES]
    rows = [
        ("families the water reached", "at_risk"),
        ("  reached before the water did", "reached_before_water"),
        ("critical households", "critical_total"),
        ("critical reached within 3 h", "critical_reached_3h"),
        ("households reached", "households_reached"),
        ("people rescued", "people_rescued"),
        ("median min to assignment", "median_minutes_to_assign"),
        ("median min to assign (critical)", "median_minutes_to_assign_critical"),
        ("median min to rescue", "median_minutes_to_rescue"),
        ("wasted trips", "wasted_trips"),
    ]
    print(f"{'':34}{'Rescue Grid':>14}{'no clock':>10}{'FCFS':>10}")
    for label, key in rows:
        print(f"{label:34}" + "".join(f"{m[key]!s:>{w}}" for m, w in zip(metrics, (14, 10, 10), strict=True)))
    print("\nwasted trips by reason")
    for p, m in zip(POLICIES, metrics, strict=True):
        print(f"  {p:20}{m['wasted_by']}")
    c = report["comparison"]
    print(
        f"\ncritical reached within 3 h: {c['critical_reached_3h_gain_pct']:+.1f}% vs baseline; "
        f"water clock: {c['water_clock_gain']:+d} families reached before the water   "
        f"({report['runtime_ms']['total'] / 1000:.1f}s)"
    )


if __name__ == "__main__":
    main()
