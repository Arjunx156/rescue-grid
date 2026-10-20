"use client";

import { type RefObject, useEffect, useRef, useState } from "react";
import {
  AmbientLight,
  BoxGeometry,
  BufferGeometry,
  Color,
  CylinderGeometry,
  DirectionalLight,
  DynamicDrawUsage,
  Float32BufferAttribute,
  Fog,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  Object3D,
  PerspectiveCamera,
  PlaneGeometry,
  RingGeometry,
  Scene,
  WebGLRenderer,
} from "three";
import { decodeTwin, depthsAt, SEA, storyAt, type Twin, toScene, type WaterMeta } from "@/lib/twin";

type House = [number, number, number, number, number, number | null]; // lat, lng, critical, first, people, danger
interface Replay {
  starts_at: string;
  houses: House[];
  water: WaterMeta;
  policies: { rescue_grid: { rescued: (number | null)[]; tracks: Record<string, number[][]> } };
}

export interface TwinReadout {
  minute: number;
  floodedKm2: number;
  reported: number;
  atRisk: number;
  beforeWater: number;
}

const BG = 0x0b0f14;
const CELL_KM2 = 0.16;
const WATER_SCALE = 0.9; // metres of water -> scene units: exaggerated so a street's depth reads from the sky
const SHOWN = 0.5; // rain puddles everywhere would bury the story; show the water people call about
// the hero's loop: 11 pm to 10 am on the first night, in 26 seconds; handed to the scroll over the first 12%
const HERO_FROM = 300;
const HERO_TO = 960;
const HERO_SECONDS = 26;
const HANDOVER = 0.12;
const C = {
  ground: new Color(0x222c3b),
  groundHigh: new Color(0x3d4b60),
  shallow: new Color(0x0b4f61),
  deep: new Color(0x7ce9fb),
  waiting: new Color(0xf97316),
  critical: new Color(0xef4444),
  rescued: new Color(0x22c55e),
  boat: new Color(0x60a5fa),
};

function groundHeight(m: number) {
  return m <= 30 ? 0.15 + m * 0.05 : 1.65 + (m - 30) * 0.015;
}

/** Where a team is at a minute: on a segment, interpolate; between segments, rest at the last end. */
function teamAt(segs: number[][], t: number): [number, number] | null {
  let last: number[] | null = null;
  for (const s of segs) {
    if (t < s[0]) break;
    if (t <= s[1]) {
      const f = s[1] > s[0] ? (t - s[0]) / (s[1] - s[0]) : 1;
      return [s[2] + (s[4] - s[2]) * f, s[3] + (s[5] - s[3]) * f];
    }
    last = s;
  }
  return last ? [last[4], last[5]] : segs.length ? [segs[0][2], segs[0][3]] : null;
}

async function load(): Promise<{ replay: Replay; twin: Twin }> {
  const replay: Replay = await fetch("/replay/chennai-2015.json").then((r) =>
    r.ok ? r.json() : Promise.reject(new Error("replay")),
  );
  const buf = await fetch(replay.water.file).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error("water"))));
  return { replay, twin: decodeTwin(replay.water, buf) };
}

