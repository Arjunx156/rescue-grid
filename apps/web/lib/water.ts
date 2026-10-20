/**
 * The flood nowcast on the command map: decoding the forecast field, reading depth at a
 * frame or a point, and counting each family's water clock down on the disaster's clock.
 */

import type { WaterClockOut, WaterForecast } from "./api";

export interface WaterField {
  issuedAt: number;
  everyMin: number;
  frames: number;
  stepM: number;
  grid: WaterForecast["grid"];
  /** flat grid indices of the cells that are wet in some frame, ascending */
  cells: Uint32Array;
  /** frames x cells, depth in stepM steps: the likely (p50) and worst (p90) case */
  p50: Uint8Array;
  p90: Uint8Array;
  reportsUsed: number;
  members: WaterForecast["members"];
}

const M_PER_DEG_LAT = 110_600;
const M_PER_DEG_LNG = 107_800;

function bytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function decodeWater(f: WaterForecast): WaterField {
  const raw = bytes(f.cells);
  // copy into an aligned buffer; browsers are little-endian, like the server's "<u4"
  const cells = new Uint32Array(raw.slice().buffer, 0, raw.byteLength / 4);
  const p50 = bytes(f.p50);
  const p90 = bytes(f.p90);
  if (p50.length !== f.frames * cells.length || p90.length !== p50.length) {
    throw new Error("water forecast does not match its cell list");
  }
  return {
    issuedAt: new Date(f.issued_at).getTime(),
    everyMin: f.every_min,
    frames: f.frames,
    stepM: f.step_m,
    grid: f.grid,
    cells,
    p50,
    p90,
    reportsUsed: f.reports_used,
    members: f.members,
  };
}

/** Depth in metres of every listed cell at a fractional frame, linear between frames. */
export function frameDepths(w: WaterField, frame: number, worst: boolean, out?: Float32Array): Float32Array {
  const n = w.cells.length;
  const res = out && out.length === n ? out : new Float32Array(n);
  const src = worst ? w.p90 : w.p50;
  const f = Math.min(Math.max(frame, 0), w.frames - 1);
  const a = Math.floor(f);
  const b = Math.min(a + 1, w.frames - 1);
  const t = f - a;
  for (let k = 0; k < n; k++) res[k] = (src[a * n + k] * (1 - t) + src[b * n + k] * t) * w.stepM;
  return res;
}

export function cellBounds(w: WaterField, flat: number): [number, number, number, number] {
  const { west, north, cell_m, nx } = w.grid;
  const dlat = cell_m / M_PER_DEG_LAT;
  const dlng = cell_m / M_PER_DEG_LNG;
  const i = Math.floor(flat / nx);
  const j = flat % nx;
  return [west + j * dlng, north - (i + 1) * dlat, west + (j + 1) * dlng, north - i * dlat];
}

/** Square cells with their depth, for a fill or fill-extrusion layer. Dry cells are left out. */
/** 0.3 m: the bottom of the map's legend, and about where a family starts asking for help. */
export const SHOWN_DEPTH_M = 0.3;

export function waterFeatures(w: WaterField, depths: Float32Array, min = SHOWN_DEPTH_M): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (let k = 0; k < w.cells.length; k++) {
    const d = depths[k];
    if (d < min) continue;
    const [x1, y1, x2, y2] = cellBounds(w, w.cells[k]);
    features.push({
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [x1, y1],
            [x2, y1],
            [x2, y2],
            [x1, y2],
            [x1, y1],
          ],
        ],
      },
      properties: { d: Math.round(d * 100) / 100 },
    });
  }
  return { type: "FeatureCollection", features };
}

/** The likely and worst-case depth over the forecast at one point, or null when it stays dry. */
export function depthsAt(
  w: WaterField,
  lat: number,
  lng: number,
): { minutes: number[]; likely: number[]; worst: number[] } | null {
  const { west, north, cell_m, nx, ny } = w.grid;
  const i = Math.floor((north - lat) / (cell_m / M_PER_DEG_LAT));
  const j = Math.floor((lng - west) / (cell_m / M_PER_DEG_LNG));
  if (i < 0 || i >= ny || j < 0 || j >= nx) return null;
  const target = i * nx + j;
  let lo = 0;
  let hi = w.cells.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (w.cells[mid] < target) lo = mid + 1;
    else hi = mid - 1;
  }
  if (w.cells[lo] !== target) return null;
  const n = w.cells.length;
  const minutes: number[] = [];
  const likely: number[] = [];
  const worst: number[] = [];
  for (let f = 0; f < w.frames; f++) {
    minutes.push(f * w.everyMin);
    likely.push(w.p50[f * n + lo] * w.stepM);
    worst.push(w.p90[f * n + lo] * w.stepM);
  }
  return { minutes, likely, worst };
}

/** Minutes left on a water clock at `nowMs` on the disaster's clock; null when the water is not coming. */
export function clockLeft(clock: WaterClockOut | null | undefined, nowMs: number): number | null {
  if (!clock || clock.minutes == null) return null;
  const elapsed = (nowMs - new Date(clock.issued_at).getTime()) / 60_000;
  return Math.max(0, clock.minutes - elapsed);
}

export function clockText(minutes: number): string {
  if (minutes < 1) return "now";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes - h * 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}
