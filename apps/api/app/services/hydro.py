"""Where the water is, and where it will be.

A 2D flood model on a terrain grid: the local inertial form of the shallow water
equations (Bates, Horritt and Fewtrell 2010, the scheme inside LISFLOOD-FP), with
Manning friction, rain, river releases, street drains and a fixed-level sea.

It runs as a small ensemble whose members disagree about the forcing: how hard it
rains and how much the reservoirs release. Every SOS that says "waist deep" is a
water gauge. Each reading re-weights the members by how well they predicted it,
then nudges every member's water toward it. Run forward, the ensemble gives each
household a water clock: when the water will reach its danger line, with an early
and a late estimate.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numba
import numpy as np

G = 9.81
HMIN = 1e-3  # m; shallower faces carry no flow
ALPHA = 0.7  # CFL safety factor for the time step
DT_MAX = 60.0  # s
MANNING_LAND = 0.06  # streets between buildings, at 200 m cells
MANNING_CHANNEL = 0.035
DRAIN_MM_H = 3.0  # what clogged storm drains and saturated soil still take away
M_PER_DEG_LAT = 110_600.0
M_PER_DEG_LNG = 107_800.0  # at 13 N, as everywhere else in the code base

# water classes in the terrain mask
CHANNEL, LAKE, SEA = 1, 2, 3

# assimilation
BACKGROUND_SIGMA_M = 0.6  # how far the model's own depth may be off
CORRELATION_M = 400.0  # a report speaks for its street, fading over a few hundred metres
FORGET = 0.9  # old evidence about the forcing fades, so the ensemble can change its mind
WEIGHT_FLOOR = 0.01
# (rain scale, release scale) per member: the plausible spread around the forecast
DEFAULT_MEMBERS: tuple[tuple[float, float], ...] = (
    (0.6, 0.6),
    (0.8, 1.25),
    (1.0, 1.0),
    (1.0, 1.6),
    (1.25, 0.8),
    (1.4, 1.4),
    (1.7, 1.0),
    (1.2, 2.0),
)

Series = tuple[tuple[float, float], ...]  # (minute, value), linear between points, flat outside


def _seconds(series: Series, width: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """A series as (seconds, values) arrays, padded to a width with flat points far in the future."""
    pts = list(series) or [(0.0, 0.0)]
    pts += [(pts[-1][0] + 1e6 * (k + 1), pts[-1][1]) for k in range(width - len(pts))]
    return np.array([t * 60.0 for t, _ in pts]), np.array([v for _, v in pts], dtype=np.float64)


@dataclass(frozen=True)
class Grid:
    z: np.ndarray  # ground elevation, m, north row first
    water: np.ndarray  # CHANNEL, LAKE, SEA or 0
    west: float
    north: float
    cell_m: float

    @classmethod
    def from_arrays(cls, z: np.ndarray, water: np.ndarray, west: float, north: float, cell_m: float) -> Grid:
        return cls(np.asarray(z, dtype=np.float64), np.asarray(water, dtype=np.uint8), west, north, float(cell_m))

    @classmethod
    def load(cls, path: Path) -> Grid:
        d = np.load(path)
        bounds = d["bounds"]
        return cls.from_arrays(d["z"], d["water"], float(bounds[0]), float(bounds[3]), float(d["cell_m"]))

    @property
    def shape(self) -> tuple[int, int]:
        ny, nx = self.z.shape
        return int(ny), int(nx)

    @property
    def dlat(self) -> float:
        return self.cell_m / M_PER_DEG_LAT

    @property
    def dlng(self) -> float:
        return self.cell_m / M_PER_DEG_LNG

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        ny, nx = self.shape
        return self.west, self.north - ny * self.dlat, self.west + nx * self.dlng, self.north

    def cell(self, lat: float, lng: float) -> tuple[int, int] | None:
        i = math.floor((self.north - lat) / self.dlat)
        j = math.floor((lng - self.west) / self.dlng)
        ny, nx = self.shape
        return (i, j) if 0 <= i < ny and 0 <= j < nx else None

    def centre(self, i: int, j: int) -> tuple[float, float]:
        return self.north - (i + 0.5) * self.dlat, self.west + (j + 0.5) * self.dlng

    def nearest_channel(self, lat: float, lng: float, within_m: float = 2000.0) -> tuple[float, float]:
        """A release enters the river, as it does through a weir: the closest channel cell, if one is near."""
        c = self.cell(lat, lng)
        ii, jj = np.nonzero(self.water == CHANNEL)
        if c is None or not len(ii):
            return lat, lng
        d2 = (ii - c[0]) ** 2 + (jj - c[1]) ** 2
        k = int(np.argmin(d2))
        if math.sqrt(float(d2[k])) * self.cell_m > within_m:
            return lat, lng
        return self.centre(int(ii[k]), int(jj[k]))


@dataclass(frozen=True)
class Source:
    """A river or reservoir release entering at one point."""

    name: str
    lat: float
    lng: float
    m3s: Series


@dataclass(frozen=True)
class Forcing:
    rain_mm_h: Series = ()
    sources: tuple[Source, ...] = ()
    rain_scale: float = 1.0
    inflow_scale: float = 1.0

    @classmethod
    def none(cls) -> Forcing:
        return cls()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Forcing:
        return cls(
            rain_mm_h=tuple((float(t), float(v)) for t, v in d.get("rain_mm_h", [])),
            sources=tuple(
                Source(s["name"], float(s["lat"]), float(s["lng"]), tuple((float(t), float(v)) for t, v in s["m3s"]))
                for s in d.get("sources", [])
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rain_mm_h": [list(p) for p in self.rain_mm_h],
            "sources": [
                {"name": s.name, "lat": s.lat, "lng": s.lng, "m3s": [list(p) for p in s.m3s]} for s in self.sources
            ],
        }

    def scaled(self, rain: float, inflow: float) -> Forcing:
        return replace(self, rain_scale=self.rain_scale * rain, inflow_scale=self.inflow_scale * inflow)


class Model:
    """One flood: water depth in each cell and the discharge across each face."""

    def __init__(self, grid: Grid, drain_mm_h: float = DRAIN_MM_H, sea_level_m: float = 0.0, minute: float = 0.0):
        self.grid = grid
        ny, nx = grid.shape
        self.h = np.zeros((ny, nx))
        self.qx = np.zeros((ny, nx + 1))  # m2/s across west/east faces, positive eastward
        self.qy = np.zeros((ny + 1, nx))  # m2/s across north/south faces, positive southward
        self.minute = minute
        self.drain_ms = drain_mm_h / 1000 / 3600
        self.sea = grid.water == SEA
        self.sea_level_m = sea_level_m
        n = np.where(grid.water == CHANNEL, MANNING_CHANNEL, MANNING_LAND)
        self._n2x = ((n[:, :-1] + n[:, 1:]) / 2) ** 2
        self._n2y = ((n[:-1, :] + n[1:, :]) / 2) ** 2
        self._sea_h = np.maximum(0.0, sea_level_m - grid.z)
        self._apply_sea()

    def copy(self) -> Model:
        m = object.__new__(Model)
        m.__dict__.update(self.__dict__)
        m.h, m.qx, m.qy = self.h.copy(), self.qx.copy(), self.qy.copy()
        return m

    def volume_m3(self) -> float:
        return float(self.h[~self.sea].sum()) * self.grid.cell_m**2

    def depth_at(self, lat: float, lng: float) -> float | None:
        c = self.grid.cell(lat, lng)
        return float(self.h[c]) if c else None

    def run(self, minutes: float, forcing: Forcing) -> None:
        self.run_to(self.minute + minutes, forcing)

    def run_to(self, minute: float, forcing: Forcing) -> None:
        cells = [(c, src) for src in forcing.sources if (c := self.grid.cell(src.lat, src.lng))]
        width = max((len(src.m3s) for _, src in cells), default=1)
        src_ij = np.zeros((len(cells), 2), dtype=np.int64)
        src_t, src_v = np.zeros((len(cells), width)), np.zeros((len(cells), width))
        for k, (c, src) in enumerate(cells):
            src_ij[k] = c
            src_t[k], src_v[k] = _seconds(src.m3s, width)
        rain_t, rain_v = _seconds(forcing.rain_mm_h)
        _run(
            self.grid.z, self.h, self.qx, self.qy, self._n2x, self._n2y, self.sea, self._sea_h, self.grid.cell_m,
            self.minute * 60.0, minute * 60.0, self.drain_ms,
            rain_t, rain_v, forcing.rain_scale / 3.6e6, src_ij, src_t, src_v, forcing.inflow_scale,
        )  # fmt: skip
        self.minute = minute

    def _apply_sea(self) -> None:
        self.h[self.sea] = self._sea_h[self.sea]


@numba.njit(cache=True, nogil=True)
def _run(z, h, qx, qy, n2x, n2y, sea, sea_h, dx, t, end, drain_ms, rain_t, rain_v, rain_k, src_ij, src_t, src_v, src_k):
    """The whole time loop compiled, so ensemble members never wait on each other for the GIL."""
    added, scale = np.empty_like(h), np.empty_like(h)
    deepest = h.max()
    while t < end - 1e-9:
        dt = DT_MAX if deepest < HMIN else min(DT_MAX, ALPHA * dx / np.sqrt(G * deepest))
        dt = min(dt, end - t)
        added[:] = np.interp(t, rain_t, rain_v) * rain_k * dt
        for k in range(src_ij.shape[0]):
            added[src_ij[k, 0], src_ij[k, 1]] += np.interp(t, src_t[k], src_v[k]) * src_k * dt / dx**2
        deepest = _step(z, h, qx, qy, n2x, n2y, sea, sea_h, added, scale, dx, dt, drain_ms * dt)
        t += dt


@numba.njit(cache=True, nogil=True)
def _step(z, h, qx, qy, n2x, n2y, sea, sea_h, added, scale, dx, dt, drain):
    """One time step, fused into a single pass per stage. Bates et al. (2010) eq. 11 for the
    faces (momentum without advection, friction implicit), a limiter so no cell sends away
    more water than it holds, then continuity. Returns the deepest water for the next step."""
    ny, nx = h.shape
    for i in range(ny):
        for j in range(1, nx):
            za, zb = z[i, j - 1], z[i, j]
            qx[i, j] = _face(qx[i, j], za + h[i, j - 1], zb + h[i, j], za, zb, n2x[i, j - 1], dt, dx)
    for i in range(1, ny):
        for j in range(nx):
            za, zb = z[i - 1, j], z[i, j]
            qy[i, j] = _face(qy[i, j], za + h[i - 1, j], zb + h[i, j], za, zb, n2y[i - 1, j], dt, dx)

    k = dt / dx
    for i in range(ny):
        for j in range(nx):
            out = (max(qx[i, j + 1], 0.0) + max(-qx[i, j], 0.0) + max(qy[i + 1, j], 0.0) + max(-qy[i, j], 0.0)) * k
            avail = h[i, j] + added[i, j]
            scale[i, j] = avail / out if out > avail and not sea[i, j] else 1.0
    for i in range(ny):
        for j in range(1, nx):
            q = qx[i, j]
            qx[i, j] = q * scale[i, j - 1] if q > 0 else q * scale[i, j]
    for i in range(1, ny):
        for j in range(nx):
            q = qy[i, j]
            qy[i, j] = q * scale[i - 1, j] if q > 0 else q * scale[i, j]

    deepest = 0.0
    for i in range(ny):
        for j in range(nx):
            if sea[i, j]:
                v = sea_h[i, j]
            else:
                v = h[i, j] + k * (qx[i, j] - qx[i, j + 1] + qy[i, j] - qy[i + 1, j]) + added[i, j]
                v = max(0.0, v - min(v, drain))
            h[i, j] = v
            deepest = max(deepest, v)
    return deepest


@numba.njit(cache=True, nogil=True, inline="always")
def _face(q, eta_a, eta_b, z_a, z_b, n2, dt, dx):
    hflow = max(eta_a, eta_b) - max(z_a, z_b)
    if hflow <= HMIN:
        return 0.0
    return (q - G * hflow * dt * (eta_b - eta_a) / dx) / (1.0 + G * dt * n2 * abs(q) / hflow ** (7.0 / 3.0))


# --- the crowd as a gauge network ----------------------------------------------------------


@dataclass(frozen=True)
class Observation:
    lat: float
    lng: float
    depth_m: float
    sigma_m: float
    minute: float


@dataclass(frozen=True)
class Band:
    """Depth at one place over the forecast frames: low, middle and high estimates."""

    minutes: np.ndarray
    p10: np.ndarray
    p50: np.ndarray
    p90: np.ndarray


@dataclass(frozen=True)
class Clock:
    """Minutes from the forecast's start until the water reaches a line."""

    p50: float
    early: float
    late: float | None  # None: the slow members never get there within the horizon


