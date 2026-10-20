"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  Crosshair,
  GitMerge,
  MapPin,
  MoreHorizontal,
  Phone,
  ShieldAlert,
  Truck,
  Undo2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type CaseDetail, type CaseOut, type TeamOut } from "@/lib/api";
import {
  ASSET_LABEL,
  ago,
  CHANNEL_LABEL,
  clock,
  cn,
  km,
  minutes,
  NEED_LABEL,
  REASON_LABEL,
  STATUS_LABEL,
  stamp,
  TEAM_STATUS_LABEL,
} from "@/lib/format";
import { keys, useCase } from "@/lib/queries";
import { useUi } from "@/lib/store";
import { canReach, effectiveDepth, etaSeconds, haversineM } from "@/lib/travel";
import type { WaterField } from "@/lib/water";
import { Confidence, PeopleCount, ScoreBreakdown, SourceCount, UrgencyPill, VulnIcons, WaterTag } from "../domain";
import { ErrorNote, Section, Skeleton } from "../ui/bits";
import { Button } from "../ui/button";
import { Dialog, Menu, MenuItem, MenuSeparator } from "../ui/overlay";
import { WaterClock } from "./water-clock";

const EVENT_LABEL: Record<string, string> = {
  case_created: "Case created",
  report_merged: "Another report merged in",
  assigned: "Team assigned",
  assignment_cancelled: "Assignment cancelled",
  field_started: "Team set off",
  field_reached: "Team reached",
  field_completed: "Rescue completed",
  field_failed: "Team couldn't reach",
  case_edited: "Edited",
  merged: "Absorbed a duplicate",
  merged_into: "Merged into another case",
  unmerged: "Merge undone",
  duplicate_dismissed: "Marked not a duplicate",
  pin_received: "Reporter shared a pin",
};

function useCaseAction(caseId: string) {
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  return useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.case(caseId) });
    },
    onError: (e) =>
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "That did not work. Try again.",
      }),
  });
}

function eventText(e: CaseDetail["events"][number]): string {
  const p = e.payload as Record<string, unknown>;
  const base = EVENT_LABEL[e.event_type] ?? e.event_type.replace(/_/g, " ");
  if (e.event_type === "assigned" && p.team) return `${base}: ${p.team}`;
  if (e.event_type === "field_completed" && p.people_rescued != null) return `${p.team} rescued ${p.people_rescued}`;
  if (e.event_type === "report_merged" && Array.isArray(p.reasons) && p.reasons.length)
    return `${base} (${(p.reasons as string[]).slice(0, 2).join(", ")})`;
  if (e.event_type === "case_edited" && p.location) return "Location corrected";
  return base;
}

