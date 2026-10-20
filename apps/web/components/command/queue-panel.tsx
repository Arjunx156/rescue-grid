"use client";

import { ChevronsRight, Layers } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CaseOut, TeamOut } from "@/lib/api";
import { cn, LEVEL_LABEL, LEVELS, type Level, levelColor } from "@/lib/format";
import { useUi } from "@/lib/store";
import { LevelGlyph } from "../domain";
import { Empty, Kbd } from "../ui/bits";
import { Menu } from "../ui/overlay";
import { CaseRow } from "./case-row";

const NEEDS_ACTION = new Set(["new", "needs_review", "queued", "unreachable"]);

export function sortCases(cases: CaseOut[]): CaseOut[] {
  return [...cases].sort(
    (a, b) => b.urgency_score - a.urgency_score || a.first_reported_at.localeCompare(b.first_reported_at),
  );
}

function LayerToggles() {
  const { showFlood, showTeams, showRoutes, setLayer } = useUi();
  const row = (k: "showFlood" | "showTeams" | "showRoutes", label: string, on: boolean) => (
    <label className="flex cursor-pointer items-center justify-between gap-6 rounded-md px-2.5 py-1.5 text-[13px] hover:bg-panel-2">
      {label}
      <input
        type="checkbox"
        className="accent-[var(--focus)]"
        checked={on}
        onChange={(e) => setLayer(k, e.target.checked)}
      />
    </label>
  );
  return (
    <Menu
      trigger={
        <button
          type="button"
          className="grid size-7 place-items-center rounded-md text-muted hover:bg-panel-2 hover:text-text"
          aria-label="Map layers"
        >
          <Layers className="size-4" />
        </button>
      }
    >
      <div className="p-1">
        {row("showFlood", "Flood zones", showFlood)}
        {row("showTeams", "Teams", showTeams)}
        {row("showRoutes", "Routes", showRoutes)}
      </div>
    </Menu>
  );
}

