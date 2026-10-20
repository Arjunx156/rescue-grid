"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Anchor, Footprints, HeartPulse, Navigation, Plane, Plus, Truck } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { useShell } from "@/components/command/context";
import { SidePanel } from "@/components/command/panel";
import { Empty } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input, Select } from "@/components/ui/field";
import { Dialog } from "@/components/ui/overlay";
import { ApiError, api, type TeamOut } from "@/lib/api";
import { ASSET_LABEL, ago, cn, TEAM_STATUS_LABEL } from "@/lib/format";
import { keys } from "@/lib/queries";
import { useUi } from "@/lib/store";

const ASSET_ICON: Record<string, typeof Truck> = {
  boat: Anchor,
  truck: Truck,
  medical: HeartPulse,
  foot: Footprints,
  helicopter: Plane,
};

const ORDER = ["en_route", "on_scene", "assigned", "available", "returning", "off_duty"];

function RegisterTeam({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const { disasterId, disaster } = useShell();
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [form, setForm] = useState({
    call_sign: "",
    asset_type: "boat",
    capacity: "6",
    lead_name: "",
    lead_phone: "",
    base_name: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const center = disaster?.center;
    try {
      await api.post("/api/v1/teams", {
        disaster_id: disasterId,
        call_sign: form.call_sign,
        asset_type: form.asset_type,
        capacity: Number(form.capacity),
        lead_name: form.lead_name || null,
        lead_phone: form.lead_phone || null,
        base_name: form.base_name || null,
        lat: center?.[0] ?? null,
        lng: center?.[1] ?? null,
      });
      qc.invalidateQueries({ queryKey: keys.teams(disasterId ?? "") });
      toast({
        kind: "success",
        text: `${form.call_sign.toUpperCase()} registered. The lead can sign in with their phone.`,
      });
      onOpenChange(false);
      setForm({
        call_sign: "",
        asset_type: "boat",
        capacity: "6",
        lead_name: "",
        lead_phone: "",
        base_name: "",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not register the team");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Register a team"
      description="The lead signs in to the field app with this phone number and a one-time code."
    >
      <form id="register-team" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <FormRow label="Call sign" htmlFor="call">
          <Input
            id="call"
            required
            maxLength={16}
            placeholder="B-12"
            value={form.call_sign}
            onChange={set("call_sign")}
          />
        </FormRow>
        <FormRow label="Asset" htmlFor="asset">
          <Select id="asset" value={form.asset_type} onChange={set("asset_type")}>
            {Object.entries(ASSET_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </FormRow>
        <FormRow label="People per trip" htmlFor="cap">
          <Input id="cap" type="number" min={1} max={100} required value={form.capacity} onChange={set("capacity")} />
        </FormRow>
        <FormRow label="Base or relief camp" htmlFor="base" hint="Optional">
          <Input id="base" value={form.base_name} onChange={set("base_name")} />
        </FormRow>
        <FormRow label="Lead's name" htmlFor="lname">
          <Input id="lname" value={form.lead_name} onChange={set("lead_name")} />
        </FormRow>
        <FormRow label="Lead's phone" htmlFor="lphone" hint="WhatsApp number for sign-in codes">
          <Input id="lphone" type="tel" value={form.lead_phone} onChange={set("lead_phone")} />
        </FormRow>
        {error ? <p className="text-[13px] text-critical sm:col-span-2">{error}</p> : null}
        <div className="flex justify-end gap-2 sm:col-span-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" loading={busy}>
            Register team
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export default function TeamsPage() {
  const { teams, cases, now, canEdit, disasterId } = useShell();
  const { fly, select, toast } = useUi();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const caseById = useMemo(() => new Map(cases.map((c) => [c.id, c])), [cases]);
  const sorted = useMemo(
    () =>
      [...teams].sort(
        (a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || a.call_sign.localeCompare(b.call_sign),
      ),
    [teams],
  );
  const onDuty = teams.filter((t) => t.status !== "off_duty").length;

  const duty = async (t: TeamOut, on: boolean) => {
    try {
      await api.patch(`/api/v1/teams/${t.id}`, {
        status: on ? "available" : "off_duty",
      });
      qc.invalidateQueries({ queryKey: keys.teams(disasterId ?? "") });
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Could not change duty",
      });
    }
  };

  return (
    <SidePanel
      title="Teams"
      aside={
        <>
          <span className="tnum">
            {onDuty} of {teams.length} on duty
          </span>
          {canEdit ? (
            <Button size="xs" variant="subtle" icon={<Plus className="size-3.5" />} onClick={() => setOpen(true)}>
              Register
            </Button>
          ) : null}
        </>
      }
    >
      {onDuty === 0 && teams.length > 0 ? (
        <output className="m-3 block rounded-lg border border-medium/40 bg-medium/10 px-3 py-2 text-[13px]">
          No teams available. Dispatch is paused until a team goes on duty.
        </output>
      ) : null}
      {teams.length === 0 ? (
        <Empty title="No teams yet" body="Register boats, trucks and medical teams so the planner can dispatch them." />
      ) : (
        <ul>
          {sorted.map((t) => {
            const Icon = ASSET_ICON[t.asset_type] ?? Navigation;
            const job = t.active_case_id ? caseById.get(t.active_case_id) : undefined;
            const busy = ["assigned", "en_route", "on_scene"].includes(t.status);
            return (
              <li key={t.id} className="border-b border-line px-4 py-3 last:border-0">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => t.lat != null && t.lng != null && fly(t.lat, t.lng, 14)}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                    aria-label={`Show ${t.call_sign} on the map`}
                  >
                    <span
                      className={cn(
                        "grid size-8 shrink-0 place-items-center rounded-md border",
                        busy ? "border-signal/50 text-accent-text" : "border-line text-muted",
                      )}
                    >
                      <Icon className="size-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-2 text-[13px]">
                        <span className="font-mono font-medium">{t.call_sign}</span>
                        <span
                          className={cn(t.status === "off_duty" ? "text-faint" : busy ? "text-accent-text" : "text-go")}
                        >
                          {TEAM_STATUS_LABEL[t.status]}
                        </span>
                      </span>
                      <span className="block truncate text-xs text-muted">
                        {ASSET_LABEL[t.asset_type]}, carries {t.capacity}
                        {t.organization ? ` · ${t.organization}` : ""}
                      </span>
                    </span>
                  </button>
                  {canEdit && !busy ? (
                    <label className="flex items-center gap-2 text-xs text-muted">
                      On duty
                      <input
                        type="checkbox"
                        className="accent-[var(--focus)]"
                        checked={t.status !== "off_duty"}
                        onChange={(e) => duty(t, e.target.checked)}
                      />
                    </label>
                  ) : null}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 pl-11 text-xs text-muted">
                  {job ? (
                    <button
                      type="button"
                      onClick={() => select(job.id)}
                      className="truncate text-left text-text hover:underline"
                    >
                      {job.tracking_code} · {job.summary}
                    </button>
                  ) : null}
                  {t.queued ? <span>{t.queued} more queued</span> : null}
                  {t.location_updated_at ? (
                    <span className="tnum">Seen {ago(t.location_updated_at, now)} ago</span>
                  ) : (
                    <span>No location yet</span>
                  )}
                  {t.lead_name ? (
                    <span>
                      {t.lead_name}
                      {t.lead_phone ? (
                        <a href={`tel:${t.lead_phone}`} className="ml-1 font-mono text-accent-text hover:underline">
                          {t.lead_phone}
                        </a>
                      ) : null}
                    </span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <RegisterTeam open={open} onOpenChange={setOpen} />
    </SidePanel>
  );
}
