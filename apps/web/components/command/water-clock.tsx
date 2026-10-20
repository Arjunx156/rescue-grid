"use client";

import { Waves } from "lucide-react";
import { useId, useMemo, useState } from "react";
import type { CaseOut } from "@/lib/api";
import { clock, cn } from "@/lib/format";
import { clockLeft, clockText, depthsAt, type WaterField } from "@/lib/water";

const W = 340;
const H = 132;
const PAD = { l: 30, r: 10, t: 12, b: 20 };

/**
 * One family's water clock: how long until the water reaches their danger line, the likely and
 * worst-case depth over the next three hours, and where the assigned team's arrival falls on it.
 */
export function WaterClock({
  c,
  field,
  now,
  eta,
  team,
}: {
  c: CaseOut;
  field: WaterField | null;
  now: number;
  eta?: string | null;
  team?: string | null;
}) {
  const clk = c.water_clock;
  const left = clockLeft(clk, now);
  const series = useMemo(
    () => (field && c.lat != null && c.lng != null ? depthsAt(field, c.lat, c.lng) : null),
    [field, c.lat, c.lng],
  );
  if (!clk) return null;

  const due = clk.minutes != null ? new Date(clk.issued_at).getTime() + clk.minutes * 60_000 : null;
  const etaMs = eta ? new Date(eta).getTime() : null;
  const margin = due != null && etaMs != null ? Math.round((due - etaMs) / 60_000) : null;
  const elapsed = (now - new Date(clk.issued_at).getTime()) / 60_000;
  const range =
    clk.early != null && left != null
      ? `between ${clockText(Math.max(0, clk.early - elapsed))} and ${
          clk.late != null ? clockText(Math.max(0, clk.late - elapsed)) : "beyond three hours"
        }`
      : null;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <Waves className="size-4 shrink-0 self-center text-water" aria-hidden="true" />
        {left != null ? (
          <p className="text-[13px] text-muted">
            <span className={cn("text-[22px] font-semibold tnum", left < 60 ? "text-critical" : "text-text")}>
              {clockText(left)}
            </span>{" "}
            until {clk.danger_label.toLowerCase()} ({clk.danger_m.toFixed(1)} m)
          </p>
        ) : (
          <p className="text-[13px] text-muted">
            The forecast does not see the water reaching {clk.danger_label.toLowerCase()} in the next three hours.
          </p>
        )}
      </div>
      <p className="text-xs text-muted">
        {range ? `Likely ${range}. ` : ""}About {clk.depth_m.toFixed(1)} m here now,{" "}
        {clk.rise_cm_h >= 1
          ? `rising ${Math.round(clk.rise_cm_h)} cm an hour.`
          : clk.rise_cm_h <= -1
            ? `falling ${Math.round(-clk.rise_cm_h)} cm an hour.`
            : "holding steady."}
      </p>
      {series ? (
        <Chart
          minutes={series.minutes}
          likely={series.likely}
          worst={series.worst}
          danger={clk.danger_m}
          issuedAt={field?.issuedAt ?? new Date(clk.issued_at).getTime()}
          nowMs={now}
          etaMs={etaMs}
          team={team}
        />
      ) : null}
      {margin != null ? (
        <p className={cn("text-xs font-medium", margin >= 0 ? "text-go" : "text-critical")}>
          {margin >= 0
            ? `${team ?? "The team"} should arrive ${clockText(margin)} before the water.`
            : `${team ?? "The team"} is due ${clockText(-margin)} after the water. Is anyone closer?`}
        </p>
      ) : null}
    </div>
  );
}

