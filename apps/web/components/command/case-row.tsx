"use client";

import { Waves } from "lucide-react";
import { forwardRef } from "react";
import type { CaseOut, TeamOut } from "@/lib/api";
import { ago, cn, levelColor, REASON_LABEL, STATUS_LABEL } from "@/lib/format";
import { clockLeft, clockText } from "@/lib/water";
import { Confidence, LevelGlyph, PeopleCount, SourceCount, VulnIcons } from "../domain";

interface Props {
  c: CaseOut;
  team?: TeamOut;
  now: number;
  selected: boolean;
  onSelect: () => void;
  onHover?: (id: string | null) => void;
}

/** One case, scannable in a second: level, what, where, how long, who's on it. */
export const CaseRow = forwardRef<HTMLButtonElement, Props>(function CaseRow(
  { c, team, now, selected, onSelect, onHover },
  ref,
) {
  const color = levelColor(c.urgency_level);
  const waiting = ago(c.first_reported_at, now);
  const reason = c.review_reasons[0];
  const left = team ? null : clockLeft(c.water_clock, now);
  const racing = left != null && left <= 180;
  return (
    <button
      ref={ref}
      type="button"
      onClick={onSelect}
      onMouseEnter={() => onHover?.(c.id)}
      onMouseLeave={() => onHover?.(null)}
      aria-current={selected || undefined}
      aria-label={`${c.urgency_level} case, ${c.people_count ?? "unknown"} people, ${waiting} waiting, ${c.locality ?? "location pending"}${racing ? `, water reaches their danger line in ${clockText(left)}` : ""}`}
      className={cn(
        "group relative block w-full border-b border-line px-3.5 py-3 text-left transition-colors [content-visibility:auto] [contain-intrinsic-size:auto_92px]",
        selected ? "bg-panel-2" : "hover:bg-panel-2/60",
      )}
    >
      <span
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ background: selected ? color : "transparent" }}
        aria-hidden
      />
      <div className="flex items-center gap-2 text-xs">
        <span className="inline-flex items-center gap-1.5 font-medium tnum" style={{ color }}>
          <LevelGlyph level={c.urgency_level} />
          {c.urgency_score}
        </span>
        <span className="font-mono text-faint">{c.tracking_code}</span>
        <span className="ml-auto text-muted tnum">{waiting}</span>
      </div>
      <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-text">{c.summary || "Reading the report"}</p>
      <div className="mt-1.5 flex items-center gap-2.5 text-xs text-muted">
        <PeopleCount n={c.people_count} />
        <VulnIcons c={c} max={3} showMedical={false} />
        <SourceCount n={c.source_count} />
        {racing ? (
          <span
            className={cn(
              "ml-auto inline-flex items-center gap-1 font-medium tnum",
              left < 60 ? "text-critical" : "text-high",
            )}
            title={c.water_clock?.danger_label}
          >
            <Waves className="size-3.5" aria-hidden="true" />
            {clockText(left)}
          </span>
        ) : null}
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-xs">
        <span className="min-w-0 truncate text-muted">{c.locality ?? c.address_text ?? "Location pending"}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          {team ? (
            <span className="font-mono text-accent-text">
              {team.call_sign} · {STATUS_LABEL[c.status]}
            </span>
          ) : reason ? (
            <span className="text-medium">{REASON_LABEL[reason] ?? reason}</span>
          ) : null}
          {c.location_confidence < 0.6 ? <Confidence value={c.location_confidence} source={c.location_source} /> : null}
        </span>
      </div>
    </button>
  );
});