function AssignDialog({
  c,
  teams,
  open,
  onOpenChange,
}: {
  c: CaseOut;
  teams: TeamOut[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const action = useCaseAction(c.id);
  const toast = useUi((s) => s.toast);
  const depth = effectiveDepth(c.water_level, c.flood_depth_m);
  const rows = useMemo(
    () =>
      teams
        .filter((t) => t.status !== "off_duty" && t.lat != null && t.lng != null && c.lat != null && c.lng != null)
        .map((t) => {
          const d = haversineM(t.lat as number, t.lng as number, c.lat as number, c.lng as number);
          return {
            t,
            d,
            eta: etaSeconds(t.asset_type, d),
            reach: canReach(t.asset_type, depth, c.in_flood_zone),
          };
        })
        .sort((a, b) => Number(b.reach.ok) - Number(a.reach.ok) || a.eta - b.eta),
    [teams, c, depth],
  );
  const assign = (t: TeamOut) =>
    action.mutate(() => api.post(`/api/v1/cases/${c.id}/assign`, { team_id: t.id }), {
      onSuccess: () => {
        onOpenChange(false);
        toast({
          kind: "success",
          text: `${t.call_sign} assigned to ${c.tracking_code}`,
        });
      },
    });
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Assign a team to ${c.tracking_code}`}
      description={
        depth != null
          ? `About ${depth.toFixed(1)} m of water. Teams that cannot get through are listed last.`
          : undefined
      }
    >
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No teams are on duty. Ask a team lead to go on duty from the field app.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map(({ t, d, eta, reach }, i) => (
            <li key={t.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-mono font-medium">{t.call_sign}</span>
                  <span className="text-muted">
                    {ASSET_LABEL[t.asset_type]}, carries {t.capacity}
                  </span>
                  {i === 0 && reach.ok ? <span className="text-xs text-go">Nearest that can reach</span> : null}
                </div>
                <div className="text-xs text-muted">
                  {km(d)} · about {minutes(eta)} · {TEAM_STATUS_LABEL[t.status]}
                  {t.queued ? ` · ${t.queued} more queued` : ""}
                  {reach.ok ? "" : ` · ${reach.why}`}
                </div>
              </div>
              <Button
                size="sm"
                variant={reach.ok ? "primary" : "outline"}
                disabled={!reach.ok}
                loading={action.isPending}
                onClick={() => assign(t)}
              >
                Assign
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

function MergeDialog({
  c,
  cases,
  open,
  onOpenChange,
}: {
  c: CaseOut;
  cases: CaseOut[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const { toast, select } = useUi();
  const action = useCaseAction(c.id);
  const [other, setOther] = useState<CaseOut | null>(null);
  const near = useMemo(
    () =>
      c.lat == null || c.lng == null
        ? []
        : cases
            .filter((x) => x.id !== c.id && x.lat != null && x.lng != null)
            .map((x) => ({
              x,
              d: haversineM(c.lat as number, c.lng as number, x.lat as number, x.lng as number),
            }))
            .filter((r) => r.d < 1500)
            .sort((a, b) => a.d - b.d)
            .slice(0, 12),
    [c, cases],
  );
  const merge = () => {
    if (!other) return;
    action.mutate(() => api.post(`/api/v1/cases/${c.id}/merge`, { other_case_id: other.id }), {
      onSuccess: () => {
        onOpenChange(false);
        qc.invalidateQueries({ queryKey: ["review"] });
        toast({
          kind: "success",
          text: `${other.tracking_code} merged into ${c.tracking_code}`,
          undo: () => {
            api
              .post(`/api/v1/cases/${other.id}/unmerge`)
              .then(() => {
                qc.invalidateQueries({ queryKey: ["cases"] });
                select(other.id);
              })
              .catch(() => toast({ kind: "error", text: "Could not undo the merge" }));
          },
        });
        setOther(null);
      },
    });
  };
  const row = (label: string, a: React.ReactNode, b: React.ReactNode) => (
    <div className="grid grid-cols-[7rem_1fr_1fr] gap-3 border-b border-line py-2 text-[13px] last:border-0">
      <span className="text-muted">{label}</span>
      <span>{a}</span>
      <span>{b}</span>
    </div>
  );
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) setOther(null);
      }}
      size="lg"
      title={`Merge into ${c.tracking_code}`}
      description="Pick the report that describes the same family. Both histories are kept, and you can undo."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!other} loading={action.isPending} onClick={merge} icon={<GitMerge className="size-4" />}>
            Merge cases
          </Button>
        </>
      }
    >
      {near.length === 0 ? (
        <p className="text-sm text-muted">No other open cases within 1.5 km.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
          <ul className="space-y-1">
            {near.map(({ x, d }) => (
              <li key={x.id}>
                <button
                  type="button"
                  onClick={() => setOther(x)}
                  className={cn(
                    "w-full rounded-md border px-2.5 py-2 text-left text-[13px] transition-colors",
                    other?.id === x.id ? "border-accent bg-accent-soft" : "border-line hover:border-line-strong",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs">{x.tracking_code}</span>
                    <span className="text-xs text-muted">{km(d)}</span>
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-muted">{x.summary}</div>
                </button>
              </li>
            ))}
          </ul>
          <div>
            {other ? (
              <div>
                {row(
                  "",
                  <span className="font-mono text-xs">{c.tracking_code}</span>,
                  <span className="font-mono text-xs">{other.tracking_code}</span>,
                )}
                {row("Summary", c.summary, other.summary)}
                {row("People", c.people_count ?? "?", other.people_count ?? "?")}
                {row("Water", <WaterTag level={c.water_level} />, <WaterTag level={other.water_level} />)}
                {row("Where", c.address_text ?? c.locality, other.address_text ?? other.locality)}
                {row("Contact", c.contact_name ?? "None", other.contact_name ?? "None")}
                {row("Reports", c.source_count, other.source_count)}
              </div>
            ) : (
              <p className="pt-2 text-sm text-muted">Choose a case on the left to compare them side by side.</p>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

export function CaseDrawer({
  caseId,
  cases,
  teams,
  now,
  canEdit,
  water,
}: {
  caseId: string;
  cases: CaseOut[];
  teams: TeamOut[];
  now: number;
  canEdit: boolean;
  water: WaterField | null;
}) {
  const { data, isLoading, error, refetch } = useCase(caseId);
  const qc = useQueryClient();
  const { select, pinEdit, startPinEdit, endPinEdit, toast, fly } = useUi();
  const action = useCaseAction(caseId);
  const [assignOpen, setAssignOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [confirm, setConfirm] = useState<null | "false_alarm" | "closed" | "rescued">(null);
  const c = data;
  const editing = pinEdit?.caseId === caseId;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !assignOpen && !mergeOpen && !confirm) {
        if (editing) endPinEdit();
        else select(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [select, editing, endPinEdit, assignOpen, mergeOpen, confirm]);

  const patch = (body: Record<string, unknown>, success: string) =>
    action.mutate(() => api.patch(`/api/v1/cases/${caseId}`, { ...body, version: c?.version }), {
      onSuccess: () => {
        toast({ kind: "success", text: success });
        qc.invalidateQueries({ queryKey: ["review"] });
      },
    });

  const savePin = () => {
    if (!pinEdit) return;
    patch({ lat: pinEdit.lat, lng: pinEdit.lng }, "Location saved. The plan will update.");
    endPinEdit();
  };

  const team = c?.current_team_id ? teams.find((t) => t.id === c.current_team_id) : undefined;
  const activeAssignment = c?.assignments.find((a) => ["approved", "started", "reached"].includes(a.status));
  const reasons = c?.review_reasons ?? [];

  return (
    <aside
      aria-label="Case details"
      className="glass absolute inset-y-3 right-3 z-20 flex w-[min(440px,calc(100%-1.5rem))] flex-col overflow-hidden rounded-xl border border-line shadow-float animate-in"
    >
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        {c ? (
          <UrgencyPill level={c.urgency_level} score={c.urgency_score} size="md" />
        ) : (
          <Skeleton className="h-7 w-24" />
        )}
        {c ? <span className="font-mono text-xs text-muted">{c.tracking_code}</span> : null}
        {c ? <span className="text-xs text-muted">· {STATUS_LABEL[c.status]}</span> : null}
        <button
          type="button"
          onClick={() => select(null)}
          className="ml-auto rounded-md p-1 text-muted hover:bg-panel-2 hover:text-text"
          aria-label="Close case (Esc)"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-4 scroll-thin">
        {error ? <ErrorNote onRetry={() => refetch()}>Could not load this case.</ErrorNote> : null}
        {isLoading || !c ? (
          <div className="space-y-3">
            <Skeleton className="h-6 w-4/5" />
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <>
            <div className="space-y-2.5">
              <p className="text-[17px] font-medium leading-snug text-text">{c.summary || "No summary yet"}</p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
                <PeopleCount n={c.people_count} />
                <VulnIcons c={c} />
                <SourceCount n={c.source_count} />
                <span className="text-muted tnum">{ago(c.first_reported_at, now)} waiting</span>
              </div>
              {c.needs.length ? (
                <p className="text-xs text-muted">
                  Asks for{" "}
                  {c.needs
                    .map((n) => NEED_LABEL[n] ?? n)
                    .join(", ")
                    .toLowerCase()}
                </p>
              ) : null}
            </div>

            {reasons.length && canEdit ? (
              <div className="space-y-2 rounded-lg border border-medium/40 bg-medium/10 p-3">
                <p className="flex items-center gap-2 text-[13px] font-medium text-text">
                  <ShieldAlert className="size-4 text-medium" />
                  {reasons.map((r) => REASON_LABEL[r] ?? r).join(" · ")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {reasons.some((r) => r === "location_unknown" || r === "low_confidence_location") ? (
                    <Button
                      size="sm"
                      variant="subtle"
                      icon={<Crosshair className="size-3.5" />}
                      onClick={() => startPinEdit(c.id, c.lat ?? 13, c.lng ?? 80.2)}
                    >
                      Fix the pin
                    </Button>
                  ) : null}
                  {reasons.some((r) => r === "reported_rescued" || r === "possibly_rescued") ? (
                    <>
                      <Button size="sm" variant="go" onClick={() => setConfirm("rescued")}>
                        Confirm they're safe
                      </Button>
                      <Button
                        size="sm"
                        variant="subtle"
                        onClick={() =>
                          patch(
                            {
                              clear_reasons: ["reported_rescued", "possibly_rescued"],
                            },
                            "Kept open",
                          )
                        }
                      >
                        Keep open
                      </Button>
                    </>
                  ) : null}
                  {reasons.includes("possible_duplicate") ? (
                    <Button
                      size="sm"
                      variant="subtle"
                      icon={<GitMerge className="size-3.5" />}
                      onClick={() => setMergeOpen(true)}
                    >
                      Compare duplicates
                    </Button>
                  ) : null}
                  {reasons.includes("manual_reading") ||
                  reasons.includes("team_could_not_reach") ||
                  reasons.includes("reported_after_rescue") ||
                  reasons.includes("instructions_in_message") ? (
                    <Button
                      size="sm"
                      variant="subtle"
                      icon={<Check className="size-3.5" />}
                      onClick={() =>
                        patch(
                          {
                            clear_reasons: [
                              "manual_reading",
                              "team_could_not_reach",
                              "reported_after_rescue",
                              "instructions_in_message",
                            ],
                          },
                          "Marked as checked",
                        )
                      }
                    >
                      Mark checked
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}

            <Section title="Location" aside={<Confidence value={c.location_confidence} source={c.location_source} />}>
              <div className="space-y-2 text-[13px]">
                <p className="text-text">{c.address_text ?? "No address matched"}</p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  {c.locality ? <span>{c.locality}</span> : null}
                  {c.lat != null && c.lng != null ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-mono hover:text-text"
                      onClick={() => {
                        navigator.clipboard?.writeText(`${c.lat?.toFixed(5)}, ${c.lng?.toFixed(5)}`);
                        toast({ kind: "info", text: "Coordinates copied" });
                      }}
                      aria-label="Copy coordinates"
                    >
                      {c.lat.toFixed(5)}, {c.lng.toFixed(5)}
                      <Copy className="size-3" />
                    </button>
                  ) : null}
                  {c.in_flood_zone ? (
                    <span className="text-water">
                      In flood zone
                      {c.flood_depth_m ? `, ~${c.flood_depth_m.toFixed(1)} m` : ""}
                    </span>
                  ) : null}
                </div>
                {editing ? (
                  <div className="flex items-center gap-2 rounded-md border border-accent/50 bg-accent-soft px-3 py-2">
                    <MapPin className="size-4 text-accent-text" />
                    <span className="flex-1 text-xs">Click the map where the family is.</span>
                    <Button size="xs" variant="ghost" onClick={endPinEdit}>
                      Cancel
                    </Button>
                    <Button size="xs" onClick={savePin}>
                      Save pin
                    </Button>
                  </div>
                ) : canEdit ? (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="xs"
                      variant="subtle"
                      icon={<Crosshair className="size-3.5" />}
                      onClick={() => startPinEdit(c.id, c.lat ?? 13, c.lng ?? 80.2)}
                    >
                      Move pin
                    </Button>
                    {c.lat != null && c.lng != null ? (
                      <Button size="xs" variant="ghost" onClick={() => fly(c.lat as number, c.lng as number, 15)}>
                        Zoom to
                      </Button>
                    ) : null}
                  </div>
                ) : null}
                {c.location_candidates.length && !editing && canEdit ? (
                  <div className="space-y-1">
                    <p className="text-xs text-muted">Other places it could be</p>
                    {c.location_candidates.map((cand) => (
                      <button
                        key={`${cand.lat},${cand.lng}`}
                        type="button"
                        onClick={() => {
                          startPinEdit(c.id, cand.lat, cand.lng);
                          fly(cand.lat, cand.lng, 15);
                        }}
                        className="flex w-full items-center justify-between rounded-md border border-line px-2.5 py-1.5 text-left text-xs hover:border-line-strong"
                      >
                        <span className="truncate">{cand.label}</span>
                        <span className="text-muted tnum">{Math.round(cand.confidence * 100)}%</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </Section>

            <Section title="Team">
              {activeAssignment ? (
                <div className="rounded-lg border border-line p-3 text-[13px]">
                  <div className="flex items-center gap-2">
                    <Truck className="size-4 text-accent-text" />
                    <span className="font-mono font-medium">{activeAssignment.team_call_sign ?? team?.call_sign}</span>
                    <span className="text-muted">{STATUS_LABEL[c.status]}</span>
                    {activeAssignment.eta ? (
                      <span className="ml-auto text-muted tnum">ETA {clock(activeAssignment.eta)}</span>
                    ) : null}
                  </div>
                  {activeAssignment.reasons.length ? (
                    <ul className="mt-2 space-y-0.5 text-xs text-muted">
                      {activeAssignment.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  ) : null}
                  {canEdit ? (
                    <Button
                      size="xs"
                      variant="ghost"
                      className="mt-2 -ml-2"
                      icon={<Undo2 className="size-3.5" />}
                      onClick={() =>
                        action.mutate(() => api.post(`/api/v1/assignments/${activeAssignment.id}/cancel`), {
                          onSuccess: () =>
                            toast({
                              kind: "info",
                              text: "Assignment cancelled. The case is back in the queue.",
                            }),
                        })
                      }
                    >
                      Cancel assignment
                    </Button>
                  ) : null}
                </div>
              ) : (
                <p className="text-[13px] text-muted">
                  {c.status === "needs_review"
                    ? "Waiting for review before dispatch."
                    : "No team yet. The planner will propose one."}
                </p>
              )}
              {c.contact_phone ? (
                <a
                  href={`tel:${c.contact_phone}`}
                  className="inline-flex items-center gap-1.5 text-[13px] text-accent-text hover:underline"
                >
                  <Phone className="size-3.5" />
                  {c.contact_name ? `${c.contact_name}, ` : ""}
                  <span className="font-mono">{c.contact_phone}</span>
                </a>
              ) : null}
            </Section>

            {c.water_clock ? (
              <Section title="Water clock" aside="from the flood forecast">
                <WaterClock
                  c={c}
                  field={water}
                  now={now}
                  eta={activeAssignment?.eta}
                  team={activeAssignment?.team_call_sign ?? team?.call_sign}
                />
              </Section>
            ) : null}

            <Section title="Why this score" aside={<span className="tnum">{c.urgency_score} / 100</span>}>
              <ScoreBreakdown factors={c.score_breakdown} score={c.urgency_score} />
            </Section>

            <Section title={c.sources.length > 1 ? `${c.sources.length} reports` : "Report"}>
              <ul className="space-y-3">
                {c.sources.map((s) => (
                  <li key={s.id} className="rounded-lg border border-line p-3">
                    <div className="mb-1.5 flex items-center gap-2 text-xs text-muted">
                      <span className="text-text">{CHANNEL_LABEL[s.channel] ?? s.channel}</span>
                      <span className="tnum">{stamp(s.received_at)}</span>
                      {s.language && s.language !== "en" ? <span className="uppercase">{s.language}</span> : null}
                      <span className="ml-auto font-mono">{s.tracking_code}</span>
                    </div>
                    {s.text ? (
                      <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-text">{s.text}</p>
                    ) : (
                      <p className="text-[13px] text-muted">Message text is restricted for your role.</p>
                    )}
                    {s.provider === "local" && s.model ? null : s.model ? (
                      <p className="mt-1.5 text-[11px] text-faint">Read by {s.model}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Section>

            <Section title="History">
              <ol className="relative space-y-3 border-l border-line pl-4">
                {c.events.map((e) => (
                  <li key={e.id} className="text-[13px]">
                    <span className="absolute -left-[3.5px] mt-1.5 size-1.5 rounded-full bg-line-strong" aria-hidden />
                    <div className="text-text">{eventText(e)}</div>
                    <div className="text-xs text-muted">
                      {stamp(e.created_at)} · {e.actor_label ?? e.actor_type}
                    </div>
                  </li>
                ))}
              </ol>
            </Section>
          </>
        )}
      </div>

      {c && canEdit && !["rescued", "closed", "duplicate", "false_alarm"].includes(c.status) ? (
        <div className="flex items-center gap-2 border-t border-line px-4 py-3">
          <Button onClick={() => setAssignOpen(true)} disabled={c.lat == null}>
            {activeAssignment ? "Reassign" : "Assign team"}
          </Button>
          <Button variant="outline" onClick={() => setConfirm("rescued")}>
            Mark rescued
          </Button>
          <Menu
            trigger={<Button variant="ghost" aria-label="More actions" icon={<MoreHorizontal className="size-4" />} />}
          >
            <MenuItem icon={<GitMerge />} onSelect={() => setMergeOpen(true)}>
              Merge with another case
            </MenuItem>
            <MenuSeparator />
            <MenuItem onSelect={() => setConfirm("false_alarm")} danger>
              Mark as false alarm
            </MenuItem>
            <MenuItem onSelect={() => setConfirm("closed")} danger>
              Close case
            </MenuItem>
          </Menu>
        </div>
      ) : c?.status === "duplicate" && canEdit ? (
        <div className="flex items-center gap-2 border-t border-line px-4 py-3">
          <Button
            variant="outline"
            icon={<Undo2 className="size-4" />}
            onClick={() =>
              action.mutate(() => api.post(`/api/v1/cases/${c.id}/unmerge`), {
                onSuccess: () => toast({ kind: "success", text: "Merge undone" }),
              })
            }
          >
            Undo merge
          </Button>
        </div>
      ) : null}

      {c ? (
        <>
          <AssignDialog c={c} teams={teams} open={assignOpen} onOpenChange={setAssignOpen} />
          <MergeDialog c={c} cases={cases} open={mergeOpen} onOpenChange={setMergeOpen} />
          <Dialog
            open={confirm !== null}
            onOpenChange={(v) => !v && setConfirm(null)}
            size="sm"
            title={
              confirm === "rescued"
                ? "Mark as rescued?"
                : confirm === "false_alarm"
                  ? "Mark as a false alarm?"
                  : "Close this case?"
            }
            description={
              confirm === "rescued"
                ? "Any team on the way is stood down and the reporter is told."
                : "The case leaves the queue and any assigned team is stood down."
            }
            footer={
              <>
                <Button variant="ghost" onClick={() => setConfirm(null)}>
                  Keep it open
                </Button>
                <Button
                  variant={confirm === "rescued" ? "go" : "danger"}
                  loading={action.isPending}
                  onClick={() => {
                    if (!confirm) return;
                    patch({ status: confirm }, confirm === "rescued" ? "Marked rescued" : "Case closed");
                    setConfirm(null);
                  }}
                >
                  {confirm === "rescued"
                    ? "Mark rescued"
                    : confirm === "false_alarm"
                      ? "Mark false alarm"
                      : "Close case"}
                </Button>
              </>
            }
          />
        </>
      ) : null}
    </aside>
  );
}
