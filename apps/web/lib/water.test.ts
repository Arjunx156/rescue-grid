import { describe, expect, test } from "bun:test";
import type { WaterForecast } from "./api";
import { clockLeft, clockText, decodeWater, depthsAt, frameDepths, waterFeatures } from "./water";

const b64 = (a: ArrayBufferView) => btoa(String.fromCharCode(...new Uint8Array(a.buffer, a.byteOffset, a.byteLength)));

// a 2 x 3 grid, two wet cells (flat indices 1 and 4), two frames
const forecast: WaterForecast = {
  issued_at: "2015-12-01T18:00:00Z",
  every_min: 15,
  frames: 2,
  step_m: 0.025,
  grid: { west: 80, north: 13, cell_m: 200, ny: 2, nx: 3 },
  cells: b64(new Uint32Array([1, 4])),
  p50: b64(new Uint8Array([40, 8, 80, 8])), // frame 0: 1.0 m, 0.2 m; frame 1: 2.0 m, 0.2 m
  p90: b64(new Uint8Array([60, 8, 100, 8])),
  reports_used: 3,
  members: [],
};

describe("water", () => {
  test("decodes cells and depths, and refuses a mismatch", () => {
    const w = decodeWater(forecast);
    expect([...w.cells]).toEqual([1, 4]);
    expect(() => decodeWater({ ...forecast, p50: b64(new Uint8Array([1])) })).toThrow();
  });

  test("depth is linear between frames, likely or worst case", () => {
    const w = decodeWater(forecast);
    expect(frameDepths(w, 0.5, false)[0]).toBeCloseTo(1.5);
    expect(frameDepths(w, 1, true)[0]).toBeCloseTo(2.5);
  });

  test("dry cells stay off the map and squares close on themselves", () => {
    const w = decodeWater(forecast);
    const fc = waterFeatures(w, frameDepths(w, 0, false), 0.5);
    expect(fc.features).toHaveLength(1);
    const ring = (fc.features[0].geometry as GeoJSON.Polygon).coordinates[0];
    expect(ring[0]).toEqual(ring[4]);
  });

  test("reads the series at a point and nothing outside the wet cells", () => {
    const w = decodeWater(forecast);
    // cell 1 is row 0, column 1
    const at = depthsAt(w, 13 - 0.0005, 80 + 1.5 * (200 / 107_800));
    expect(at?.likely).toEqual([1, 2]);
    expect(depthsAt(w, 13 - 0.0005, 80 + 0.0005)).toBeNull();
  });

  test("a clock counts down from when it was issued and stops at zero", () => {
    const clock = {
      issued_at: "2015-12-01T18:00:00Z",
      depth_m: 0.5,
      danger_m: 2.4,
      danger_label: "Water reaches a single-storey roof",
      minutes: 50,
      early: 30,
      late: 90,
      rise_cm_h: 20,
    };
    const t = new Date("2015-12-01T18:20:00Z").getTime();
    expect(clockLeft(clock, t)).toBeCloseTo(30);
    expect(clockLeft(clock, t + 3_600_000)).toBe(0);
    expect(clockLeft({ ...clock, minutes: null }, t)).toBeNull();
    expect(clockText(0.4)).toBe("now");
    expect(clockText(130)).toBe("2 h 10 min");
  });
});
