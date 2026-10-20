"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, GitMerge, Search, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useShell } from "@/components/command/context";
import { FullPage } from "@/components/command/panel";
import { Confidence, LevelGlyph, VulnIcons } from "@/components/domain";
import { Empty, Kbd, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { Dialog } from "@/components/ui/overlay";
import { ApiError, api, type CaseOut } from "@/lib/api";
import { ago, cn, levelColor, STATUS_LABEL, WATER_LABEL } from "@/lib/format";
import { useUi } from "@/lib/store";

type SortKey = "score" | "waiting" | "people" | "locality";

const STATUS_FILTERS: Record<string, string[] | null> = {
  "Needs a team": ["new", "needs_review", "queued", "unreachable"],
  "In the field": ["assigned", "en_route", "on_scene"],
  "Needs review": ["needs_review"],
  "All open": null,
};

export default function QueuePage() {
  const { cases, teams, now, canEdit, loading, disasterId } = useShell();
  const { selectedCaseId, select, toast } = useUi();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("Needs a team");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({
    key: "score",
    dir: -1,
  });
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [confirmClose, setConfirmClose] = useState(false);
  const [busy, setBusy] = useState(false);
  const tbody = useRef<HTMLTableSectionElement>(null);
  const teamById = useMemo(() => new Map(teams.map((t) => [t.id, t])), [teams]);

  const rows = useMemo(() => {
    const allowed = STATUS_FILTERS[status];
    const term = q.trim().toLowerCase();
    const list = cases.filter(
      (c) =>
        (!allowed || allowed.includes(c.status)) &&
        (!term ||
          [c.tracking_code, c.summary, c.locality, c.address_text].some((v) => v?.toLowerCase().includes(term))),
    );
    const val = (c: CaseOut): number | string => {
      switch (sort.key) {
        case "score":
          return c.urgency_score;
        case "waiting":
          return -new Date(c.first_reported_at).getTime();
        case "people":
          return c.people_count ?? 0;
        case "locality":
          return (c.locality ?? "").toLowerCase();
      }
    };
    return list.sort((a, b) => {
      const x = val(a);
      const y = val(b);
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir || b.urgency_score - a.urgency_score;
    });
  }, [cases, q, status, sort]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [role=dialog]") || e.metaKey || e.ctrlKey) return;
      if (e.key !== "j" && e.key !== "k") return;
      const i = rows.findIndex((c) => c.id === selectedCaseId);
      const next = rows[e.key === "j" ? Math.min(rows.length - 1, i + 1) : Math.max(0, i - 1)];
      if (!next) return;
      select(next.id);
      tbody.current?.querySelector(`[data-id="${next.id}"]`)?.scrollIntoView({ block: "nearest" });
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, selectedCaseId, select]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === "locality" ? 1 : -1 }));

  const head = (key: SortKey, label: string, className?: string) => (
    <th
      scope="col"
      className={cn("px-3 py-2 font-medium", className)}
      aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      <button type="button" onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 hover:text-text">
        {label}
        {sort.key === key ? sort.dir === 1 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" /> : null}
      </button>
    </th>
  );

  const selected = cases.filter((c) => checked.has(c.id));
  const bulkMerge = async () => {
    if (selected.length < 2) return;
    setBusy(true);
    const [keep, ...rest] = [...selected].sort((a, b) => b.urgency_score - a.urgency_score);
    try {
      for (const other of rest)
        await api.post(`/api/v1/cases/${keep.id}/merge`, {
          other_case_id: other.id,
        });
      toast({
        kind: "success",
        text: `Merged ${rest.length} into ${keep.tracking_code}`,
      });
      setChecked(new Set());
      qc.invalidateQueries({ queryKey: ["cases", disasterId] });
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Merge failed",
      });
    } finally {
      setBusy(false);
    }
  };
  const bulkClose = async () => {
    setBusy(true);
    try {
      for (const c of selected)
        await api.patch(`/api/v1/cases/${c.id}`, {
          status: "false_alarm",
          note: "Closed in bulk from the queue",
        });
      toast({
        kind: "success",
        text: `Closed ${selected.length} as false alarms`,
      });
      setChecked(new Set());
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Could not close all of them",
      });
    } finally {
      setBusy(false);
      setConfirmClose(false);
    }
  };

  return (
    <FullPage
      title="Queue"
      description="Every open case, most urgent first. Click a row to open it; j and k move through the list."
      actions={
        <>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-faint" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search cases"
              className="w-60 pl-8"
              aria-label="Filter cases"
            />
          </div>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40" aria-label="Status">
            {Object.keys(STATUS_FILTERS).map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
        </>
      }
    >
      {canEdit && checked.size > 0 ? (
        <div className="sticky top-0 z-10 mb-3 flex items-center gap-3 rounded-lg border border-accent/40 bg-panel px-3 py-2 text-[13px]">
          <span className="tnum">{checked.size} selected</span>
          <Button
            size="sm"
            variant="subtle"
            icon={<GitMerge className="size-3.5" />}
            disabled={checked.size < 2}
            loading={busy}
            onClick={bulkMerge}
          >
            Merge into one case
          </Button>
          <Button
            size="sm"
            variant="danger"
            icon={<XCircle className="size-3.5" />}
            onClick={() => setConfirmClose(true)}
          >
            Close as false alarms
          </Button>
          <button type="button" onClick={() => setChecked(new Set())} className="ml-auto text-muted hover:text-text">
            Clear
          </button>
        </div>
      ) : null}
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[1080px] border-collapse text-left text-[13px]">
          <thead className="sticky top-0 z-[1] bg-panel text-xs text-muted">
            <tr className="border-b border-line">
              {canEdit ? (
                <th scope="col" className="w-9 px-3">
                  <input
                    type="checkbox"
                    aria-label="Select all shown"
                    className="accent-[var(--focus)]"
                    checked={rows.length > 0 && rows.every((c) => checked.has(c.id))}
                    onChange={(e) => setChecked(e.target.checked ? new Set(rows.map((c) => c.id)) : new Set())}
                  />
                </th>
              ) : null}
              {head("score", "Urgency", "w-28")}
              <th scope="col" className="px-3 py-2 font-medium">
                Code
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Who and what
              </th>
              {head("people", "People", "w-20")}
              <th scope="col" className="px-3 py-2 font-medium">
                Water
              </th>
              {head("locality", "Where")}
              {head("waiting", "Waiting", "w-24")}
              <th scope="col" className="px-3 py-2 font-medium">
                Status
              </th>
            </tr>
          </thead>
          <tbody ref={tbody}>
            {loading
              ? Array.from({ length: 8 }, (_, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: placeholders have no identity
                  <tr key={i} className="border-b border-line">
                    <td colSpan={9} className="px-3 py-3">
                      <Skeleton className="h-4 w-full" />
                    </td>
                  </tr>
                ))
              : rows.map((c) => {
                  const team = c.current_team_id ? teamById.get(c.current_team_id) : undefined;
                  return (
                    <tr
                      key={c.id}
                      data-id={c.id}
                      onClick={() => select(c.id)}
                      aria-selected={c.id === selectedCaseId}
                      className={cn(
                        "cursor-pointer border-b border-line transition-colors last:border-0",
                        c.id === selectedCaseId ? "bg-panel-2" : "hover:bg-panel",
                      )}
                    >
                      {canEdit ? (
                        <td
                          className="px-3"
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            className="accent-[var(--focus)]"
                            aria-label={`Select ${c.tracking_code}`}
                            checked={checked.has(c.id)}
                            onChange={(e) => {
                              const next = new Set(checked);
                              if (e.target.checked) next.add(c.id);
                              else next.delete(c.id);
                              setChecked(next);
                            }}
                          />
                        </td>
                      ) : null}
                      <td className="px-3 py-2.5">
                        <span
                          className="inline-flex items-center gap-1.5 font-medium tnum"
                          style={{ color: levelColor(c.urgency_level) }}
                        >
                          <LevelGlyph level={c.urgency_level} />
                          {c.urgency_score}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 font-mono text-xs text-muted">{c.tracking_code}</td>
                      <td className="max-w-[28rem] px-3">
                        <div className="truncate text-text">{c.summary}</div>
                        <div className="mt-0.5">
                          <VulnIcons c={c} max={5} />
                        </div>
                      </td>
                      <td className="px-3 tnum">{c.people_count ?? "?"}</td>
                      <td className="whitespace-nowrap px-3 text-water">
                        {c.water_level && c.water_level !== "unknown" ? (
                          WATER_LABEL[c.water_level]
                        ) : (
                          <span className="text-faint">Unknown</span>
                        )}
                      </td>
                      <td className="px-3">
                        <div className="flex items-center gap-2">
                          <span className="max-w-52 truncate">{c.locality ?? c.address_text ?? "Not matched"}</span>
                          {c.location_confidence < 0.6 ? (
                            <Confidence value={c.location_confidence} source={c.location_source} />
                          ) : null}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-3 text-muted tnum">{ago(c.first_reported_at, now)}</td>
                      <td className="whitespace-nowrap px-3">
                        {team ? (
                          <span className="font-mono text-xs text-accent-text">
                            {team.call_sign} · {STATUS_LABEL[c.status]}
                          </span>
                        ) : (
                          <span className={c.status === "needs_review" ? "text-medium" : "text-muted"}>
                            {STATUS_LABEL[c.status]}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
          </tbody>
        </table>
        {!loading && rows.length === 0 ? (
          <Empty
            title={cases.length ? "No case matches" : "All clear. No open cases."}
            body={cases.length ? "Try another filter or search." : undefined}
          />
        ) : null}
      </div>
      <p className="mt-3 flex items-center gap-2 text-xs text-faint">
        <Kbd>j</Kbd>
        <Kbd>k</Kbd> move · <Kbd>Esc</Kbd> close · <Kbd>⌘K</Kbd> find
      </p>
      <Dialog
        open={confirmClose}
        onOpenChange={setConfirmClose}
        size="sm"
        title={`Close ${selected.length} cases as false alarms?`}
        description="They leave the queue and any assigned team is stood down. Each case keeps its history."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmClose(false)}>
              Keep them
            </Button>
            <Button variant="danger" loading={busy} onClick={bulkClose}>
              Close {selected.length} cases
            </Button>
          </>
        }
      />
    </FullPage>
  );
}
