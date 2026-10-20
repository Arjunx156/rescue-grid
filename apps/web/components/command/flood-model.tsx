"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ShieldCheck, ShieldX, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FormRow, Input } from "@/components/ui/field";
import { ApiError, api, type DisasterOut, type FloodModelIn, type FloodModelOut } from "@/lib/api";
import { keys, useWater } from "@/lib/queries";
import { useUi } from "@/lib/store";

type Release = NonNullable<FloodModelIn["releases"]>[number];

function num(v: string, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/** What the reports have taught the ensemble: the weighted forcing scale, against the forecast. */
function learned(members: { rain: number; release: number; weight: number }[]) {
  const rain = members.reduce((s, m) => s + m.rain * m.weight, 0);
  const release = members.reduce((s, m) => s + m.release * m.weight, 0);
  return { rain, release };
}

/**
 * The water clock's inputs for a live disaster: the rain and the reservoir releases the control
 * room hears about. The reports correct them; this panel says by how much.
 */
export function FloodModel({ disaster }: { disaster: DisasterOut }) {
  const water = useWater(disaster.id);
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const current = water.data?.forcing;
  const [rainNow, setRainNow] = useState("");
  const [rainNext, setRainNext] = useState("");
  const [sea, setSea] = useState("0.4");
  const [releases, setReleases] = useState<Release[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!current) return;
    setRainNow(String(current.rain_now_mm_h));
    setRainNext(String(current.rain_next_mm_h));
    setSea(String(current.sea_level_m));
    setReleases(current.releases);
  }, [current]);

  const save = async () => {
    setBusy(true);
    try {
      const body: FloodModelIn = {
        rain_now_mm_h: num(rainNow),
        rain_next_mm_h: num(rainNext),
        sea_level_m: num(sea, 0.4),
        releases,
      };
      await api.put<FloodModelOut>(`/api/v1/disasters/${disaster.id}/flood-model`, body);
      await qc.invalidateQueries({ queryKey: keys.water(disaster.id) });
      toast({ kind: "success", text: "Saved. The next forecast uses it, and every water clock follows." });
    } catch (e) {
      toast({ kind: "error", text: e instanceof ApiError ? e.message : "Could not save the flood model" });
    } finally {
      setBusy(false);
    }
  };

  const forecast = water.data?.forecast;
  const lesson = forecast?.members.length ? learned(forecast.members) : null;
  const [lat, lng] = (disaster.center ?? [13, 80.2]) as [number, number];

  return (
    <section className="rounded-xl border border-line bg-panel p-5">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-[15px] font-semibold">Flood model</h2>
        <span className="text-xs text-muted">
          {water.data?.available
            ? `Forecasting three hours ahead from ${forecast?.reports_used.toLocaleString("en-IN")} reports of water depth.`
            : (water.data?.reason ?? "Checking the model…")}
        </span>
      </div>
      {lesson ? (
        <p className="mt-3 max-w-2xl text-[13px] text-muted">
          The reports point to about <span className="font-medium text-text tnum">{lesson.rain.toFixed(1)}×</span> the
          forecast rain and <span className="font-medium text-text tnum">{lesson.release.toFixed(1)}×</span> the
          forecast releases. If that holds, update the numbers below.
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <FormRow label="Rain now (mm/h)" htmlFor="rain-now">
          <Input
            id="rain-now"
            type="number"
            min={0}
            max={300}
            step={1}
            value={rainNow}
            onChange={(e) => setRainNow(e.target.value)}
            className="w-32"
          />
        </FormRow>
        <FormRow label="Rain in 3 hours (mm/h)" htmlFor="rain-next">
          <Input
            id="rain-next"
            type="number"
            min={0}
            max={300}
            step={1}
            value={rainNext}
            onChange={(e) => setRainNext(e.target.value)}
            className="w-32"
          />
        </FormRow>
        <FormRow label="Sea level (m)" htmlFor="sea">
          <Input
            id="sea"
            type="number"
            min={-1}
            max={3}
            step={0.1}
            value={sea}
            onChange={(e) => setSea(e.target.value)}
            className="w-28"
          />
        </FormRow>
      </div>
      <div className="mt-5">
        <div className="flex items-center gap-2">
          <h3 className="text-[13px] font-semibold">Reservoir and river releases</h3>
          <span className="text-xs text-muted">Placed on the nearest river. Cubic metres a second.</span>
          <Button
            size="xs"
            variant="ghost"
            className="ml-auto"
            icon={<Plus className="size-3.5" />}
            disabled={releases.length >= 8}
            onClick={() => setReleases((r) => [...r, { name: "", lat, lng, now_m3s: 0, next_m3s: 0 }])}
          >
            Add a release
          </Button>
        </div>
        {releases.length ? (
          <ul className="mt-2 space-y-2">
            {releases.map((r, i) => {
              const set = (patch: Partial<Release>) =>
                setReleases((all) => all.map((x, k) => (k === i ? { ...x, ...patch } : x)));
              const id = `release-${i}`;
              return (
                // releases have no id until saved; their order is their identity here
                // biome-ignore lint/suspicious/noArrayIndexKey: see above
                <li key={i} className="flex flex-wrap items-end gap-2">
                  <FormRow label="Name" htmlFor={`${id}-name`}>
                    <Input
                      id={`${id}-name`}
                      value={r.name}
                      onChange={(e) => set({ name: e.target.value })}
                      placeholder="Chembarambakkam lake"
                      className="w-56"
                    />
                  </FormRow>
                  <FormRow label="Latitude" htmlFor={`${id}-lat`}>
                    <Input
                      id={`${id}-lat`}
                      type="number"
                      step={0.0001}
                      value={r.lat}
                      onChange={(e) => set({ lat: num(e.target.value) })}
                      className="w-28"
                    />
                  </FormRow>
                  <FormRow label="Longitude" htmlFor={`${id}-lng`}>
                    <Input
                      id={`${id}-lng`}
                      type="number"
                      step={0.0001}
                      value={r.lng}
                      onChange={(e) => set({ lng: num(e.target.value) })}
                      className="w-28"
                    />
                  </FormRow>
                  <FormRow label="Now" htmlFor={`${id}-now`}>
                    <Input
                      id={`${id}-now`}
                      type="number"
                      min={0}
                      step={10}
                      value={r.now_m3s}
                      onChange={(e) => set({ now_m3s: num(e.target.value) })}
                      className="w-24"
                    />
                  </FormRow>
                  <FormRow label="In 6 hours" htmlFor={`${id}-next`}>
                    <Input
                      id={`${id}-next`}
                      type="number"
                      min={0}
                      step={10}
                      value={r.next_m3s}
                      onChange={(e) => set({ next_m3s: num(e.target.value) })}
                      className="w-24"
                    />
                  </FormRow>
                  <button
                    type="button"
                    aria-label={`Remove ${r.name || "this release"}`}
                    onClick={() => setReleases((all) => all.filter((_, k) => k !== i))}
                    className="mb-1.5 rounded p-1.5 text-muted hover:text-critical"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="mt-2 text-[13px] text-muted">No releases. The model floods from rain alone.</p>
        )}
      </div>
      <div className="mt-5 flex items-center gap-3">
        <Button onClick={save} loading={busy} disabled={releases.some((r) => !r.name.trim())}>
          Save flood model
        </Button>
        <span className="text-xs text-faint">
          What already happened stays as it was; the new numbers apply from now.
        </span>
      </div>
    </section>
  );
}

interface AuditOut {
  events: number;
  intact: boolean;
  head: string;
  break_at: number | null;
  reason: string | null;
}

/** The audit chain, recomputed on demand: every event intact, or exactly where it broke. */
export function AuditTrail({ disaster }: { disaster: DisasterOut }) {
  const q = useQuery({
    queryKey: ["audit", disaster.id],
    queryFn: () => api.get<AuditOut>(`/api/v1/admin/audit?disaster_id=${disaster.id}`),
    staleTime: 60_000,
  });
  const r = q.data;
  return (
    <section className="rounded-xl border border-line bg-panel p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[15px] font-semibold">Audit trail</h2>
        <span className="text-xs text-muted">
          Every change is chained to the one before it inside the database. Edits are refused; a deletion shows here.
        </span>
        <Button size="sm" variant="subtle" className="ml-auto" loading={q.isFetching} onClick={() => q.refetch()}>
          Verify again
        </Button>
      </div>
      {r ? (
        <div className="mt-4 flex items-start gap-3 text-[13px]">
          {r.intact ? (
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-go" aria-hidden="true" />
          ) : (
            <ShieldX className="mt-0.5 size-4 shrink-0 text-critical" aria-hidden="true" />
          )}
          <div>
            <p className={r.intact ? "text-text" : "font-medium text-critical"}>
              {r.intact
                ? `${r.events.toLocaleString("en-IN")} events, chain intact.`
                : `Broken at event ${r.break_at}: ${r.reason}.`}
            </p>
            {r.head ? (
              <p className="mt-1 font-mono text-xs break-all text-faint">
                Latest link {r.head.slice(0, 16)}…{r.head.slice(-8)}
              </p>
            ) : null}
          </div>
        </div>
      ) : q.isError ? (
        <p className="mt-4 text-[13px] text-critical">Could not check the chain. Try again.</p>
      ) : null}
    </section>
  );
}
