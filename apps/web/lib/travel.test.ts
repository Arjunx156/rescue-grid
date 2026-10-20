import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { canReach, effectiveDepth, etaSeconds, haversineM } from "./travel";

// the UI's ETAs must agree with the optimiser's, so read its constants straight from the source
const py = readFileSync(join(import.meta.dir, "../../api/app/services/travel.py"), "utf8");

function pyDict(name: string): Record<string, number> {
  const body = py.match(new RegExp(`^${name} = {([^}]*)}`, "m"))?.[1];
  if (!body) throw new Error(`${name} not found in travel.py`);
  return Object.fromEntries([...body.matchAll(/"(\w+)":\s*([\d.]+)/g)].map((m) => [m[1], Number(m[2])]));
}

describe("travel model", () => {
  const speed = pyDict("SPEED_KMH");
  const detour = pyDict("DETOUR");
  const startup = pyDict("STARTUP_S");

  test.each(Object.keys(speed))("%s ETA matches the optimiser", (asset) => {
    expect(etaSeconds(asset, 0)).toBeCloseTo(startup[asset], 6);
    const perKm = (1000 * detour[asset]) / ((speed[asset] * 1000) / 3600);
    expect(etaSeconds(asset, 1000) - etaSeconds(asset, 0)).toBeCloseTo(perKm, 6);
  });

  test("haversine: one degree of latitude is about 111 km", () => {
    expect(haversineM(13, 80.2, 14, 80.2)).toBeGreaterThan(110_000);
    expect(haversineM(13, 80.2, 14, 80.2)).toBeLessThan(112_000);
  });

  test("depth takes the deeper of the report and the flood layer", () => {
    expect(effectiveDepth("knee", 1.2)).toBe(1.2);
    expect(effectiveDepth("roof", 0.4)).toBe(3);
    expect(effectiveDepth("unknown", null)).toBeNull();
  });

  test("who can reach what", () => {
    expect(canReach("truck", 1.3, true).ok).toBe(false);
    expect(canReach("truck", 0.5, false).ok).toBe(true);
    expect(canReach("boat", 0.1, false).ok).toBe(false);
    expect(canReach("boat", 0.1, true).ok).toBe(true);
    expect(canReach("helicopter", 3, true).ok).toBe(true);
  });
});
