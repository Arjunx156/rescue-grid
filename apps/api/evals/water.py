"""Water clock skill on the replay: an identical-twin experiment.

The truth is the simulated flood (app.sim.flood). Rescue Grid starts from the 2015-style
forecast, which is too low and too late, and either runs it alone or also assimilates
every located report as a gauge reading. Each hour, for every family that has reported
and is still waiting, we ask: will the water reach this family's true danger line in the
next three hours, and when? Scoring against the true line isolates the forecast from the
danger-line heuristic.
"""

from __future__ import annotations

import json
import statistics
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import Any

import numpy as np

from app.agents import rules
from app.core.settings import get_settings
from app.services import waterclock
from app.services.hydro import Forcing, Grid

EVERY_MIN = 60
WINDOW_MIN = 360  # a family is scored for six hours after its first report
HOURS = 48


def score(mode: str) -> dict[str, Any]:
    """mode: "crowd" assimilates reports; "forecast" runs the forecast alone."""
    data = get_settings().data_dir
    base = data / "replay" / "chennai-2015"
    meta = json.loads((base / "dataset.json").read_text(encoding="utf-8"))
    rows = (base / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    msgs = sorted((json.loads(x) for x in rows if x.strip()), key=lambda m: m["t"])
    forcing = json.loads((base / "forcing.json").read_text(encoding="utf-8"))
    grid = Grid.load(data / "geo" / "terrain.npz")
    water = np.load(base / "water.npz")
    frames, step, every = water["frames"], float(water["step_m"]), float(water["every_min"])
    start = datetime.fromisoformat(meta["starts_at"])
    nc = waterclock.Nowcast(
        grid, Forcing.from_dict(forcing["forecast"]), forcing["spinup_min"], sea_level_m=forcing["sea_level_m"]
    )

    def minute(t: str) -> float:
        return (datetime.fromisoformat(t) - start).total_seconds() / 60

    hits = misses = false_alarms = quiet = 0
    timing: list[float] = []
    depth_err: list[float] = []
    pending = iter(msgs)
    nxt = next(pending, None)
    for m in range(0, HOURS * 60 + 1, EVERY_MIN):
        while nxt and minute(nxt["t"]) <= m:
            t = nxt["truth"]
            if mode == "crowd" and t["kind"] == "sos":
                e, _ = rules.extract(nxt["text"])
                # the reader's level at the reported household; geocoding error is scored elsewhere
                nc.report(waterclock.observation(t["lat"], t["lng"], e.water_level, minute(nxt["t"])))
            nxt = next(pending, None)
        fc = nc.cycle(m)
        k = round(m / every)
        for h in meta["households"]:
            first = minute(h["first_report"])
            if not first <= m < first + WINDOW_MIN:
                continue
            cell = grid.cell(h["lat"], h["lng"])
            band = fc.depths(h["lat"], h["lng"])
            if cell is None or band is None:
                continue
            truth = frames[:, cell[0], cell[1]] * step
            if truth[k] >= h["danger_m"]:
                continue  # already past the line: nothing left to forecast
            depth_err.append(abs(float(band.p50[0]) - float(truth[k])))
            ahead = np.nonzero(truth[k : k + round(180 / every) + 1] >= h["danger_m"])[0]
            true_min = float(ahead[0] * every) if len(ahead) else None
            clock = fc.time_to(h["lat"], h["lng"], h["danger_m"])
            if true_min is not None and clock is not None:
                hits += 1
                timing.append(abs(clock.p50 - true_min))
            elif true_min is not None:
                misses += 1
            elif clock is not None:
                false_alarms += 1
            else:
                quiet += 1
    return {
        "crossings": hits + misses,
        "detected": hits / max(1, hits + misses),
        "false_alarm_rate": false_alarms / max(1, false_alarms + quiet),
        "timing_error_min": statistics.median(timing) if timing else None,
        "depth_error_m": statistics.median(depth_err),
        "reports_used": nc.reports_used,
    }


def run_water() -> dict[str, float]:
    with ProcessPoolExecutor(max_workers=2) as pool:
        crowd, alone = pool.map(score, ("crowd", "forecast"))
    print("\nwater clock, 3 h ahead, against the simulated truth:")
    print(f"  {'':28}{'with reports':>14}{'forecast alone':>16}")
    for key, label in (
        ("detected", "danger crossings caught"),
        ("false_alarm_rate", "false alarms"),
        ("timing_error_min", "timing error (median min)"),
        ("depth_error_m", "depth error now (median m)"),
    ):
        a, b = crowd[key], alone[key]
        fmt = (lambda v: f"{v:.1%}") if key in ("detected", "false_alarm_rate") else (lambda v: f"{v:.2f}")
        print(f"  {label:28}{fmt(a) if a is not None else '-':>14}{fmt(b) if b is not None else '-':>16}")
    print(f"  {crowd['crossings']} crossings scored, {crowd['reports_used']} reports assimilated")
    return {
        "water_detected": crowd["detected"],
        "water_detected_forecast_alone": alone["detected"],
        "water_false_alarms": crowd["false_alarm_rate"],
        "water_timing_error_min": crowd["timing_error_min"] or 0.0,
        "water_depth_error_m": crowd["depth_error_m"],
        "water_depth_error_forecast_alone_m": alone["depth_error_m"],
        "water_reports_used": crowd["reports_used"],
    }
