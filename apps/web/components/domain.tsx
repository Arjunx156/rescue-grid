"use client";

import { Accessibility, Baby, HeartPulse, MessagesSquare, TrendingUp, Users, Waves } from "lucide-react";
import type { ReactNode, SVGProps } from "react";
import type { CaseOut, Factor } from "@/lib/api";
import { cn, LEVEL_LABEL, levelColor, MEDICAL_LABEL, WATER_LABEL } from "@/lib/format";
import { Tip } from "./ui/overlay";

/** Level shape + word + colour: urgency is never colour alone. */
export function UrgencyPill({ level, score, size = "sm" }: { level: string; score?: number; size?: "sm" | "md" }) {
  const color = levelColor(level);
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border font-medium tnum",
        size === "sm" ? "h-[22px] px-2 text-xs" : "h-7 px-2.5 text-[13px]",
      )}
      style={{
        color,
        borderColor: `color-mix(in oklab, ${color} 45%, transparent)`,
        background: `color-mix(in oklab, ${color} 12%, transparent)`,
      }}
    >
      <LevelGlyph level={level} />
      {LEVEL_LABEL[level] ?? level}
      {score !== undefined ? <span className="tnum">{score}</span> : null}
    </span>
  );
}

/** Distinct shapes per level so a colour-blind dispatcher reads the same thing. */
export function LevelGlyph({ level, className }: { level: string; className?: string }) {
  const common = cn("size-2.5 shrink-0", className);
  if (level === "critical") {
    return (
      <span className={cn("relative inline-flex", common)} aria-hidden>
        <span className="absolute inset-0 rounded-full bg-current motion-safe:animate-ring" />
        <svg viewBox="0 0 10 10" className="relative size-full" fill="currentColor" aria-hidden="true">
          <path d="M5 0 10 9H0Z" />
        </svg>
      </span>
    );
  }
  if (level === "high") {
    return (
      <svg viewBox="0 0 10 10" className={common} fill="currentColor" aria-hidden="true">
        <path d="M5 0 10 5 5 10 0 5Z" />
      </svg>
    );
  }
  if (level === "medium") {
    return (
      <svg viewBox="0 0 10 10" className={common} fill="currentColor" aria-hidden="true">
        <rect x="1" y="1" width="8" height="8" rx="1" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 10 10" className={common} fill="currentColor" aria-hidden="true">
      <circle cx="5" cy="5" r="4" />
    </svg>
  );
}

function Glyph(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    />
  );
}

export const ElderlyIcon = (p: SVGProps<SVGSVGElement>) => (
  <Glyph {...p}>
    <circle cx="10" cy="4.5" r="2" />
    <path d="M10 7.5c-1.6 0-2.6 1.2-3 3l-1 5" />
    <path d="M10 7.5c1.2.4 2 1.6 2.2 3.2l.3 2.3" />
    <path d="m8.5 13-1 8M10.5 13l2 8" />
    <path d="M15 11.5c1.1 0 1.8.8 1.8 1.8V21" />
  </Glyph>
);

export const ChildIcon = (p: SVGProps<SVGSVGElement>) => (
  <Glyph {...p}>
    <circle cx="12" cy="7" r="2.5" />
    <path d="M8 13.5c1-2.2 2.3-3.5 4-3.5s3 1.3 4 3.5" />
    <path d="m10.5 13-1 7M13.5 13l1 7" />
  </Glyph>
);

export const PregnantIcon = (p: SVGProps<SVGSVGElement>) => (
  <Glyph {...p}>
    <circle cx="11" cy="4.5" r="2" />
    <path d="M11 7.5c-1.5.8-2 2.3-2 4.5l.5 2.5" />
    <path d="M11 7.5c1 1 1.4 2 1.6 3 2.4.4 3.6 2 3.4 3.8-.2 1.6-1.6 2.6-3.5 2.6H10" />
    <path d="m9.5 17.5-.5 3.5M12.5 18l.5 3" />
  </Glyph>
);

interface VulnSpec {
  key: string;
  icon: ReactNode;
  label: (n: number) => string;
}

const VULN: VulnSpec[] = [
  {
    key: "infant",
    icon: <Baby className="size-4" />,
    label: (n) => `${n} infant${n > 1 ? "s" : ""}`,
  },
  {
    key: "pregnant",
    icon: <PregnantIcon className="size-4" />,
    label: () => "Pregnant",
  },
  {
    key: "elderly",
    icon: <ElderlyIcon className="size-4" />,
    label: (n) => `${n} elderly`,
  },
  {
    key: "child",
    icon: <ChildIcon className="size-4" />,
    label: (n) => `${n} child${n > 1 ? "ren" : ""}`,
  },
  {
    key: "disabled",
    icon: <Accessibility className="size-4" />,
    label: (n) => `${n} disabled`,
  },
];