function build(canvas: HTMLCanvasElement, replay: Replay, twin: Twin) {
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.setClearColor(BG, 1);
  const scene = new Scene();
  scene.fog = new Fog(BG, 70, 190);
  const camera = new PerspectiveCamera(32, 1, 0.5, 600);
  scene.add(new AmbientLight(0xa9bfd8, 0.7));
  // the sea: one dark plane under the columns, so the coastline reads where the land stops
  const sea = new Mesh(new PlaneGeometry(400, 400), new MeshBasicMaterial({ color: 0x0c1824 }));
  sea.rotation.x = -Math.PI / 2;
  sea.position.y = 0.02;
  scene.add(sea);
  const sun = new DirectionalLight(0xffffff, 1.25);
  sun.position.set(-50, 70, -30);
  scene.add(sun);

  const { nx, ny, elev_step_m } = twin.meta;
  const land: number[] = [];
  for (let k = 0; k < nx * ny; k++) if (twin.elev[k] !== SEA) land.push(k);
  // grid cell -> its slot among the land columns, -1 for the sea
  const slot = new Int32Array(nx * ny).fill(-1);
  land.forEach((k, n) => {
    slot[k] = n;
  });
  const slotAt = (x: number, z: number) => {
    const i = Math.floor(z + ny / 2);
    const j = Math.floor(x + nx / 2);
    return i >= 0 && i < ny && j >= 0 && j < nx ? slot[i * nx + j] : -1;
  };
  const top = new Float32Array(land.length);
  const dummy = new Object3D();
  const color = new Color();

  // ground: one column per 400 m cell
  const box = new BoxGeometry(0.94, 1, 0.94);
  box.translate(0, 0.5, 0);
  const ground = new InstancedMesh(box, new MeshLambertMaterial(), land.length);
  land.forEach((k, n) => {
    const m = twin.elev[k] * elev_step_m;
    const h = groundHeight(m);
    top[n] = h;
    dummy.position.set((k % nx) - nx / 2 + 0.5, 0, Math.floor(k / nx) - ny / 2 + 0.5);
    dummy.scale.set(1, h, 1);
    dummy.updateMatrix();
    ground.setMatrixAt(n, dummy.matrix);
    ground.setColorAt(n, color.copy(C.ground).lerp(C.groundHigh, Math.min(1, m / 40)));
  });
  scene.add(ground);

  // water: a column standing on each wet cell, rewritten every frame
  const waterGeo = new BoxGeometry(0.96, 1, 0.96);
  waterGeo.translate(0, 0.5, 0);
  const water = new InstancedMesh(
    waterGeo,
    new MeshLambertMaterial({ transparent: true, opacity: 0.88, emissive: 0x0b3f4d }),
    land.length,
  );
  water.instanceMatrix.setUsage(DynamicDrawUsage);
  land.forEach((k, n) => {
    dummy.position.set((k % nx) - nx / 2 + 0.5, top[n], Math.floor(k / nx) - ny / 2 + 0.5);
    dummy.scale.set(1, 1, 1);
    dummy.updateMatrix();
    water.setMatrixAt(n, dummy.matrix);
    water.setColorAt(n, C.shallow);
  });
  water.frustumCulled = false;
  scene.add(water);

  // families: a beacon from their first SOS, green once a team reached them
  const houses = replay.houses;
  const rescued = replay.policies.rescue_grid.rescued;
  const pinGeo = new CylinderGeometry(0.11, 0.11, 1, 6);
  pinGeo.translate(0, 0.5, 0);
  const pins = new InstancedMesh(pinGeo, new MeshBasicMaterial(), houses.length);
  pins.instanceMatrix.setUsage(DynamicDrawUsage);
  pins.frustumCulled = false;
  const housePos = houses.map(([lat, lng]) => toScene(twin.meta, lat, lng));
  const houseCell = housePos.map(([x, z]) => slotAt(x, z));
  scene.add(pins);

  // the water clock: a ring that tightens as the water nears the family's danger line
  const ringGeo = new RingGeometry(0.72, 0.9, 40);
  ringGeo.rotateX(-Math.PI / 2);
  const rings = new InstancedMesh(
    ringGeo,
    new MeshBasicMaterial({ transparent: true, opacity: 0.9, depthWrite: false }),
    houses.length,
  );
  rings.instanceMatrix.setUsage(DynamicDrawUsage);
  rings.frustumCulled = false;
  scene.add(rings);

  // boats and the leg each one is on
  const tracks = Object.values(replay.policies.rescue_grid.tracks);
  const boatGeo = new BoxGeometry(0.55, 0.28, 0.55);
  const boats = new InstancedMesh(boatGeo, new MeshBasicMaterial({ color: C.boat }), tracks.length);
  boats.instanceMatrix.setUsage(DynamicDrawUsage);
  boats.frustumCulled = false;
  scene.add(boats);
  const legs = new Float32Array(tracks.length * 6);
  const legGeo = new BufferGeometry();
  legGeo.setAttribute("position", new Float32BufferAttribute(legs, 3).setUsage(DynamicDrawUsage));
  const legLines = new LineSegments(legGeo, new LineBasicMaterial({ color: C.boat, transparent: true, opacity: 0.45 }));
  legLines.frustumCulled = false;
  scene.add(legLines);

  const depths = new Float32Array(nx * ny);
  const matrix = new Matrix4();
  const hide = new Matrix4().makeScale(0, 0, 0);

  function waterTop(n: number, k: number) {
    return top[n] + (depths[k] >= SHOWN ? depths[k] * WATER_SCALE : 0);
  }

  function frame(progress: number, wall: number, animate: boolean): TwinReadout {
    const s = storyAt(progress);
    // the hero is alive: the first night loops slowly until the reader scrolls, then the scroll takes the clock
    const handover = Math.min(1, progress / HANDOVER);
    const loop = HERO_FROM + ((wall / 1000) % HERO_SECONDS) * ((HERO_TO - HERO_FROM) / HERO_SECONDS);
    const minute = animate ? loop + (s.minute - loop) * handover : s.minute;
    const drift = animate ? Math.sin(wall / 5200) * 2.2 : 0;
    camera.position.set(s.eye[0] + drift, s.eye[1], s.eye[2] - drift * 0.6);
    camera.lookAt(s.look[0], s.look[1], s.look[2]);

    depthsAt(twin, minute, depths);
    const wm = water.instanceMatrix.array as Float32Array;
    let wet = 0;
    for (let n = 0; n < land.length; n++) {
      const k = land[n];
      const d = depths[k];
      const o = n * 16;
      if (d < SHOWN) {
        wm[o] = 0;
        wm[o + 10] = 0;
        wm[o + 5] = 0;
        continue;
      }
      wet++;
      wm[o] = 1;
      wm[o + 10] = 1;
      wm[o + 5] = d * WATER_SCALE;
      water.setColorAt(n, color.copy(C.shallow).lerp(C.deep, Math.min(1, (d - SHOWN) / 2)));
    }
    water.instanceMatrix.needsUpdate = true;
    if (water.instanceColor) water.instanceColor.needsUpdate = true;

    let reported = 0;
    let atRisk = 0;
    let beforeWater = 0;
    const pulse = animate ? 0.5 + 0.5 * Math.sin(wall / 260) : 1;
    houses.forEach(([, , critical, first, , danger], h) => {
      const [x, z] = housePos[h];
      const n = houseCell[h];
      const base = n >= 0 ? waterTop(n, land[n]) : 0.2;
      const done = rescued[h];
      const safe = done != null && done <= minute;
      if (danger != null && danger <= minute) {
        atRisk++;
        if (done != null && done <= danger) beforeWater++;
      }
      if (first > minute) {
        pins.setMatrixAt(h, hide);
        rings.setMatrixAt(h, hide);
        return;
      }
      reported++;
      const grow = Math.min(1, (minute - first) / 25);
      const tall = safe ? 0.5 : critical ? 1.9 : 1.2;
      matrix.makeScale(1, tall * grow, 1).setPosition(x, base, z);
      pins.setMatrixAt(h, matrix);
      pins.setColorAt(h, safe ? C.rescued : critical ? C.critical : C.waiting);
      // a ring only while the water is on its way to this family and no team has reached them
      const left = danger != null ? danger - minute : null;
      if (!safe && left != null && left > 0 && left <= 240) {
        const r = 0.55 + 1.9 * (left / 240);
        matrix.makeScale(r, 1, r).setPosition(x, base + 0.05, z);
        rings.setMatrixAt(h, matrix);
        rings.setColorAt(h, left <= 60 ? color.copy(C.critical).multiplyScalar(0.6 + 0.4 * pulse) : C.waiting);
      } else {
        rings.setMatrixAt(h, hide);
      }
    });
    pins.instanceMatrix.needsUpdate = true;
    rings.instanceMatrix.needsUpdate = true;
    if (pins.instanceColor) pins.instanceColor.needsUpdate = true;
    if (rings.instanceColor) rings.instanceColor.needsUpdate = true;

    tracks.forEach((segs, b) => {
      const at = teamAt(segs, minute);
      if (!at) {
        boats.setMatrixAt(b, hide);
        return;
      }
      const [x, z] = toScene(twin.meta, at[0], at[1]);
      const n = slotAt(x, z);
      const y = (n >= 0 ? waterTop(n, land[n]) : 0.3) + 0.35;
      matrix.makeTranslation(x, y, z);
      boats.setMatrixAt(b, matrix);
      const leg = segs.find((sg) => minute >= sg[0] && minute <= sg[1]);
      if (leg) {
        const [x1, z1] = toScene(twin.meta, leg[2], leg[3]);
        const [x2, z2] = toScene(twin.meta, leg[4], leg[5]);
        legs.set([x1, y, z1, x2, y, z2], b * 6);
      } else {
        legs.fill(0, b * 6, b * 6 + 6);
      }
    });
    boats.instanceMatrix.needsUpdate = true;
    legGeo.attributes.position.needsUpdate = true;

    renderer.render(scene, camera);
    return { minute, floodedKm2: Math.round(wet * CELL_KM2), reported, atRisk, beforeWater };
  }

  function resize(w: number, h: number) {
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  }

  function dispose() {
    sea.geometry.dispose();
    (sea.material as MeshBasicMaterial).dispose();
    for (const o of [ground, water, pins, rings, boats]) {
      o.geometry.dispose();
      (o.material as MeshBasicMaterial).dispose();
    }
    legGeo.dispose();
    (legLines.material as LineBasicMaterial).dispose();
    renderer.dispose();
  }

  return { frame, resize, dispose };
}

