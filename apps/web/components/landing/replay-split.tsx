"use client";

import { Pause, Play, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { clock } from "@/lib/format";

type Coords = number[] | number[][] | number[][][] | number[][][][];
interface Policy {
  label: string;
  rescued: (number | null)[];
  tracks: Record<string, number[][]>;
  metrics: Record<string, number | null>;
}
interface Replay {
  name: string;
  starts_at: string;
  duration: number;
  bounds: [number, number, number, number];
  houses: [number, number, number, number, number][]; // lat, lng, critical, first minute, people
  policies: { rescue_grid: Policy; fcfs: Policy };
  geo: { flood: Coords[]; rivers: Coords[]; lakes: Coords[] };
}

const PLAY_SECONDS = 42; // the whole 60 hours, one long breath
const C = {
  bg: "#0b0f14",
  flood: "rgba(34,211,238,0.10)",
  river: "rgba(34,211,238,0.45)",
  wait: "#64748b",
  crit: "#ef4444",
  done: "#22c55e",
  team: "#3b82f6",
};

function useReplay() {
  const [data, setData] = useState<Replay | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    fetch("/replay/chennai-2015.json")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setFailed(true));
  }, []);
  return { data, failed };
}

function project(bounds: Replay["bounds"], w: number, h: number) {
  const [x1, y1, x2, y2] = bounds;
  const kx = Math.cos((((y1 + y2) / 2) * Math.PI) / 180);
  const scale = Math.min(w / ((x2 - x1) * kx), h / (y2 - y1));
  const ox = (w - (x2 - x1) * kx * scale) / 2;
  const oy = (h - (y2 - y1) * scale) / 2;
  return (lng: number, lat: number): [number, number] => [ox + (lng - x1) * kx * scale, oy + (y2 - lat) * scale];
}

