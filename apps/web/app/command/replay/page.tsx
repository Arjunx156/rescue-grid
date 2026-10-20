"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Square } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useShell } from "@/components/command/context";
import { SidePanel } from "@/components/command/panel";
import { ErrorNote, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { ApiError, api, type DisasterOut } from "@/lib/api";
import { clock, cn, stamp } from "@/lib/format";
import { keys, type ReplayState, useDisasterId, useReplayState } from "@/lib/queries";
import { useUi } from "@/lib/store";

interface Dataset {
  slug: string;
  name: string;
  description: string;
  starts_at: string;
  ends_at: string;
  message_count: number;
  household_count: number;
}

interface Bench {
  policies: Record<string, { label: string; metrics: Record<string, number | null> }>;
  comparison: {
    critical_reached_3h_gain_pct: number;
    wasted_trips_avoided: number;
  };
}

const SPEEDS = [30, 60, 120, 300];

function Row({ label, a, b }: { label: string; a: string; b: string }) {
  return (
    <div className="grid grid-cols-[1fr_5.5rem_5.5rem] items-baseline gap-2 border-b border-line py-2 text-[13px] last:border-0">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium tnum">{a}</span>
      <span className="text-right text-muted tnum">{b}</span>
    </div>
  );
}

export default function ReplayPage() {
  const { canEdit } = useShell();
  const [, setDisaster, disaster] = useDisasterId();
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [speed, setSpeed] = useState(60);
  const [autopilot, setAutopilot] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const datasets = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.get<Dataset[]>("/api/v1/replay/datasets"),
  });
  const bench = useQuery({
    queryKey: ["bench"],
    queryFn: () => api.get<Bench>("/api/v1/replay/benchmark"),
    retry: false,
  });
  const isReplay = disaster?.status === "replay";
  const state = useReplayState(disaster).data;

  const start = async (slug: string) => {
    setBusy("start");
    try {
      const r = await api.post<{ disaster: DisasterOut; state: ReplayState }>("/api/v1/replay/start", {
        dataset: slug,
        speed,
        autopilot,
      });
      await qc.invalidateQueries({ queryKey: keys.disasters });
      qc.setQueryData(keys.replay(r.disaster.id), r.state);
      setDisaster(r.disaster.id);
      toast({
        kind: "success",
        text: "Replay started. Messages are arriving on the map.",
      });
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Could not start the replay",
      });
    } finally {
      setBusy(null);
    }
  };
  const control = async (action: "pause" | "resume" | "stop") => {
    if (!disaster) return;
    setBusy(action);
    try {
      const s = await api.post<ReplayState>(`/api/v1/replay/${disaster.id}/${action}`);
      qc.setQueryData(keys.replay(disaster.id), s);
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "That did not work",
      });
    } finally {
      setBusy(null);
    }
  };
  const changeSpeed = async (v: number) => {
    setSpeed(v);
    if (!isReplay || !disaster) return;
    const s = await api
      .post<ReplayState>(`/api/v1/replay/${disaster.id}/speed/set`, {
        speed: v,
      })
      .catch(() => null);
    if (s) qc.setQueryData(keys.replay(disaster.id), s);
  };

  const rg = bench.data?.policies.rescue_grid?.metrics;
  const fc = bench.data?.policies.fcfs?.metrics;

  return (
    <SidePanel
      title="Disaster replay"
      aside={isReplay && state ? <span className="capitalize">{state.status}</span> : null}
    >
      <div className="space-y-6 p-4">
        {isReplay && state ? (
          <section className="space-y-3">
            <p className="text-[13px] text-muted">{disaster?.name}</p>
            <div>
              <div className="flex items-baseline justify-between text-xs text-muted">
                <span className="font-mono text-[22px] text-text tnum">{clock(state.sim_now)}</span>
                <span className="tnum">
                  {state.emitted.toLocaleString("en-IN")} of {state.total.toLocaleString("en-IN")} messages
                </span>
              </div>
              <div
                className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel-2"
                role="progressbar"
                aria-valuenow={Math.round(state.progress * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Replay progress"
              >
                <div
                  className="h-full rounded-full bg-signal transition-[width] duration-700"
                  style={{ width: `${state.progress * 100}%` }}
                />
              </div>
              <p className="mt-1.5 text-xs text-faint">
                {stamp(state.starts_at)} to {stamp(state.ends_at)} IST
              </p>
            </div>
            {canEdit ? (
              <div className="flex items-center gap-2">
                {state.status === "playing" ? (
                  <Button
                    variant="outline"
                    icon={<Pause className="size-4" />}
                    loading={busy === "pause"}
                    onClick={() => control("pause")}
                  >
                    Pause
                  </Button>
                ) : state.status === "paused" ? (
                  <Button
                    icon={<Play className="size-4" />}
                    loading={busy === "resume"}
                    onClick={() => control("resume")}
                  >
                    Resume
                  </Button>
                ) : null}
                <Select
                  value={state.speed}
                  onChange={(e) => changeSpeed(Number(e.target.value))}
                  className="w-24"
                  aria-label="Speed"
                >
                  {SPEEDS.map((s) => (
                    <option key={s} value={s}>
                      {s}x
                    </option>
                  ))}
                </Select>
                {state.status !== "finished" ? (
                  <Button
                    variant="ghost"
                    icon={<Square className="size-3.5" />}
                    loading={busy === "stop"}
                    onClick={() => control("stop")}
                  >
                    Stop
                  </Button>
                ) : null}
              </div>
            ) : null}
            <p className="text-xs text-muted">
              {state.autopilot
                ? "Autopilot approves each plan for the simulated crews, so the loop runs on its own. Review cases still wait for you."
                : "Plans wait for your approval on the Dispatch page."}
            </p>
          </section>
        ) : null}

        <section className="space-y-3">
          <h2 className="text-[13px] font-semibold">{isReplay ? "Start again" : "Choose a dataset"}</h2>
          {datasets.isLoading ? <Skeleton className="h-32" /> : null}
          {datasets.error ? <ErrorNote>Could not list datasets.</ErrorNote> : null}
          {datasets.data?.map((d) => (
            <article key={d.slug} className="rounded-lg border border-line p-3.5">
              <h3 className="text-[14px] font-medium">{d.name}</h3>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">{d.description}</p>
              <p className="mt-2 text-xs text-faint tnum">
                {d.message_count.toLocaleString("en-IN")} messages · {d.household_count} households ·{" "}
                {stamp(d.starts_at)} onward
              </p>
              {canEdit ? (
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <Select
                    value={speed}
                    onChange={(e) => setSpeed(Number(e.target.value))}
                    className="w-24"
                    aria-label="Replay speed"
                  >
                    {SPEEDS.map((s) => (
                      <option key={s} value={s}>
                        {s}x
                      </option>
                    ))}
                  </Select>
                  <label className="flex items-center gap-2 text-[13px] text-muted">
                    <input
                      type="checkbox"
                      className="accent-[var(--focus)]"
                      checked={autopilot}
                      onChange={(e) => setAutopilot(e.target.checked)}
                    />
                    Autopilot
                  </label>
                  <Button
                    className="ml-auto"
                    icon={<Play className="size-4" />}
                    loading={busy === "start"}
                    onClick={() => start(d.slug)}
                  >
                    {isReplay ? "Restart replay" : "Start replay"}
                  </Button>
                </div>
              ) : null}
            </article>
          ))}
        </section>

        {rg && fc ? (
          <section className="space-y-2">
            <h2 className="text-[13px] font-semibold">Same 48 hours, two ways</h2>
            <p className="text-xs text-muted">
              A simulation on this dataset with the same 28 teams and ground truth. Rescue Grid against answering
              messages in the order they arrive.
            </p>
            <div className="rounded-lg border border-line px-3">
              <div className="grid grid-cols-[1fr_5.5rem_5.5rem] gap-2 border-b border-line py-2 text-xs text-muted">
                <span />
                <span className="text-right">Rescue Grid</span>
                <span className="text-right">In order</span>
              </div>
              <Row label="Critical reached in 3 h" a={`${rg.critical_reached_3h}`} b={`${fc.critical_reached_3h}`} />
              <Row label="Households reached" a={`${rg.households_reached}`} b={`${fc.households_reached}`} />
              <Row
                label="People rescued"
                a={`${rg.people_rescued?.toLocaleString("en-IN")}`}
                b={`${fc.people_rescued?.toLocaleString("en-IN")}`}
              />
              <Row
                label="Median to a team, critical"
                a={`${Math.round(rg.median_minutes_to_assign_critical ?? 0)} min`}
                b={`${Math.round(fc.median_minutes_to_assign_critical ?? 0)} min`}
              />
              <Row label="Wasted trips" a={`${rg.wasted_trips}`} b={`${fc.wasted_trips}`} />
            </div>
            <Link href="/#replay" className={cn("inline-block text-[13px] text-accent-text hover:underline")}>
              Watch them side by side
            </Link>
          </section>
        ) : null}
      </div>
    </SidePanel>
  );
}