@dataclass
class Forecast:
    grid: Grid
    minute: float  # simulation minute the forecast starts at
    every_min: float
    p10: np.ndarray  # (frames, ny, nx) metres
    p50: np.ndarray
    p90: np.ndarray
    weights: np.ndarray = field(default_factory=lambda: np.ones(1))

    @property
    def minutes(self) -> np.ndarray:
        return np.arange(self.p50.shape[0]) * self.every_min

    def depths(self, lat: float, lng: float) -> Band | None:
        c = self.grid.cell(lat, lng)
        if c is None:
            return None
        i, j = c
        return Band(self.minutes, self.p10[:, i, j], self.p50[:, i, j], self.p90[:, i, j])

    def time_to(self, lat: float, lng: float, line_m: float) -> Clock | None:
        b = self.depths(lat, lng)
        if b is None:
            return None
        mid = _crossing(b.minutes, b.p50, line_m)
        if mid is None:
            return None
        early = _crossing(b.minutes, b.p90, line_m)  # the wettest members get there first
        return Clock(mid, early if early is not None else mid, _crossing(b.minutes, b.p10, line_m))


def _crossing(minutes: np.ndarray, depth: np.ndarray, line: float) -> float | None:
    above = np.nonzero(depth >= line)[0]
    if not len(above):
        return None
    k = int(above[0])
    if k == 0:
        return 0.0
    d0, d1 = float(depth[k - 1]), float(depth[k])
    return float(minutes[k - 1] + (line - d0) / (d1 - d0) * (minutes[k] - minutes[k - 1]))


