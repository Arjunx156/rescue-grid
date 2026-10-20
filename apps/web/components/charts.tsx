"use client";

import { useEffect, useRef, useState } from "react";
import { clock, cn } from "@/lib/format";

/**
 * Charts follow the dataviz rules: categorical slots in fixed order (validated on the dark
 * surface), 2px lines, hairline grid, legend plus direct end labels, a crosshair tooltip
 * that lists every series, and a table view so no value hides behind hover.
 */
export const SERIES_DARK = ["#3987e5", "#d95926", "#199e70"];

interface Series {
  key: string;
  label: string;
  color: string;
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function niceMax(v: number): number {
  if (v <= 5) return 5;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / (p / 2)) * (p / 2);
}

function readHour(row: Record<string, number | string> | undefined, series: Series[], xKey: string): string {
  if (!row) return "";
  return `${clock(String(row[xKey]))}: ${series.map((s) => `${row[s.key]} ${s.label}`).join(", ")}`;
}

export function LineChart({
  title,
  rows,
  series,
  xKey,
  height = 240,
}: {
  title: string;
  rows: Record<string, number | string>[];
  series: Series[];
  xKey: string;
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const pad = { t: 12, r: 96, b: 26, l: 36 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;
  const max = niceMax(Math.max(1, ...rows.flatMap((r) => series.map((s) => Number(r[s.key]) || 0))));
  const x = (i: number) => pad.l + (rows.length <= 1 ? w / 2 : (i / (rows.length - 1)) * w);
  const y = (v: number) => pad.t + h - (v / max) * h;
  const ticks = [0, max / 2, max];
  const paths = series.map((s) => ({
    s,
    d: rows.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(Number(r[s.key]) || 0).toFixed(1)}`).join(""),
  }));
  const labelEvery = Math.max(1, Math.ceil(rows.length / Math.max(2, Math.floor(w / 70))));
  const last = rows.length - 1;
  // end labels: nudge apart only when they would overlap, with a leader line
  const ends = series
    .map((s) => ({ s, v: Number(rows[last]?.[s.key]) || 0 }))
    .sort((a, b) => b.v - a.v)
    .reduce<{ s: Series; v: number; ly: number }[]>((acc, e) => {
      const want = y(e.v);
      const prev = acc[acc.length - 1];
      acc.push({ ...e, ly: prev && want - prev.ly < 14 ? prev.ly + 14 : want });
      return acc;
    }, []);
  // labels pushed below the plot slide back up as a group
  const overflow = ends.length ? ends[ends.length - 1].ly - (pad.t + h - 4) : 0;
  if (overflow > 0) for (const e of ends) e.ly -= overflow;

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - box.left) / box.width;
    setHover(Math.max(0, Math.min(last, Math.round(rel * last))));
  };

  return (
    <figure className="rounded-xl border border-line bg-panel p-4">
      <figcaption className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="text-[14px] font-semibold">{title}</span>
        <span className="flex items-center gap-3 text-xs text-muted">
          {series.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <svg width="14" height="4" aria-hidden="true">
                <line x1="0" y1="2" x2="14" y2="2" stroke={s.color} strokeWidth="2" strokeLinecap="round" />
              </svg>
              {s.label}
            </span>
          ))}
        </span>
        <button
          type="button"
          onClick={() => setTable((t) => !t)}
          className="ml-auto text-xs text-accent-text hover:underline"
        >
          {table ? "Show chart" : "Show as table"}
        </button>
      </figcaption>
      {rows.length === 0 ? (
        <p className="py-16 text-center text-[13px] text-muted">No reports yet.</p>
      ) : table ? (
        <div className="max-h-72 overflow-auto scroll-thin">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-panel text-muted">
              <tr>
                <th className="py-1 pr-4 font-medium">Hour (IST)</th>
                {series.map((s) => (
                  <th key={s.key} className="py-1 pr-4 text-right font-medium">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tnum">
              {rows.map((r) => (
                <tr key={String(r[xKey])} className="border-t border-line">
                  <td className="py-1 pr-4">{clock(String(r[xKey]))}</td>
                  {series.map((s) => (
                    <td key={s.key} className="py-1 pr-4 text-right">
                      {r[s.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} className="relative">
          <svg
            width={width}
            height={height}
            role="img"
            aria-label={`${title}: ${series.map((s) => s.label).join(", ")} per hour`}
          >
            {ticks.map((t) => (
              <g key={t}>
                <line x1={pad.l} x2={pad.l + w} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth="1" />
                <text
                  x={pad.l - 8}
                  y={y(t)}
                  dy="0.32em"
                  textAnchor="end"
                  className="fill-[var(--faint)] text-[10px] tnum"
                >
                  {Math.round(t)}
                </text>
              </g>
            ))}
            {rows.map((r, i) =>
              i % labelEvery === 0 ? (
                <text
                  key={String(r[xKey])}
                  x={x(i)}
                  y={height - 6}
                  textAnchor="middle"
                  className="fill-[var(--faint)] text-[10px] tnum"
                >
                  {clock(String(r[xKey]))}
                </text>
              ) : null,
            )}
            {paths.map(({ s, d }) => (
              <path
                key={s.key}
                d={d}
                fill="none"
                stroke={s.color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            ))}
            {ends.map((e) => (
              <g key={e.s.key}>
                <circle cx={x(last)} cy={y(e.v)} r="4" fill={e.s.color} stroke="var(--panel)" strokeWidth="2" />
                {Math.abs(e.ly - y(e.v)) > 1 ? (
                  <line x1={x(last) + 5} y1={y(e.v)} x2={x(last) + 10} y2={e.ly} stroke="var(--faint)" />
                ) : null}
                <text x={x(last) + 12} y={e.ly} dy="0.32em" className="fill-[var(--muted)] text-[11px]">
                  {e.s.label} <tspan className="fill-[var(--text)] tnum">{e.v}</tspan>
                </text>
              </g>
            ))}
            {hover != null ? (
              <g pointerEvents="none">
                <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + h} stroke="var(--line-strong)" />
                {series.map((s) => (
                  <circle
                    key={s.key}
                    cx={x(hover)}
                    cy={y(Number(rows[hover][s.key]) || 0)}
                    r="4"
                    fill={s.color}
                    stroke="var(--panel)"
                    strokeWidth="2"
                  />
                ))}
              </g>
            ) : null}
          </svg>
          {/* the svg is one image to a screen reader, so the hour scrubber sits on top as its own control */}
          <div
            role="slider"
            tabIndex={0}
            aria-label="Hour"
            aria-valuemin={0}
            aria-valuemax={last}
            aria-valuenow={hover ?? last}
            aria-valuetext={readHour(rows[hover ?? last], series, xKey)}
            className="absolute rounded-sm"
            style={{ left: pad.l, top: pad.t, width: w, height: h }}
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
            onFocus={() => setHover(last)}
            onBlur={() => setHover(null)}
            onKeyDown={(e) => {
              const step: Record<string, (v: number) => number> = {
                ArrowLeft: (v) => v - 1,
                ArrowRight: (v) => v + 1,
                Home: () => 0,
                End: () => last,
              };
              const move = step[e.key];
              if (!move) return;
              e.preventDefault();
              setHover((v) => Math.max(0, Math.min(last, move(v ?? last))));
            }}
          />
          {hover != null ? (
            <div
              className="pointer-events-none absolute top-2 z-10 min-w-36 rounded-md border border-line bg-raised px-2.5 py-2 text-xs shadow-float"
              style={{ left: Math.min(x(hover) + 12, width - 160) }}
            >
              <div className="mb-1 text-muted tnum">{clock(String(rows[hover][xKey]))}</div>
              {series.map((s) => (
                <div key={s.key} className="flex items-center gap-2">
                  <svg width="10" height="4" aria-hidden="true">
                    <line x1="0" y1="2" x2="10" y2="2" stroke={s.color} strokeWidth="2" />
                  </svg>
                  <span className="font-semibold text-text tnum">{rows[hover][s.key]}</span>
                  <span className="text-muted">{s.label}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </figure>
  );
}

/** Horizontal bars for a breakdown: one hue unless the categories carry their own meaning. */
export function BarList({
  title,
  items,
  color = SERIES_DARK[0],
  footnote,
}: {
  title: string;
  items: {
    label: React.ReactNode;
    key: string;
    value: number;
    color?: string;
  }[];
  color?: string;
  footnote?: React.ReactNode;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  const [hover, setHover] = useState<string | null>(null);
  return (
    <figure className="rounded-xl border border-line bg-panel p-4" aria-label={title}>
      <figcaption className="mb-3 text-[14px] font-semibold">{title}</figcaption>
      {items.length === 0 ? (
        <p className="py-8 text-center text-[13px] text-muted">Nothing yet.</p>
      ) : (
        <ul className="space-y-2.5">
          {items.map((i) => (
            <li
              key={i.key}
              className="grid grid-cols-[8.5rem_1fr_3rem] items-center gap-3 text-[13px]"
              onPointerEnter={() => setHover(i.key)}
              onPointerLeave={() => setHover(null)}
            >
              <span className="truncate text-muted">{i.label}</span>
              <span className="relative h-3" title={`${i.value}`}>
                <span
                  className={cn(
                    "absolute inset-y-0 left-0 rounded-r-[4px] transition-[filter]",
                    hover === i.key && "brightness-125",
                  )}
                  style={{
                    width: `${Math.max(1.5, (i.value / max) * 100)}%`,
                    background: i.color ?? color,
                  }}
                />
              </span>
              <span className="text-right text-text tnum">{i.value.toLocaleString("en-IN")}</span>
            </li>
          ))}
        </ul>
      )}
      {footnote ? <p className="mt-3 text-xs text-muted">{footnote}</p> : null}
    </figure>
  );
}
