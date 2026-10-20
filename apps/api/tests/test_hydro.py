"""The flood model obeys the physics it claims, and the crowd moves it toward the truth."""

from __future__ import annotations

import numpy as np
import pytest

from app.services import hydro, waterclock
from app.services.hydro import Ensemble, Forcing, Grid, Model, Observation, Source

CELL = 100.0


def _grid(z: np.ndarray, sea: np.ndarray | None = None) -> Grid:
    water = np.zeros(z.shape, dtype=np.uint8)
    if sea is not None:
        water[sea] = hydro.SEA
    return Grid.from_arrays(z.astype(float), water, west=80.0, north=13.0, cell_m=CELL)


def _bowl(n: int = 21) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n]
    return 0.002 * ((x - n // 2) ** 2 + (y - n // 2) ** 2)


def test_still_water_stays_still() -> None:
    m = Model(_grid(_bowl()), drain_mm_h=0)
    m.h = np.maximum(0.0, 0.4 - m.grid.z)
    before = m.h.copy()
    m.run(30, Forcing.none())
    assert np.abs(m.h - before).max() < 1e-9
    assert np.abs(m.qx).max() < 1e-9 and np.abs(m.qy).max() < 1e-9


def test_closed_basin_conserves_water_and_never_goes_negative() -> None:
    m = Model(_grid(_bowl()), drain_mm_h=0)
    m.h[2:6, 2:6] = 1.5  # a mound on the rim
    v0 = m.volume_m3()
    m.run(45, Forcing.none())
    assert m.volume_m3() == pytest.approx(v0, rel=1e-9)
    assert m.h.min() >= 0


def test_water_runs_downhill() -> None:
    z = np.tile(np.linspace(3.0, 0.0, 30), (8, 1))  # falls from west to east
    m = Model(_grid(z), drain_mm_h=0)
    m.h[:, :4] = 0.5
    m.run(60, Forcing.none())
    cols = np.arange(30)
    centre = (m.h.sum(axis=0) * cols).sum() / m.h.sum()
    # Manning flow on a 0.1% slope moves a few hundred metres in an hour, and only downhill
    assert centre > 6
    assert m.h[:, 0].max() < 0.1


def test_rain_on_a_flat_closed_box_fills_evenly() -> None:
    m = Model(_grid(np.zeros((10, 10))), drain_mm_h=0)
    m.run(60, Forcing(rain_mm_h=((0, 36.0), (600, 36.0))))
    assert m.h == pytest.approx(np.full((10, 10), 0.036), abs=1e-9)


def test_drains_take_their_share_of_the_rain() -> None:
    m = Model(_grid(np.zeros((10, 10))), drain_mm_h=12)
    m.run(60, Forcing(rain_mm_h=((0, 36.0), (600, 36.0))))
    assert m.h.mean() == pytest.approx(0.024, abs=1e-6)


def test_a_river_source_adds_its_discharge() -> None:
    g = _grid(np.zeros((12, 12)))
    lat, lng = g.centre(6, 6)
    m = Model(g, drain_mm_h=0)
    m.run(10, Forcing(sources=(Source("river", lat, lng, ((0, 5.0), (600, 5.0))),)))
    assert m.volume_m3() == pytest.approx(5.0 * 600, rel=1e-6)


def test_the_sea_takes_what_reaches_it() -> None:
    z = np.tile(np.linspace(2.0, 0.2, 12), (6, 1))
    sea = np.zeros(z.shape, dtype=bool)
    sea[:, -3:] = True
    z[sea] = -1.0
    m = Model(_grid(z, sea), drain_mm_h=0, sea_level_m=0.0)
    m.h[:, :3] = 0.6
    land = ~sea
    v0 = float((m.h * land).sum())
    m.run(180, Forcing.none())
    assert float((m.h * land).sum()) < 0.5 * v0


def test_depth_at_reads_the_cell_under_a_point() -> None:
    g = _grid(np.zeros((10, 10)))
    m = Model(g, drain_mm_h=0)
    m.h[3, 7] = 1.25
    lat, lng = g.centre(3, 7)
    assert m.depth_at(lat, lng) == pytest.approx(1.25)
    assert m.depth_at(0.0, 0.0) is None


# --- assimilation --------------------------------------------------------------------------


def test_a_report_pulls_the_water_toward_it_nearby_and_not_far_away() -> None:
    g = _grid(np.zeros((40, 40)))
    ens = Ensemble(g, Forcing.none(), members=((1.0, 1.0),), drain_mm_h=0)
    lat, lng = g.centre(20, 20)
    ens.assimilate([Observation(lat, lng, depth_m=1.0, sigma_m=0.2, minute=0)])
    m = ens.members[0]
    assert m.depth_at(lat, lng) == pytest.approx(1.0, abs=0.15)
    assert m.h[20, 23] > 0.2  # 300 m away still feels it
    assert m.h[20, 39] < 0.01  # 1.9 km away does not


def test_a_report_never_puts_water_on_ground_above_its_surface() -> None:
    z = np.zeros((30, 30))
    z[:, 18:] = 5.0  # a ridge east of the report
    g = _grid(z)
    ens = Ensemble(g, Forcing.none(), members=((1.0, 1.0),), drain_mm_h=0)
    lat, lng = g.centre(15, 15)
    ens.assimilate([Observation(lat, lng, depth_m=1.0, sigma_m=0.2, minute=0)])
    assert ens.members[0].h[:, 18:].max() == 0.0


def test_reports_teach_the_ensemble_which_forcing_is_true() -> None:
    """Identical twin: the truth rains 1.5x the forecast; the crowd's readings find that out."""
    g = _grid(_bowl(25) * 0.2)
    rain = Forcing(rain_mm_h=((0, 60.0), (600, 60.0)))
    truth = Model(g, drain_mm_h=0)
    ens = Ensemble(g, rain, members=((0.5, 1.0), (1.0, 1.0), (1.5, 1.0), (2.0, 1.0)), drain_mm_h=0)
    for minute in range(15, 121, 15):
        truth.run(15, rain.scaled(1.5, 1.0))
        ens.advance(minute)
        obs = [Observation(*g.centre(i, j), float(truth.h[i, j]), 0.02, minute) for i, j in ((5, 5), (12, 12), (19, 8))]
        ens.assimilate(obs)
    assert int(np.argmax(ens.weights)) == 2


def test_forecast_says_when_water_reaches_a_line() -> None:
    g = _grid(np.zeros((8, 8)))
    rain = Forcing(rain_mm_h=((0, 60.0), (600, 60.0)))  # 1 mm a minute on a closed box
    ens = Ensemble(g, rain, members=((1.0, 1.0),), drain_mm_h=0)
    fc = ens.forecast(horizon_min=120, every_min=10)
    lat, lng = g.centre(4, 4)
    clock = fc.time_to(lat, lng, 0.045)
    assert clock is not None
    assert clock.p50 == pytest.approx(45, abs=1)
    assert fc.time_to(lat, lng, 5.0) is None  # beyond the horizon
    band = fc.depths(lat, lng)
    assert band is not None and band.p50[-1] == pytest.approx(0.12, abs=1e-6)


def test_forecast_spread_brackets_the_uncertain_forcing() -> None:
    g = _grid(np.zeros((8, 8)))
    rain = Forcing(rain_mm_h=((0, 60.0), (600, 60.0)))
    ens = Ensemble(g, rain, members=((0.5, 1.0), (1.0, 1.0), (1.5, 1.0)), drain_mm_h=0)
    fc = ens.forecast(horizon_min=60, every_min=10)
    d = fc.depths(*g.centre(4, 4))
    assert d is not None and d.p10[-1] < d.p50[-1] < d.p90[-1]
    clock = fc.time_to(*g.centre(4, 4), 0.025)
    assert clock is not None and clock.late is not None
    assert clock.early < clock.p50 < clock.late


# --- the water clock -----------------------------------------------------------------------


def test_danger_line_follows_where_the_family_can_go() -> None:
    assert waterclock.danger_line("first_floor", {}).depth_m == pytest.approx(3.2)
    assert waterclock.danger_line("second_floor", {}).depth_m == pytest.approx(6.0)
    assert waterclock.danger_line("roof", {}).depth_m == pytest.approx(2.6)
    assert waterclock.danger_line("knee", {}).depth_m == pytest.approx(2.4)  # they climb to the roof
    # someone who cannot be walked out sets a lower line
    assert waterclock.danger_line("knee", {"infant": 1}).depth_m == pytest.approx(1.0)
    assert waterclock.danger_line("waist", {"medical": ["dialysis"]}).depth_m == pytest.approx(1.0)
    assert waterclock.danger_line(None, {}).label


def test_reports_become_gauge_readings_with_honest_error() -> None:
    o = waterclock.observation(12.98, 80.22, "waist", minute=30)
    assert o is not None and o.depth_m == pytest.approx(0.8) and o.sigma_m >= 0.15
    assert waterclock.observation(12.98, 80.22, "unknown", minute=30) is None
    assert waterclock.observation(12.98, 80.22, None, minute=30) is None
    roof = waterclock.observation(12.98, 80.22, "roof", minute=30)
    assert roof is not None and roof.sigma_m > o.sigma_m  # "on the roof" says less about depth


def test_clock_reads_the_forecast_at_the_household() -> None:
    g = _grid(np.zeros((8, 8)))
    ens = Ensemble(g, Forcing(rain_mm_h=((0, 600.0), (600, 600.0))), members=((1.0, 1.0),), drain_mm_h=0)
    fc = ens.forecast(horizon_min=180, every_min=15)  # 10 mm a minute
    lat, lng = g.centre(4, 4)
    clock = waterclock.clock_for(fc, lat, lng, "knee", {"infant": 1})
    assert clock is not None
    assert clock.danger_m == pytest.approx(1.0)
    assert clock.minutes == pytest.approx(100, abs=1)
    assert clock.rise_cm_h == pytest.approx(60, abs=1)
    assert waterclock.clock_for(fc, 0.0, 0.0, "knee", {}) is None  # outside the model


def test_clock_counts_down_between_forecasts() -> None:
    c = waterclock.WaterClock(0.4, 1.3, "Too deep to stand in", 50.0, 30.0, 80.0, 20.0)
    assert c.remaining(10) == pytest.approx(40)
    assert c.remaining(70) == 0
    assert waterclock.WaterClock(0.4, 1.3, "x", None, None, None, 0.0).remaining(10) is None


def test_nowcast_assimilates_reports_at_their_own_time() -> None:
    g = _grid(np.zeros((30, 30)))
    lat, lng = g.centre(15, 15)

    def centre_after(report_minute: float) -> float:
        nc = waterclock.Nowcast(g, Forcing.none(), spinup_min=0, members=((1.0, 1.0),), drain_mm_h=0)
        nc.report(waterclock.observation(lat, lng, "waist", minute=report_minute))
        fc = nc.cycle(30)
        assert fc.minute == 30 and nc.forecast is fc and not nc.pending
        depth = nc.ensemble.members[0].depth_at(lat, lng)
        assert depth is not None
        return depth

    # an early reading has had time to spread across flat ground; a fresh one has not
    assert centre_after(5) < centre_after(29) - 0.1


def test_nowcast_profile_is_measured_from_now() -> None:
    g = _grid(np.zeros((8, 8)))
    nc = waterclock.Nowcast(
        g, Forcing(rain_mm_h=((0, 60.0), (600, 60.0))), spinup_min=0, members=((1.0, 1.0),), drain_mm_h=0
    )
    nc.cycle(0)
    profile = nc.profile(20, *g.centre(4, 4))  # asked 20 minutes after the forecast was issued
    assert profile[0][0] == 0
    assert profile[0][1] == pytest.approx(0.02, abs=1e-3)
    clock = nc.clock(20, *g.centre(4, 4), "knee", {})
    assert clock is not None and clock.minutes is None  # 1.3 m is beyond three hours of 1 mm a minute
