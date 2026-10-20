"""Who goes where: a prize-collecting vehicle routing problem solved with OR-Tools.

Teams are vehicles (capacity, start, earliest availability); cases are optional
stops. Dropping a case costs a penalty that grows with urgency and headcount,
and every case pays for each second it waits, weighted by its urgency level. So
the solver reaches the most people in the most danger first, then minimises
driving. Assets that cannot reach a case (a truck in 1.5 m of water) are
forbidden from it outright.

With a water clock, two things change. A case whose water reaches its danger
line within the horizon gets a deadline, and every second past it costs far more
than waiting does. And reach is judged on the water forecast for the moment a
team would arrive, not the water reported an hour ago.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.services import travel
from app.services.geocode import haversine_m

HORIZON_S = 8 * 3600
UNKNOWN_PEOPLE = 2
# cost per second of waiting, by urgency level
LATENESS_COEF = {"critical": 40, "high": 12, "medium": 3, "low": 1}
DROP_BASE = 2_500_000
DEADLINE_COEF = 200  # cost per second a team arrives after the water reached the danger line


@dataclass
class DTeam:
    id: str
    call_sign: str
    asset_type: str
    capacity: int
    lat: float
    lng: float
    available_in_s: int = 0


@dataclass
class DCase:
    id: str
    lat: float
    lng: float
    people: int | None
    urgency: int
    level: str
    depth_m: float | None
    in_flood_zone: bool
    summary: str = ""
    deadline_s: int | None = None  # seconds until the water reaches the danger line
    depth_profile: tuple[tuple[int, float], ...] = ()  # (seconds from now, forecast depth m)

    def depth_after(self, seconds: float) -> float | None:
        """The deeper of the reported depth and the forecast for that moment."""
        if not self.depth_profile:
            return self.depth_m
        ts, ds = zip(*self.depth_profile, strict=True)
        return max(float(np.interp(seconds, ts, ds)), self.depth_m or 0.0)


@dataclass
class Stop:
    case_id: str
    team_id: str
    sequence: int
    distance_m: int
    travel_s: int
    arrival_s: int
    reasons: list[str] = field(default_factory=list)
    margin_s: int | None = None  # deadline minus arrival; negative means the water got there first


@dataclass
class Plan:
    status: str  # ok | empty | no_teams | no_solution
    stops: list[Stop] = field(default_factory=list)
    dropped: dict[str, str] = field(default_factory=dict)  # case id -> why
    objective: float = 0.0
    solver_ms: int = 0
    people_covered: int = 0
    critical_covered: int = 0


def _drop_penalty(c: DCase) -> int:
    people = c.people or UNKNOWN_PEOPLE
    base = DROP_BASE * (max(c.urgency, 5) / 100) ** 2 * (1 + min(people, 20) / 10)
    # late is still better than never: dropping must not become a way to dodge the deadline cost
    return int(base + (DEADLINE_COEF * 3600 if c.deadline_s is not None else 0))


def _arrival_s(t: DTeam, c: DCase) -> float:
    """Straight to the case: the earliest a team could be there, before any routing."""
    meters = float(haversine_m(t.lat, t.lng, c.lat, c.lng))
    return t.available_in_s + float(travel.travel_seconds(t.asset_type, meters))


def _reach(t: DTeam, c: DCase) -> travel.Reach:
    return travel.can_reach(t.asset_type, c.depth_after(_arrival_s(t, c)), c.in_flood_zone)


def plan(
    teams: list[DTeam],
    cases: list[DCase],
    time_limit_s: float = 3.0,
    initial_routes: dict[str, list[str]] | None = None,
) -> Plan:
    started = time.perf_counter()
    if not cases:
        return Plan("empty")
    if not teams:
        return Plan("no_teams", dropped={c.id: "No teams on duty" for c in cases})

    # who can reach what; unreachable cases never enter the model
    dropped: dict[str, str] = {}
    reachable: list[tuple[DCase, list[int]]] = []
    for c in cases:
        ok = [v for v, t in enumerate(teams) if _reach(t, c).ok]
        if ok:
            reachable.append((c, ok))
        else:
            deepest = max((c.depth_after(_arrival_s(t, c)) or 0.0) for t in teams)
            need = "a boat or helicopter" if deepest > 0.9 else "a road team"
            dropped[c.id] = f"No team on duty can reach it (needs {need})"
    if not reachable:
        return Plan("no_solution", dropped=dropped, solver_ms=_ms(started))
    # one plan is one trip per team, so only the most urgent cases that could fill the fleet
    # about twice over are worth the solver's time; the rest wait for the next rolling re-plan
    reachable.sort(key=lambda r: (r[0].urgency, r[0].people or 0), reverse=True)
    seats = sum(t.capacity for t in teams) * 2
    shortlist, people = [], 0
    for c, ok in reachable:
        if people >= seats and len(shortlist) >= max(60, 3 * len(teams)):
            break
        shortlist.append((c, ok))
        people += c.people or UNKNOWN_PEOPLE
    reachable = shortlist
    all_cases, cases = cases, [c for c, _ in reachable]
    allowed = {j: ok for j, (_, ok) in enumerate(reachable)}

    nt, nc = len(teams), len(cases)
    end = nt + nc  # one shared dummy end node: routes are open, teams stay where they finish
    lat = np.array([t.lat for t in teams] + [c.lat for c in cases])
    lng = np.array([t.lng for t in teams] + [c.lng for c in cases])
    dist = travel.distance_matrix_m(lat, lng)

    manager = pywrapcp.RoutingIndexManager(nc + nt + 1, nt, list(range(nt)), [end] * nt)
    routing = pywrapcp.RoutingModel(manager)

    # one time matrix per asset type: service at the origin plus travel to the destination
    service = np.zeros(nt + nc + 1)
    matrices: dict[str, int] = {}
    for asset in {t.asset_type for t in teams}:
        for j, c in enumerate(cases):
            service[nt + j] = travel.service_seconds(asset, c.people)
        m = travel.travel_seconds(asset, dist) + service[: nt + nc, None]
        full = np.zeros((nt + nc + 1, nt + nc + 1), dtype=np.int64)
        full[: nt + nc, : nt + nc] = np.minimum(m, HORIZON_S * 4).astype(np.int64)
        np.fill_diagonal(full, 0)
        matrices[asset] = routing.RegisterTransitMatrix(full.tolist())
    for v, t in enumerate(teams):
        routing.SetArcCostEvaluatorOfVehicle(matrices[t.asset_type], v)

    routing.AddDimensionWithVehicleTransits([matrices[t.asset_type] for t in teams], 0, HORIZON_S * 2, False, "time")
    time_dim = routing.GetDimensionOrDie("time")
    for v, t in enumerate(teams):
        start = routing.Start(v)
        time_dim.CumulVar(start).SetRange(min(t.available_in_s, HORIZON_S), HORIZON_S)

    # a household bigger than any team that can reach it gets a full first trip;
    # the field team reports how many it took and the rest are re-planned
    caps = [t.capacity for t in teams]
    demands = (
        [0] * nt
        + [min(c.people or UNKNOWN_PEOPLE, max(caps[v] for v in allowed[j])) for j, c in enumerate(cases)]
        + [0]
    )
    demand_cb = routing.RegisterUnaryTransitCallback(lambda i: demands[manager.IndexToNode(i)])
    routing.AddDimensionWithVehicleCapacity(demand_cb, 0, caps, True, "capacity")

    # the same clock again, so arriving after the water costs on top of the waiting cost
    deadline_dim = None
    if any(c.deadline_s is not None for c in cases):
        routing.AddDimensionWithVehicleTransits(
            [matrices[t.asset_type] for t in teams], 0, HORIZON_S * 2, False, "deadline"
        )
        deadline_dim = routing.GetDimensionOrDie("deadline")
        for v, t in enumerate(teams):
            deadline_dim.CumulVar(routing.Start(v)).SetRange(min(t.available_in_s, HORIZON_S), HORIZON_S)

    for j, c in enumerate(cases):
        idx = manager.NodeToIndex(nt + j)
        routing.AddDisjunction([idx], _drop_penalty(c))
        if len(allowed[j]) < nt:
            # SetAllowedVehiclesForIndex's Span binding is broken in the Python wheel; -1 = unserved
            routing.VehicleVar(idx).SetValues([-1, *allowed[j]])
        time_dim.SetCumulVarSoftUpperBound(idx, 0, LATENESS_COEF.get(c.level, 1))
        if deadline_dim is not None and c.deadline_s is not None:
            deadline_dim.SetCumulVarSoftUpperBound(idx, max(0, c.deadline_s), DEADLINE_COEF)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(max(50, int(time_limit_s * 1000)))

    solution = None
    if initial_routes:
        case_node = {c.id: nt + j for j, c in enumerate(cases)}
        routes = [[case_node[cid] for cid in initial_routes.get(t.id, []) if cid in case_node] for t in teams]
        routing.CloseModelWithParameters(params)
        initial = routing.ReadAssignmentFromRoutes(routes, True)
        if initial:
            solution = routing.SolveFromAssignmentWithParameters(initial, params)
    if solution is None:
        solution = routing.SolveWithParameters(params)
    if solution is None:
        return Plan("no_solution", dropped=dropped, solver_ms=_ms(started))

    result = Plan("ok", objective=float(solution.ObjectiveValue()))
    for v, t in enumerate(teams):
        idx = routing.Start(v)
        prev_node, seq = v, 0
        while not routing.IsEnd(idx := solution.Value(routing.NextVar(idx))):
            node = manager.IndexToNode(idx)
            c = cases[node - nt]
            seq += 1
            d = float(dist[prev_node, node])
            arrival = int(solution.Min(time_dim.CumulVar(idx)))
            result.stops.append(
                Stop(
                    case_id=c.id,
                    team_id=t.id,
                    sequence=seq,
                    distance_m=int(d),
                    travel_s=int(travel.travel_seconds(t.asset_type, d)),
                    arrival_s=arrival,
                    margin_s=c.deadline_s - arrival if c.deadline_s is not None else None,
                )
            )
            prev_node = node
    served = {s.case_id for s in result.stops}
    for c in all_cases:
        if c.id not in served and c.id not in dropped:
            dropped[c.id] = "Lower priority than the cases assigned; waiting for a free team"
    result.dropped = dropped
    by_id = {c.id: c for c in cases}
    result.people_covered = sum(by_id[s.case_id].people or UNKNOWN_PEOPLE for s in result.stops)
    result.critical_covered = sum(1 for s in result.stops if by_id[s.case_id].level == "critical")
    _explain(result, teams, cases, dist)
    result.solver_ms = _ms(started)
    return result


def _explain(result: Plan, teams: list[DTeam], cases: list[DCase], dist: np.ndarray) -> None:
    """Plain reasons a coordinator can check before approving."""
    nt = len(teams)
    t_index = {t.id: i for i, t in enumerate(teams)}
    c_index = {c.id: j for j, c in enumerate(cases)}
    per_team: dict[str, int] = {}
    for s in result.stops:
        per_team[s.team_id] = per_team.get(s.team_id, 0) + 1
    for s in result.stops:
        t, c = teams[t_index[s.team_id]], cases[c_index[s.case_id]]
        j = nt + c_index[s.case_id]
        reasons = []
        if s.sequence == 1:
            capable = [
                (float(travel.travel_seconds(o.asset_type, dist[t_index[o.id], j])) + o.available_in_s, o)
                for o in teams
                if _reach(o, c).ok
            ]
            capable.sort(key=lambda x: x[0])
            rank = next((i for i, (_, o) in enumerate(capable) if o.id == t.id), None)
            label = travel.ASSET_LABEL[t.asset_type]
            if rank == 0:
                reasons.append(f"Closest {label} that can reach it")
            elif rank is not None:
                reasons.append(f"Closer teams are covering more urgent cases (#{rank + 1} nearest)")
        at_arrival = c.depth_after(s.arrival_s)
        reach = travel.can_reach(t.asset_type, at_arrival, c.in_flood_zone)
        if at_arrival and at_arrival >= 0.9:
            rising = c.depth_m is not None and at_arrival > c.depth_m + 0.1
            reasons.append(f"{reach.reason} (~{at_arrival:.1f} m{' by arrival' if rising else ''})")
        if s.margin_s is not None and c.deadline_s is not None:
            line = f"Water reaches the danger line in ~{max(1, round(c.deadline_s / 60))} min"
            if s.margin_s >= 0:
                reasons.insert(0, f"{line}; arrives with {round(s.margin_s / 60)} min to spare")
            else:
                reasons.insert(0, f"{line}; arrives ~{round(-s.margin_s / 60)} min after it, the soonest any team can")
        km = s.distance_m / 1000
        reasons.append(f"{km:.1f} km, about {max(1, round(s.travel_s / 60))} min away")
        if c.people:
            fit = "fits" if c.people <= t.capacity else "first trip of several"
            reasons.append(f"{c.people} people, {t.call_sign} carries {t.capacity} ({fit})")
        if per_team[s.team_id] > 1:
            reasons.append(f"Stop {s.sequence} of {per_team[s.team_id]} on this route")
        if c.level in ("critical", "high"):
            reasons.insert(0, f"{c.level.capitalize()} priority, scored {c.urgency}")
        s.reasons = reasons


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