class Ensemble:
    """Members that disagree about the forcing, weighted and nudged by what people report."""

    def __init__(
        self,
        grid: Grid,
        forcing: Forcing,
        members: Sequence[tuple[float, float]] = DEFAULT_MEMBERS,
        drain_mm_h: float = DRAIN_MM_H,
        minute: float = 0.0,
        sea_level_m: float = 0.0,
    ):
        self.grid = grid
        self.forcing = forcing
        self.scales = tuple(members)
        self.members = [Model(grid, drain_mm_h, sea_level_m, minute) for _ in self.scales]
        self.weights = np.full(len(self.scales), 1.0 / len(self.scales))

    @property
    def minute(self) -> float:
        return self.members[0].minute

    def advance(self, minute: float) -> None:
        _each(lambda k: self.members[k].run_to(minute, self.forcing.scaled(*self.scales[k])), len(self.members))

    def assimilate(self, obs: Sequence[Observation]) -> int:
        """Re-weight the members by how well each predicted the reports, then nudge them. Returns reports used."""
        located = [(o, c) for o in obs if (c := self.grid.cell(o.lat, o.lng)) is not None]
        if not located:
            return 0
        loglik = np.array(
            [sum(-0.5 * ((o.depth_m - m.h[c]) / o.sigma_m) ** 2 for o, c in located) for m in self.members]
        )
        logw = FORGET * np.log(self.weights) + loglik
        w = np.exp(logw - logw.max())
        w = np.maximum(w / w.sum(), WEIGHT_FLOOR)
        self.weights = w / w.sum()
        for m in self.members:
            self._nudge(m, located)
        return len(located)

    def _nudge(self, m: Model, located: list[tuple[Observation, tuple[int, int]]]) -> None:
        z, dx = self.grid.z, self.grid.cell_m
        num, den = np.zeros_like(m.h), np.zeros_like(m.h)
        r = math.ceil(3 * CORRELATION_M / dx)
        ny, nx = self.grid.shape
        for o, (i, j) in located:
            innovation = o.depth_m - float(m.h[i, j])
            if abs(innovation) < 1e-6:
                continue
            gain = BACKGROUND_SIGMA_M**2 / (BACKGROUND_SIGMA_M**2 + o.sigma_m**2)
            rows, cols = slice(max(0, i - r), min(ny, i + r + 1)), slice(max(0, j - r), min(nx, j + r + 1))
            ii, jj = np.ogrid[rows, cols]
            g = np.exp(-0.5 * ((ii - i) ** 2 + (jj - j) ** 2) * dx**2 / CORRELATION_M**2)
            if innovation > 0:
                # water only where the ground lies below the surface the reporter is standing in
                g = g * (z[rows, cols] <= z[i, j] + o.depth_m)
            num[rows, cols] += g * gain * innovation
            den[rows, cols] += g
        m.h = np.maximum(0.0, m.h + num / np.maximum(den, 1.0))
        m._apply_sea()

    def forecast(self, horizon_min: float, every_min: float) -> Forecast:
        frames = round(horizon_min / every_min) + 1
        ny, nx = self.grid.shape
        runs = np.zeros((len(self.members), frames, ny, nx), dtype=np.float32)

        def member(k: int) -> None:
            start = self.members[k]
            sim, forcing = start.copy(), self.forcing.scaled(*self.scales[k])
            runs[k, 0] = sim.h
            for f in range(1, frames):
                sim.run_to(start.minute + f * every_min, forcing)
                runs[k, f] = sim.h

        _each(member, len(self.members))
        p10, p50, p90 = _weighted_quantiles(runs, self.weights, (0.1, 0.5, 0.9))
        return Forecast(self.grid, self.minute, every_min, p10, p50, p90, self.weights.copy())


_pool = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1), thread_name_prefix="hydro")


def use_threads(n: int) -> None:
    """How many ensemble members run at once. A live API keeps this low, so the rest of the
    service (and Redis beside it) always has a core free."""
    global _pool
    _pool.shutdown(wait=False)
    _pool = ThreadPoolExecutor(max_workers=max(1, n), thread_name_prefix="hydro")


def _each(fn: Callable[[int], None], n: int) -> None:
    """Members are independent and the kernel releases the GIL, so they run side by side."""
    for _ in _pool.map(fn, range(n)):
        pass


def _weighted_quantiles(runs: np.ndarray, weights: np.ndarray, qs: Sequence[float]) -> list[np.ndarray]:
    order = np.argsort(runs, axis=0)
    ranked = np.take_along_axis(runs, order, axis=0)
    cum = np.cumsum(weights[order], axis=0)
    out = []
    for q in qs:
        idx = np.minimum((cum < q - 1e-9).sum(axis=0, keepdims=True), len(weights) - 1)
        out.append(np.take_along_axis(ranked, idx, axis=0)[0])
    return out
