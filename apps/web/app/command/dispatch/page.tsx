"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, RefreshCw, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useShell } from "@/components/command/context";
import { SidePanel } from "@/components/command/panel";
import { LevelGlyph } from "@/components/domain";
import { Empty, ErrorNote, Kbd, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { ApiError, api, type CaseOut, type PlanStop, type TeamOut } from "@/lib/api";
import { ASSET_LABEL, ago, clock, cn, km, levelColor, minutes } from "@/lib/format";
import { keys, usePlan } from "@/lib/queries";
import { useUi } from "@/lib/store";

function Stop({
  s,
  c,
  now,
  onApprove,
  busy,
  canEdit,
}: {
  s: PlanStop;
  c: CaseOut | undefined;
  now: number;
  onApprove: () => void;
  busy: boolean;
  canEdit: boolean;
}) {
  const { selectedCaseId, select } = useUi();
  const approved = s.status === "approved";
  return (
    <li className={cn("relative pl-6", selectedCaseId === s.case_id && "rounded-md bg-panel-2/70")}>
      <span className="absolute top-3 left-[7px] size-2 rounded-full border border-line-strong bg-bg" aria-hidden />
      <div className="flex items-start gap-2 py-2 pr-2">
        <button type="button" onClick={() => select(s.case_id)} className="min-w-0 flex-1 text-left">
          <div className="flex items-center gap-2 text-xs">
            {c ? (
              <span
                className="inline-flex items-center gap-1 font-medium tnum"
                style={{ color: levelColor(c.urgency_level) }}
              >
                <LevelGlyph level={c.urgency_level} />
                {c.urgency_score}
              </span>
            ) : null}
            <span className="font-mono text-muted">{c?.tracking_code}</span>
            <span className="ml-auto text-muted tnum">
              {s.eta ? `ETA ${clock(s.eta)}` : ""} {s.distance_m ? `· ${km(s.distance_m)}` : ""}
            </span>
          </div>
          <p className="mt-0.5 truncate text-[13px] text-text">{c?.summary ?? "Case closed since planning"}</p>
          {s.reasons.length ? (
            <ul className="mt-1 space-y-0.5 text-xs text-muted">
              {s.reasons.slice(0, 3).map((r) => (
                <li key={r} className="truncate">
                  {r}
                </li>
              ))}
            </ul>
          ) : null}
          {c ? <p className="mt-0.5 text-xs text-faint tnum">waiting {ago(c.first_reported_at, now)}</p> : null}
        </button>
        {approved ? (
          <span className="mt-0.5 inline-flex items-center gap-1 text-xs text-go">
            <Check className="size-3.5" /> Approved
          </span>
        ) : canEdit ? (
          <Button size="xs" variant="subtle" loading={busy} onClick={onApprove}>
            Approve
          </Button>
        ) : null}
      </div>
    </li>
  );
}

export default function DispatchPage() {
  const { disasterId, cases, teams, now, canEdit } = useShell();
  const plan = usePlan(disasterId);
  const qc = useQueryClient();
  const { toast, selectedCaseId } = useUi();
  const [busy, setBusy] = useState<string | null>(null);
  const caseById = useMemo(() => new Map(cases.map((c) => [c.id, c])), [cases]);
  const teamById = useMemo(() => new Map(teams.map((t) => [t.id, t])), [teams]);
  const data = plan.data;
  const routes = useMemo(() => {
    const by = new Map<string, PlanStop[]>();
    for (const s of data?.stops ?? []) by.set(s.team_id, [...(by.get(s.team_id) ?? []), s]);
    return [...by.entries()]
      .map(([teamId, stops]) => ({
        team: teamById.get(teamId),
        stops: stops.sort((a, b) => a.sequence - b.sequence),
      }))
      .filter((r): r is { team: TeamOut; stops: PlanStop[] } => !!r.team)
      .sort(
        (a, b) =>
          Math.max(...b.stops.map((s) => caseById.get(s.case_id)?.urgency_score ?? 0)) -
          Math.max(...a.stops.map((s) => caseById.get(s.case_id)?.urgency_score ?? 0)),
      );
  }, [data, teamById, caseById]);
  const pending = (data?.stops ?? []).filter((s) => s.status === "proposed");

  const approve = useCallback(
    async (ids: string[] | null, key: string) => {
      if (!data?.id) return;
      setBusy(key);
      try {
        const r = await api.post<{ approved: unknown[] }>(`/api/v1/dispatch/plan/${data.id}/approve`, {
          assignment_ids: ids,
        });
        toast({
          kind: "success",
          text: r.approved.length === 1 ? "Team dispatched" : `${r.approved.length} teams dispatched`,
        });
        qc.invalidateQueries({ queryKey: keys.plan(disasterId ?? "") });
      } catch (e) {
        toast({
          kind: "error",
          text: e instanceof ApiError ? e.message : "Could not approve",
        });
        qc.invalidateQueries({ queryKey: keys.plan(disasterId ?? "") });
      } finally {
        setBusy(null);
      }
    },
    [data?.id, disasterId, qc, toast],
  );

  const replan = async () => {
    setBusy("replan");
    try {
      const fresh = await api.post("/api/v1/dispatch/replan", {
        disaster_id: disasterId,
      });
      qc.setQueryData(keys.plan(disasterId ?? ""), fresh);
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Planning failed",
      });
    } finally {
      setBusy(null);
    }
  };

  // "a" approves the stop for the case in view
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key !== "a" || t.closest("input, textarea, select, [role=dialog]") || e.metaKey || e.ctrlKey || !canEdit)
        return;
      const stop = pending.find((s) => s.case_id === selectedCaseId);
      if (stop) {
        e.preventDefault();
        approve([stop.assignment_id], stop.assignment_id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, selectedCaseId, approve, canEdit]);

  const stats = (data?.stats ?? {}) as Record<string, number | boolean | string>;
  const noTeams = teams.every((t) => t.status === "off_duty");

  return (
    <SidePanel
      title="Dispatch plan"
      aside={
        data?.created_at ? (
          <span className="tnum">
            {clock(data.created_at)} · solved in {data.solver_ms ?? 0} ms
          </span>
        ) : null
      }
      toolbar={
        data?.id ? (
          <div className="space-y-2.5">
            <p className="text-[13px] text-muted">
              <span className="text-text tnum">{String(stats.stops ?? 0)}</span> stops for{" "}
              <span className="text-text tnum">{String(stats.teams ?? 0)}</span> teams, reaching{" "}
              <span className="text-text tnum">{String(stats.people_covered ?? 0)}</span> people and{" "}
              <span className="text-critical tnum">
                {String(stats.critical_covered ?? 0)} of {String(stats.critical_open ?? 0)}
              </span>{" "}
              critical cases.
            </p>
            {stats.stale ? (
              <p className="flex items-center gap-2 text-xs text-medium">
                <TriangleAlert className="size-3.5" /> Plan may be stale: the last re-plan found no solution. Assign by
                hand if needed.
              </p>
            ) : null}
          </div>
        ) : null
      }
      footer={
        canEdit ? (
          <div className="flex items-center gap-2">
            <Button
              variant="go"
              disabled={!pending.length}
              loading={busy === "all"}
              onClick={() => approve(null, "all")}
            >
              Approve all {pending.length || ""}
            </Button>
            <Button
              variant="outline"
              icon={<RefreshCw className="size-3.5" />}
              loading={busy === "replan"}
              onClick={replan}
            >
              Re-plan now
            </Button>
            <span className="ml-auto hidden items-center gap-1 text-xs text-faint sm:flex">
              <Kbd>a</Kbd> approve selected
            </span>
          </div>
        ) : null
      }
    >
      {plan.error ? (
        <div className="p-4">
          <ErrorNote onRetry={() => plan.refetch()}>Could not load the plan.</ErrorNote>
        </div>
      ) : plan.isLoading ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : noTeams ? (
        <Empty
          title="No teams available. Dispatch is paused."
          body="Put a team on duty from the Teams page or the field app."
        />
      ) : !data?.id || data.stops.length === 0 ? (
        <Empty
          title="Nothing to dispatch right now"
          body="New cases trigger a fresh plan within seconds. You can also re-plan now."
        />
      ) : (
        <div className="py-1">
          {routes.map(({ team, stops }) => {
            const open = stops.filter((s) => s.status === "proposed");
            return (
              <section key={team.id} className="border-b border-line px-3 py-3 last:border-0">
                <div className="mb-1 flex items-center gap-2 px-1">
                  <span className="font-mono text-[13px] font-semibold">{team.call_sign}</span>
                  <span className="text-xs text-muted">
                    {ASSET_LABEL[team.asset_type]}, carries {team.capacity}
                  </span>
                  {canEdit && open.length > 1 ? (
                    <Button
                      size="xs"
                      variant="ghost"
                      className="ml-auto"
                      loading={busy === team.id}
                      onClick={() =>
                        approve(
                          open.map((s) => s.assignment_id),
                          team.id,
                        )
                      }
                    >
                      Approve route
                    </Button>
                  ) : null}
                </div>
                <ol className="relative ml-1 border-l border-dashed border-line-strong">
                  {stops.map((s) => (
                    <Stop
                      key={s.assignment_id}
                      s={s}
                      c={caseById.get(s.case_id)}
                      now={now}
                      busy={busy === s.assignment_id}
                      canEdit={canEdit}
                      onApprove={() => approve([s.assignment_id], s.assignment_id)}
                    />
                  ))}
                </ol>
                {stops[0]?.travel_s ? (
                  <p className="mt-1 pl-6 text-xs text-faint">First stop about {minutes(stops[0].travel_s)} away</p>
                ) : null}
              </section>
            );
          })}
          {data.dropped.length ? (
            <section className="px-4 py-3">
              <h2 className="mb-2 text-[13px] font-semibold">
                Waiting for a team <span className="font-normal text-muted tnum">{data.dropped.length}</span>
              </h2>
              <ul className="space-y-1.5">
                {(data.dropped as { case_id: string; reason: string }[]).slice(0, 25).map((d) => {
                  const c = caseById.get(d.case_id);
                  if (!c) return null;
                  return (
                    <li key={d.case_id}>
                      <button
                        type="button"
                        onClick={() => useUi.getState().select(c.id)}
                        className="w-full text-left text-xs"
                      >
                        <span
                          className="inline-flex items-center gap-1 font-medium tnum"
                          style={{ color: levelColor(c.urgency_level) }}
                        >
                          <LevelGlyph level={c.urgency_level} />
                          {c.urgency_score}
                        </span>{" "}
                        <span className="text-text">{c.summary}</span>
                        <span className="block text-muted">{d.reason}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}
        </div>
      )}
    </SidePanel>
  );
}