/**
 * The 3D twin of the 2015 flood. Reads scroll progress from a ref, so the page never
 * re-renders per frame, and reports what it shows through `onReadout` a few times a second.
 */
export function FloodTwin({
  progress,
  reduced,
  onReadout,
  onFail,
}: {
  progress: RefObject<number>;
  reduced: boolean;
  onReadout: (r: TwinReadout) => void;
  onFail: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(true);
  const report = useRef(onReadout);
  report.current = onReadout;
  const fail = useRef(onFail);
  fail.current = onFail;

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const scene = useRef<ReturnType<typeof build> | null>(null);
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    let cancelled = false;
    let ro: ResizeObserver | null = null;
    load()
      .then(({ replay, twin }) => {
        if (cancelled) return;
        const s = build(el, replay, twin);
        scene.current = s;
        ro = new ResizeObserver(([e]) => {
          s.resize(Math.floor(e.contentRect.width), Math.floor(e.contentRect.height));
          if (reduced) report.current(s.frame(progress.current ?? 0, 0, false));
        });
        ro.observe(el);
      })
      .catch(() => fail.current());
    return () => {
      cancelled = true;
      ro?.disconnect();
      scene.current?.dispose();
      scene.current = null;
    };
  }, [progress, reduced]);

  useEffect(() => {
    if (!visible) return;
    let raf = 0;
    let lastReport = 0;
    let lastProgress = -1;
    const tick = (wall: number) => {
      const s = scene.current;
      const p = progress.current ?? 0;
      // with reduced motion, draw only when the reader scrolls
      if (s && (!reduced || p !== lastProgress)) {
        const r = s.frame(p, wall, !reduced);
        lastProgress = p;
        if (wall - lastReport > 120) {
          lastReport = wall;
          report.current(r);
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [visible, reduced, progress]);

  return (
    <canvas
      ref={canvas}
      className="block h-full w-full"
      role="img"
      aria-label="A 3D model of Chennai with the December 2015 flood rising as you scroll: rivers spilling over, families calling for help, boats reaching them"
    />
  );
}