function drawGeo(ctx: CanvasRenderingContext2D, data: Replay, p: ReturnType<typeof project>) {
  const ring = (r: number[][]) => {
    r.forEach(([lng, lat], i) => {
      const [x, y] = p(lng, lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
  };
  const polygons = (c: Coords) => {
    const depth = (a: unknown): number => (Array.isArray(a) ? 1 + depth(a[0]) : 0);
    const d = depth(c);
    const polys = (d === 4 ? c : [c]) as number[][][][];
    for (const poly of polys) for (const r of poly) ring(r);
  };
  ctx.fillStyle = C.flood;
  ctx.beginPath();
  for (const f of data.geo.flood) polygons(f);
  ctx.fill("evenodd");
  ctx.fillStyle = "rgba(34,211,238,0.16)";
  ctx.beginPath();
  for (const l of data.geo.lakes) polygons(l);
  ctx.fill();
  ctx.strokeStyle = C.river;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const r of data.geo.rivers) ring(r as number[][]);
  ctx.stroke();
}

/** Team position at minute t: on a segment, interpolate; between segments, rest at the last end. */
function teamAt(segs: number[][], t: number): [number, number] | null {
  if (!segs.length) return null;
  let last: number[] | null = null;
  for (const s of segs) {
    if (t < s[0]) break;
    if (t <= s[1]) {
      const f = s[1] > s[0] ? (t - s[0]) / (s[1] - s[0]) : 1;
      return [s[2] + (s[4] - s[2]) * f, s[3] + (s[5] - s[3]) * f];
    }
    last = s;
  }
  return last ? [last[4], last[5]] : [segs[0][2], segs[0][3]];
}

function Panel({ data, policy, t, highlight }: { data: Replay; policy: Policy; t: number; highlight: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const base = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState({ w: 600, h: 420 });
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => {
      const w = Math.floor(e.contentRect.width);
      setSize({ w, h: w });
    });
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  // the geography never changes: draw it once per size into an offscreen canvas
  useEffect(() => {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const off = document.createElement("canvas");
    off.width = size.w * dpr;
    off.height = size.h * dpr;
    const ctx = off.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, size.w, size.h);
    drawGeo(ctx, data, project(data.bounds, size.w, size.h));
    base.current = off;
  }, [data, size]);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx || !base.current) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (el.width !== size.w * dpr) {
      el.width = size.w * dpr;
      el.height = size.h * dpr;
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(base.current, 0, 0);
    ctx.scale(dpr, dpr);
    const p = project(data.bounds, size.w, size.h);
    const r = Math.max(1.6, size.w / 330);
    // waiting families first, rescued over them, critical waiting on top
    const layers: [number, number, string, number][] = [];
    data.houses.forEach(([lat, lng, crit, first], i) => {
      if (first > t) return;
      const done = policy.rescued[i];
      const rescued = done != null && done <= t;
      const [x, y] = p(lng, lat);
      if (rescued) layers.push([x, y, C.done, 1]);
      else layers.push([x, y, crit ? C.crit : C.wait, crit ? 2 : 0]);
    });
    layers.sort((a, b) => a[3] - b[3]);
    for (const [x, y, color, z] of layers) {
      ctx.fillStyle = color;
      ctx.globalAlpha = z === 0 ? 0.75 : 1;
      ctx.beginPath();
      ctx.arc(x, y, z === 2 ? r * 1.35 : r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = C.team;
    ctx.strokeStyle = C.bg;
    ctx.lineWidth = 1.5;
    for (const segs of Object.values(policy.tracks)) {
      const at = teamAt(segs, t);
      if (!at) continue;
      const [x, y] = p(at[1], at[0]);
      ctx.beginPath();
      ctx.moveTo(x, y - r * 2.4);
      ctx.lineTo(x + r * 1.7, y + r * 1.6);
      ctx.lineTo(x - r * 1.7, y + r * 1.6);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
  }, [data, policy, t, size]);

  const crit = data.houses.reduce((n, h) => n + h[2], 0);
  const reached = data.houses.reduce((n, h, i) => {
    const done = policy.rescued[i];
    return n + (h[2] && done != null && done <= t && done - h[3] <= 180 ? 1 : 0);
  }, 0);
  const people = data.houses.reduce((n, h, i) => {
    const done = policy.rescued[i];
    return n + (done != null && done <= t ? h[4] : 0);
  }, 0);

  return (
    <figure className="min-w-0">
      <div
        ref={wrap}
        className={`overflow-hidden rounded-xl border ${highlight ? "border-[#2a3647]" : "border-[#1f2937]"}`}
      >
        <canvas
          ref={canvas}
          style={{ width: size.w, height: size.h, display: "block" }}
          role="img"
          aria-label={`${policy.label}: ${reached} of ${crit} critical families reached within three hours so far`}
        />
      </div>
      <figcaption className="mt-4 flex items-end justify-between gap-4">
        <div>
          <p className="text-[15px] font-medium text-[#e5e7eb]">{policy.label}</p>
          <p className="text-[13px] text-[#9ca3af] tnum">{people.toLocaleString("en-IN")} people rescued</p>
        </div>
        <div className="text-right">
          <p className="text-[40px] leading-none font-semibold text-[#e5e7eb] tnum">
            {reached}
            <span className="text-[18px] text-muted"> / {crit}</span>
          </p>
          <p className="mt-1 text-[12px] text-[#9ca3af]">critical families reached within 3 h</p>
        </div>
      </figcaption>
    </figure>
  );
}

export function ReplaySplit() {
  const { data, failed } = useReplay();
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const duration = data?.duration ?? 1;

  // start when it scrolls into view; under reduced motion, show where it ends
  useEffect(() => {
    if (!data || !root.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setT(duration);
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting && !started.current) {
          started.current = true;
          setPlaying(true);
        }
      },
      { threshold: 0.35 },
    );
    io.observe(root.current);
    return () => io.disconnect();
  }, [data, duration]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setT((v) => {
        const next = v + (dt / PLAY_SECONDS) * duration;
        if (next >= duration) {
          setPlaying(false);
          return duration;
        }
        return next;
      });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [playing, duration]);

  const toggle = useCallback(() => {
    if (t >= duration) setT(0);
    setPlaying((p) => !p);
  }, [t, duration]);

  const when = useMemo(() => (data ? new Date(new Date(data.starts_at).getTime() + t * 60_000) : null), [data, t]);
  const day = when
    ? when.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        timeZone: "Asia/Kolkata",
      })
    : "";

  if (failed) {
    return (
      <p className="text-[15px] text-[#9ca3af]">
        The replay could not load. The numbers below come from the same simulation.
      </p>
    );
  }
  if (!data) {
    return (
      <div className="grid gap-6 md:grid-cols-2" aria-busy>
        {[0, 1].map((i) => (
          <div key={i} className="aspect-square rounded-xl border border-[#1f2937] bg-[#0b0f14]" />
        ))}
      </div>
    );
  }
  return (
    <div ref={root}>
      <div className="grid gap-8 md:grid-cols-2">
        <Panel data={data} policy={data.policies.rescue_grid} t={t} highlight />
        <Panel data={data} policy={data.policies.fcfs} t={t} highlight={false} />
      </div>
      <div className="mt-8 flex items-center gap-4">
        <button
          type="button"
          onClick={toggle}
          aria-label={playing ? "Pause replay" : t >= duration ? "Replay again" : "Play replay"}
          className="grid size-11 shrink-0 place-items-center rounded-full border border-[#2a3647] text-[#e5e7eb] hover:bg-[#121821]"
        >
          {playing ? (
            <Pause className="size-4" />
          ) : t >= duration ? (
            <RotateCcw className="size-4" />
          ) : (
            <Play className="size-4 translate-x-px" />
          )}
        </button>
        <input
          type="range"
          min={0}
          max={duration}
          step={1}
          value={t}
          onChange={(e) => {
            setPlaying(false);
            setT(Number(e.target.value));
          }}
          aria-label="Replay time"
          aria-valuetext={`${day} ${clock(when)}`}
          className="h-1 flex-1 cursor-pointer accent-[#3b82f6]"
        />
        <span className="w-28 shrink-0 text-right font-mono text-[13px] text-[#9ca3af] tnum">
          {day} {clock(when)}
        </span>
      </div>
      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-[#9ca3af]">
        {[
          [C.crit, "Critical, waiting"],
          [C.wait, "Others, waiting"],
          [C.done, "Reached by a team"],
        ].map(([c, l]) => (
          <span key={l} className="inline-flex items-center gap-2">
            <span className="size-2.5 rounded-full" style={{ background: c }} aria-hidden />
            {l}
          </span>
        ))}
        <span className="inline-flex items-center gap-2">
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M5 0 9 9H1Z" fill={C.team} />
          </svg>
          Rescue team
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-4 rounded-sm" style={{ background: "rgba(34,211,238,0.25)" }} aria-hidden />
          Modelled flood extent
        </span>
      </div>
    </div>
  );
}