function Chart({
  minutes,
  likely,
  worst,
  danger,
  issuedAt,
  nowMs,
  etaMs,
  team,
}: {
  minutes: number[];
  likely: number[];
  worst: number[];
  danger: number;
  issuedAt: number;
  nowMs: number;
  etaMs: number | null;
  team?: string | null;
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const span = minutes[minutes.length - 1] || 180;
  const top = Math.max(danger * 1.15, ...worst, 0.5);
  const x = (m: number) => PAD.l + (Math.min(Math.max(m, 0), span) / span) * (W - PAD.l - PAD.r);
  const y = (d: number) => H - PAD.b - (Math.min(d, top) / top) * (H - PAD.t - PAD.b);
  const line = likely.map((d, i) => `${i ? "L" : "M"}${x(minutes[i]).toFixed(1)},${y(d).toFixed(1)}`).join("");
  const band = `${worst.map((d, i) => `${i ? "L" : "M"}${x(minutes[i]).toFixed(1)},${y(d).toFixed(1)}`).join("")}${likely
    .map((_, i) => {
      const k = likely.length - 1 - i;
      return `L${x(minutes[k]).toFixed(1)},${y(likely[k]).toFixed(1)}`;
    })
    .join("")}Z`;
  const nowAt = (nowMs - issuedAt) / 60_000;
  const etaAt = etaMs != null ? (etaMs - issuedAt) / 60_000 : null;
  const ticks = [0, 60, 120, 180].filter((t) => t <= span);
  const yTicks = [0, Math.round(top * 0.5 * 10) / 10, Math.round(top * 10) / 10];
  const summary = `Likely depth ${likely[0].toFixed(1)} metres now, ${likely[likely.length - 1].toFixed(1)} in three hours; worst case ${worst[worst.length - 1].toFixed(1)}. Danger line ${danger.toFixed(1)} metres.`;

  return (
    <figure className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full overflow-visible"
        role="img"
        aria-labelledby={`${id}-t`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const m = (((e.clientX - r.left) / r.width) * W - PAD.l) / (W - PAD.l - PAD.r);
          setHover(Math.min(minutes.length - 1, Math.max(0, Math.round(m * (minutes.length - 1)))));
        }}
      >
        <title id={`${id}-t`}>{summary}</title>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
            <text x={PAD.l - 6} y={y(t) + 3.5} textAnchor="end" className="fill-[var(--faint)] text-[10px] tnum">
              {t}
            </text>
          </g>
        ))}
        {ticks.map((t) => (
          <text key={t} x={x(t)} y={H - 5} textAnchor="middle" className="fill-[var(--faint)] text-[10px] tnum">
            {t ? `+${t / 60}h` : "issued"}
          </text>
        ))}
        <path d={band} fill="var(--water)" fillOpacity={0.14} />
        <path d={line} fill="none" stroke="var(--water)" strokeWidth={2} strokeLinejoin="round" />
        <line
          x1={PAD.l}
          x2={W - PAD.r}
          y1={y(danger)}
          y2={y(danger)}
          stroke="var(--critical)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
        <text x={W - PAD.r} y={y(danger) - 4} textAnchor="end" className="fill-[var(--muted)] text-[10px]">
          danger line
        </text>
        {nowAt >= 0 && nowAt <= span ? (
          <line x1={x(nowAt)} x2={x(nowAt)} y1={PAD.t} y2={H - PAD.b} stroke="var(--muted)" strokeWidth={1} />
        ) : null}
        {etaAt != null && etaAt >= 0 && etaAt <= span ? (
          <g>
            <line x1={x(etaAt)} x2={x(etaAt)} y1={PAD.t} y2={H - PAD.b} stroke="var(--accent-text)" strokeWidth={1.5} />
            <text x={x(etaAt) + 4} y={PAD.t + 8} className="fill-[var(--muted)] text-[10px]">
              {team ?? "team"} arrives
            </text>
          </g>
        ) : null}
        {hover != null ? (
          <g>
            <line
              x1={x(minutes[hover])}
              x2={x(minutes[hover])}
              y1={PAD.t}
              y2={H - PAD.b}
              stroke="var(--line-strong)"
              strokeWidth={1}
            />
            <circle
              cx={x(minutes[hover])}
              cy={y(likely[hover])}
              r={4}
              fill="var(--water)"
              stroke="var(--raised)"
              strokeWidth={2}
            />
          </g>
        ) : null}
        <rect x={PAD.l} y={0} width={W - PAD.l - PAD.r} height={H} fill="transparent" />
      </svg>
      {hover != null ? (
        <div
          className="pointer-events-none absolute top-0 rounded-md border border-line bg-raised px-2 py-1 text-[11px] text-muted shadow-float tnum"
          style={{ left: `${(x(minutes[hover]) / W) * 100}%`, transform: "translateX(-50%) translateY(-110%)" }}
        >
          <span className="text-text">{clock(new Date(issuedAt + minutes[hover] * 60_000))}</span> · likely{" "}
          {likely[hover].toFixed(1)} m · worst {worst[hover].toFixed(1)} m
        </div>
      ) : null}
      <figcaption className="mt-1 flex items-center gap-4 text-[11px] text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-water" aria-hidden="true" />
          Likely depth (m)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-4 rounded-sm bg-water/20" aria-hidden="true" />
          up to the worst case
        </span>
      </figcaption>
    </figure>
  );
}
