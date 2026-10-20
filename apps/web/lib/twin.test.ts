import { describe, expect, test } from "bun:test";
import { BEATS, decodeTwin, depthsAt, storyAt, toScene, type WaterMeta } from "./twin";

const meta: WaterMeta = {
  file: "",
  ny: 2,
  nx: 3,
  west: 80,
  north: 13,
  dlat: 0.01,
  dlng: 0.01,
  frames: 2,
  every_min: 60,
  elev_step_m: 0.25,
  depth_step_m: 0.025,
};

function twin() {
  const n = meta.nx * meta.ny;
  const bytes = new Uint8Array(n * 3);
  bytes.fill(40, n, 2 * n); // 1.0 m everywhere in the first frame
  bytes.fill(80, 2 * n); // 2.0 m in the second
  return decodeTwin(meta, bytes.buffer);
}

describe("twin", () => {
  test("refuses a water file that does not match its description", () => {
    expect(() => decodeTwin(meta, new ArrayBuffer(5))).toThrow();
  });

  test("depth is linear between hourly frames and holds at the ends", () => {
    const out = new Float32Array(6);
    expect(depthsAt(twin(), 30, out)[0]).toBeCloseTo(1.5);
    expect(depthsAt(twin(), -10, out)[0]).toBeCloseTo(1.0);
    expect(depthsAt(twin(), 999, out)[5]).toBeCloseTo(2.0);
  });

  test("north-west is negative x and z, south-east positive", () => {
    expect(toScene(meta, 13, 80)).toEqual([-1.5, -1]);
    const [x, z] = toScene(meta, 12.98, 80.03);
    expect(x).toBeCloseTo(1.5);
    expect(z).toBeCloseTo(1);
  });

  test("the story starts at the first beat, ends at the last and only moves forward in time", () => {
    expect(storyAt(0).minute).toBe(BEATS[0].minute);
    expect(storyAt(1).minute).toBe(BEATS[BEATS.length - 1].minute);
    let last = -1;
    for (let p = 0; p <= 1; p += 0.01) {
      const m = storyAt(p).minute;
      expect(m).toBeGreaterThanOrEqual(last);
      last = m;
    }
    expect(storyAt(-3).eye).toEqual(BEATS[0].eye);
  });
});