/** The people at risk as icons with tooltips; medical needs spelled out. */
export function VulnIcons({
  c,
  max = 6,
  showMedical = true,
}: {
  c: Pick<CaseOut, "vulnerability">;
  max?: number;
  showMedical?: boolean;
}) {
  const v = (c.vulnerability ?? {}) as Record<string, number | string[]>;
  const medical = (v.medical as string[] | undefined) ?? [];
  const items = VULN.filter((s) => Number(v[s.key] ?? 0) > 0).slice(0, max);
  if (!items.length && !medical.length) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-muted">
      {items.map((s) => (
        <Tip key={s.key} label={s.label(Number(v[s.key]))}>
          <span className="inline-flex items-center gap-0.5" role="img" aria-label={s.label(Number(v[s.key]))}>
            {s.icon}
            {Number(v[s.key]) > 1 ? <span className="text-[11px] tnum">{Number(v[s.key])}</span> : null}
          </span>
        </Tip>
      ))}
      {showMedical && medical.length ? (
        <Tip label={medical.map((m) => MEDICAL_LABEL[m] ?? m).join(", ")}>
          <span
            className="inline-flex items-center gap-1 text-critical"
            role="img"
            aria-label={`Medical: ${medical.join(", ")}`}
          >
            <HeartPulse className="size-4" />
            <span className="max-w-28 truncate text-[11px]">
              {medical.map((m) => MEDICAL_LABEL[m] ?? m).join(", ")}
            </span>
          </span>
        </Tip>
      ) : null}
    </span>
  );
}

export function PeopleCount({ n }: { n: number | null | undefined }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-text tnum"
      role="img"
      aria-label={n ? `${n} people` : "Headcount unknown"}
    >
      <Users className="size-3.5 text-muted" />
      {n ?? "?"}
    </span>
  );
}

export function WaterTag({ level, rising }: { level: string | null | undefined; rising?: boolean | null }) {
  if (!level || level === "unknown") return null;
  return (
    <span className="inline-flex items-center gap-1 text-water">
      <Waves className="size-3.5" />
      <span className="text-[12px]">{WATER_LABEL[level] ?? level}</span>
      {rising ? (
        <Tip label="Water still rising">
          <TrendingUp className="size-3.5 text-high" aria-label="rising" />
        </Tip>
      ) : null}
    </span>
  );
}

export function SourceCount({ n }: { n: number }) {
  if (n < 2) return null;
  return (
    <span
      className="inline-flex items-center gap-1 text-[12px] text-muted tnum"
      role="img"
      aria-label={`${n} reports merged`}
    >
      <MessagesSquare className="size-3.5" />
      {n}
    </span>
  );
}

/** How sure we are of the pin. Uncertain locations wear a dashed outline everywhere. */
export function Confidence({ value, source }: { value: number; source: string }) {
  const pct = Math.round(value * 100);
  const sure = value >= 0.6;
  const label =
    source === "manual"
      ? "Confirmed by coordinator"
      : source === "pin"
        ? "Shared location pin"
        : `${pct}% sure of location`;
  return (
    <Tip label={label}>
      <span
        className={cn(
          "inline-flex h-[22px] items-center gap-1 rounded-full border px-2 text-[11px] tnum",
          sure ? "border-line-strong text-muted" : "border-dashed border-medium text-medium",
        )}
      >
        {sure ? null : <span aria-hidden>?</span>}
        {source === "manual" ? "Pinned" : source === "pin" ? "GPS" : `${pct}%`}
      </span>
    </Tip>
  );
}

const FACTOR_COLOR: Record<string, string> = {
  water: "#22d3ee",
  rising: "#38bdf8",
  medical: "#f87171",
  vulnerable: "#fb923c",
  rescue: "#60a5fa",
  headcount: "#a78bfa",
  waiting: "#facc15",
  flood_zone: "#2dd4bf",
  reports: "#94a3b8",
};

/** Every point of the urgency score, as a bar and a list a coordinator can check. */
export function ScoreBreakdown({ factors, score }: { factors: Factor[]; score: number }) {
  const positive = factors.filter((f) => f.points > 0);
  const total = Math.max(
    100,
    positive.reduce((a, f) => a + f.points, 0),
  );
  return (
    <div className="space-y-3">
      <div className="flex h-2 overflow-hidden rounded-full bg-panel-2" role="img" aria-label={`Score ${score} of 100`}>
        {positive.map((f) => (
          <span
            key={f.key}
            style={{
              width: `${(f.points / total) * 100}%`,
              background: FACTOR_COLOR[f.key] ?? "#94a3b8",
            }}
          />
        ))}
      </div>
      <ul className="space-y-1.5">
        {factors.map((f) => (
          <li key={f.key} className="flex items-baseline gap-2 text-[13px]">
            <span
              className="size-2 shrink-0 translate-y-[-1px] rounded-sm"
              style={{
                background: f.points < 0 ? "var(--faint)" : (FACTOR_COLOR[f.key] ?? "#94a3b8"),
              }}
              aria-hidden
            />
            <span className="text-text">{f.label}</span>
            {f.detail ? <span className="min-w-0 truncate text-muted">{f.detail}</span> : null}
            <span className="ml-auto pl-2 font-mono text-xs text-muted tnum">
              {f.points > 0 ? `+${f.points}` : f.points}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
