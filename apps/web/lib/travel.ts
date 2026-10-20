/** The same asset model the optimiser uses (apps/api/app/services/travel.py), for ETAs in the UI. */

const SPEED_KMH: Record<string, number> = {
  boat: 8,
  truck: 16,
  medical: 20,
  foot: 3.5,
  helicopter: 110,
};
const DETOUR: Record<string, number> = {
  boat: 1.2,
  truck: 1.45,
  medical: 1.4,
  foot: 1.3,
  helicopter: 1,
};
const STARTUP_S: Record<string, number> = {
  boat: 120,
  truck: 60,
  medical: 60,
  foot: 0,
  helicopter: 600,
};
const MAX_DEPTH_M: Record<string, number> = {
  truck: 0.9,
  medical: 0.5,
  foot: 0.7,
  boat: 99,
  helicopter: 99,
};
const WATER_DEPTH_M: Record<string, number> = {
  none: 0,
  ankle: 0.15,
  knee: 0.5,
  waist: 1,
  chest: 1.3,
  first_floor: 1.5,
  neck: 1.6,
  second_floor: 3,
  roof: 3,
};

export function haversineM(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const r = 6_371_000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dp = p2 - p1;
  const dl = ((lng2 - lng1) * Math.PI) / 180;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

export function etaSeconds(asset: string, meters: number): number {
  const ms = ((SPEED_KMH[asset] ?? 10) * 1000) / 3600;
  return (meters * (DETOUR[asset] ?? 1.3)) / ms + (STARTUP_S[asset] ?? 60);
}

export function effectiveDepth(water: string | null | undefined, floodDepth: number | null | undefined): number | null {
  const known = [WATER_DEPTH_M[water ?? "unknown"], floodDepth].filter((d): d is number => d != null);
  return known.length ? Math.max(...known) : null;
}

export function canReach(asset: string, depth: number | null, inFloodZone: boolean): { ok: boolean; why: string } {
  if (asset === "helicopter") return { ok: true, why: "Reaches anywhere" };
  if (asset === "boat") {
    return (depth ?? 0) >= 0.4 || inFloodZone
      ? { ok: true, why: "Can operate here" }
      : { ok: false, why: "Too shallow for a boat" };
  }
  const limit = MAX_DEPTH_M[asset] ?? 0.9;
  return depth != null && depth > limit
    ? { ok: false, why: `${depth.toFixed(1)} m is too deep` }
    : { ok: true, why: "Can get through" };
}
