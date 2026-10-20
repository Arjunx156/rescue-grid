/**
 * The landing page's 3D twin of the 2015 flood: decoding its data and mapping scroll to story.
 * Pure functions only; the renderer lives in components/landing/flood-twin.tsx.
 */

export interface WaterMeta {
  file: string;
  ny: number;
  nx: number;
  west: number;
  north: number;
  dlat: number;
  dlng: number;
  frames: number;
  every_min: number;
  elev_step_m: number;
  depth_step_m: number;
}

export interface Twin {
  meta: WaterMeta;
  /** ground height in elev_step_m steps; 255 is the sea */
  elev: Uint8Array;
  /** frames x cells, in depth_step_m steps */
  depth: Uint8Array;
}

export const SEA = 255;

export function decodeTwin(meta: WaterMeta, buf: ArrayBuffer): Twin {
  const n = meta.ny * meta.nx;
  const bytes = new Uint8Array(buf);
  if (bytes.length !== n * (1 + meta.frames)) {
    throw new Error(`water file is ${bytes.length} bytes, expected ${n * (1 + meta.frames)}`);
  }
  return { meta, elev: bytes.subarray(0, n), depth: bytes.subarray(n) };
}

/** Depth in metres in every cell at `minute`, linear between frames, written into `out`. */
export function depthsAt(t: Twin, minute: number, out: Float32Array): Float32Array {
  const { frames, every_min, depth_step_m, ny, nx } = t.meta;
  const n = ny * nx;
  const f = Math.min(Math.max(minute / every_min, 0), frames - 1);
  const a = Math.floor(f);
  const b = Math.min(a + 1, frames - 1);
  const w = f - a;
  const ao = a * n;
  const bo = b * n;
  for (let k = 0; k < n; k++) out[k] = (t.depth[ao + k] * (1 - w) + t.depth[bo + k] * w) * depth_step_m;
  return out;
}

/** Scene coordinates (x east, z south) with the grid centred on the origin, one unit per cell. */
export function toScene(meta: WaterMeta, lat: number, lng: number): [number, number] {
  return [(lng - meta.west) / meta.dlng - meta.nx / 2, (meta.north - lat) / meta.dlat - meta.ny / 2];
}

export type Vec3 = [number, number, number];

export interface Beat {
  /** where this beat starts, as a share of the story's scroll */
  at: number;
  /** replay minute shown when the beat starts */
  minute: number;
  eye: Vec3;
  look: Vec3;
}

/**
 * The story the scroll tells. Minutes are from 6 pm IST, 1 December 2015; scene units are 400 m.
 * Beats ease into each other, so a slow scroll reads as one continuous camera move.
 */
export const BEATS: Beat[] = [
  { at: 0, minute: 0, eye: [20, 62, 80], look: [6, 0, -2] }, // 6 pm: the city, the coast on the right
  { at: 0.2, minute: 90, eye: [-4, 30, 46], look: [6, 0, 2] }, // the gates open: along the Adyar
  { at: 0.45, minute: 300, eye: [40, 26, 52], look: [16, 0, 16] }, // late that night: the southern marshes fill
  { at: 0.7, minute: 480, eye: [10, 17, 34], look: [-9, 0, 9] }, // 2 am: the clocks along the Adyar near Ramapuram
  { at: 0.9, minute: 1500, eye: [6, 88, 52], look: [6, 0, 0] }, // evening: the whole fleet from above
  { at: 1, minute: 2160, eye: [6, 92, 54], look: [6, 0, 0] },
];

const smooth = (x: number) => x * x * (3 - 2 * x);
const mix = (a: number, b: number, w: number) => a + (b - a) * w;
const mix3 = (a: Vec3, b: Vec3, w: number): Vec3 => [mix(a[0], b[0], w), mix(a[1], b[1], w), mix(a[2], b[2], w)];

export interface StoryFrame {
  minute: number;
  beat: number;
  eye: Vec3;
  look: Vec3;
}

export function storyAt(progress: number, beats: Beat[] = BEATS): StoryFrame {
  const p = Math.min(Math.max(progress, 0), 1);
  let k = 0;
  while (k < beats.length - 2 && p >= beats[k + 1].at) k++;
  const a = beats[k];
  const b = beats[k + 1];
  const w = (p - a.at) / Math.max(1e-9, b.at - a.at);
  const e = smooth(Math.min(1, Math.max(0, w)));
  return { minute: mix(a.minute, b.minute, w), beat: k, eye: mix3(a.eye, b.eye, e), look: mix3(a.look, b.look, e) };
}
