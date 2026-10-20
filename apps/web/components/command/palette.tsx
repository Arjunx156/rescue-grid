"use client";

import { Search } from "lucide-react";
import { Dialog as D } from "radix-ui";
import { useMemo, useState } from "react";
import type { CaseOut } from "@/lib/api";
import { ago, cn } from "@/lib/format";
import { LevelGlyph } from "../domain";
import { sortCases } from "./queue-panel";

/** ⌘K: jump to any open case by code, place or words in its summary. */
export function Palette({
  open,
  onOpenChange,
  cases,
  now,
  onPick,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  cases: CaseOut[];
  now: number;
  onPick: (c: CaseOut) => void;
}) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    const pool = term
      ? cases.filter((c) =>
          [c.tracking_code, c.locality, c.address_text, c.summary].some((v) => v?.toLowerCase().includes(term)),
        )
      : cases;
    return sortCases(pool).slice(0, 8);
  }, [q, cases]);
  const pick = (c: CaseOut | undefined) => {
    if (!c) return;
    onPick(c);
    onOpenChange(false);
    setQ("");
  };
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <D.Content className="theme-dark fixed top-[18vh] left-1/2 z-50 w-[min(560px,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-panel text-text shadow-float animate-in">
          <D.Title className="sr-only">Find a case</D.Title>
          <div className="flex items-center gap-2 border-b border-line px-4">
            <Search className="size-4 text-muted" />
            <input
              role="combobox"
              aria-expanded={results.length > 0}
              aria-controls="palette-results"
              aria-activedescendant={results[active] ? `palette-${results[active].id}` : undefined}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  setActive((a) => Math.min(results.length - 1, a + 1));
                  e.preventDefault();
                } else if (e.key === "ArrowUp") {
                  setActive((a) => Math.max(0, a - 1));
                  e.preventDefault();
                } else if (e.key === "Enter") {
                  pick(results[active]);
                }
              }}
              placeholder="Tracking code, locality or words from the report"
              aria-label="Search cases"
              className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-faint focus-visible:outline-none"
            />
          </div>
          {results.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted">No open case matches “{q}”.</p>
          ) : (
            <div
              id="palette-results"
              role="listbox"
              aria-label="Matching cases"
              className="max-h-80 overflow-y-auto py-1 scroll-thin"
            >
              {results.map((c, i) => (
                <div
                  key={c.id}
                  id={`palette-${c.id}`}
                  role="option"
                  tabIndex={-1}
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(c)}
                  onKeyDown={(e) => e.key === "Enter" && pick(c)}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-3 px-4 py-2 text-left",
                    i === active && "bg-panel-2",
                  )}
                >
                  <span style={{ color: `var(--${c.urgency_level})` }}>
                    <LevelGlyph level={c.urgency_level} />
                  </span>
                  <span className="w-16 font-mono text-xs text-muted">{c.tracking_code}</span>
                  <span className="min-w-0 flex-1 truncate text-[13px]">{c.summary}</span>
                  <span className="text-xs text-muted">{c.locality}</span>
                  <span className="w-12 text-right text-xs text-muted tnum">{ago(c.first_reported_at, now)}</span>
                </div>
              ))}
            </div>
          )}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