export function QueuePanel({ cases, teams, now }: { cases: CaseOut[]; teams: TeamOut[]; now: number }) {
  const { selectedCaseId, select, levels, toggleLevel, hover, queueOpen, setQueueOpen } = useUi();
  const [scope, setScope] = useState<"action" | "all">("action");
  const [frozen, setFrozen] = useState<string[] | null>(null);
  const rows = useRef(new Map<string, HTMLButtonElement>());
  const teamById = useMemo(() => new Map(teams.map((t) => [t.id, t])), [teams]);

  const counts = useMemo(() => {
    const out: Record<string, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
    };
    for (const c of cases) out[c.urgency_level] = (out[c.urgency_level] ?? 0) + 1;
    return out;
  }, [cases]);

  const visible = useMemo(() => {
    const filtered = cases.filter(
      (c) => levels.includes(c.urgency_level as Level) && (scope === "all" || NEEDS_ACTION.has(c.status)),
    );
    const sorted = sortCases(filtered);
    if (!frozen) return { list: sorted, fresh: 0 };
    // while the pointer is in the list, rows keep their places; newcomers wait above
    const index = new Map(frozen.map((id, i) => [id, i]));
    const known = sorted.filter((c) => index.has(c.id)).sort((a, b) => (index.get(a.id) ?? 0) - (index.get(b.id) ?? 0));
    return { list: known, fresh: sorted.length - known.length };
  }, [cases, levels, scope, frozen]);

  // j/k walk the queue, Enter opens; ignored while typing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target instanceof Element ? e.target : null;
      if (
        target?.closest("input, textarea, select, [contenteditable], [role=dialog]") ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey
      )
        return;
      if (e.key !== "j" && e.key !== "k") return;
      const list = visible.list;
      if (!list.length) return;
      const i = list.findIndex((c) => c.id === selectedCaseId);
      const next = e.key === "j" ? Math.min(list.length - 1, i + 1) : Math.max(0, i === -1 ? 0 : i - 1);
      const id = list[next].id;
      select(id);
      rows.current.get(id)?.scrollIntoView({ block: "nearest" });
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible.list, selectedCaseId, select]);

  if (!queueOpen) {
    return (
      <button
        type="button"
        onClick={() => setQueueOpen(true)}
        className="glass absolute top-3 right-3 z-10 flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[13px] shadow-float"
      >
        Queue <span className="text-muted tnum">{cases.length}</span>
      </button>
    );
  }

  return (
    <aside
      aria-label="Case queue"
      className={cn(
        "glass absolute top-3 right-3 bottom-3 z-10 flex w-[380px] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-xl border border-line shadow-float",
        selectedCaseId && "hidden xl:flex xl:right-[464px]",
      )}
    >
      <div className="space-y-2.5 border-b border-line px-3.5 pt-3 pb-2.5">
        <div className="flex items-center gap-2">
          <h2 className="text-[14px] font-semibold">Queue</h2>
          <span className="text-xs text-muted tnum">{visible.list.length} shown</span>
          <div className="ml-auto flex items-center gap-0.5">
            <LayerToggles />
            <button
              type="button"
              onClick={() => setQueueOpen(false)}
              className="grid size-7 place-items-center rounded-md text-muted hover:bg-panel-2 hover:text-text"
              aria-label="Hide queue"
            >
              <ChevronsRight className="size-4" />
            </button>
          </div>
        </div>
        <fieldset className="flex min-w-0 items-center gap-1">
          <legend className="sr-only">Filter by urgency</legend>
          {LEVELS.map((l) => {
            const on = levels.includes(l);
            return (
              <button
                key={l}
                type="button"
                aria-pressed={on}
                onClick={() => toggleLevel(l)}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-md border px-1.5 text-xs transition-colors",
                  on ? "border-line-strong bg-panel-2 text-text" : "border-transparent text-faint hover:text-muted",
                )}
              >
                <span style={{ color: on ? levelColor(l) : undefined }}>
                  <LevelGlyph level={l} />
                </span>
                {LEVEL_LABEL[l]}
                <span className="text-muted tnum">{counts[l]}</span>
              </button>
            );
          })}
        </fieldset>
        <div className="flex items-center gap-1 text-xs" role="tablist" aria-label="Which cases">
          {(["action", "all"] as const).map((s) => (
            <button
              key={s}
              type="button"
              role="tab"
              aria-selected={scope === s}
              onClick={() => setScope(s)}
              className={cn(
                "rounded-md px-2 py-1",
                scope === s ? "bg-panel-2 text-text" : "text-muted hover:text-text",
              )}
            >
              {s === "action" ? "Needs a team" : "All open"}
            </button>
          ))}
          <span className="ml-auto hidden items-center gap-1 text-faint lg:flex">
            <Kbd>j</Kbd>
            <Kbd>k</Kbd> to move
          </span>
        </div>
      </div>
      {visible.fresh > 0 ? (
        <button
          type="button"
          onClick={() => setFrozen(null)}
          className="border-b border-line bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent-text"
        >
          Show {visible.fresh} new
        </button>
      ) : null}
      {/* hold the order still while someone is pointing at or tabbing through it */}
      <section
        aria-label="Open cases"
        className="min-h-0 flex-1 overflow-y-auto scroll-thin"
        onMouseEnter={() => setFrozen(sortCases(cases).map((c) => c.id))}
        onMouseLeave={() => setFrozen(null)}
        onFocus={() => setFrozen((f) => f ?? sortCases(cases).map((c) => c.id))}
        onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setFrozen(null)}
      >
        {visible.list.length === 0 ? (
          <Empty
            title={cases.length ? "Nothing matches these filters" : "All clear. No open cases."}
            body={
              cases.length ? "Turn a level back on to see more." : "New SOS reports appear here the moment they arrive."
            }
          />
        ) : (
          visible.list.map((c) => (
            <CaseRow
              key={c.id}
              ref={(node) => {
                if (node) rows.current.set(c.id, node);
                else rows.current.delete(c.id);
              }}
              c={c}
              team={c.current_team_id ? teamById.get(c.current_team_id) : undefined}
              now={now}
              selected={c.id === selectedCaseId}
              onSelect={() => select(c.id)}
              onHover={hover}
            />
          ))
        )}
      </section>
    </aside>
  );
}
