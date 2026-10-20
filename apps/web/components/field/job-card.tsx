"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Minus, Navigation, Phone, Plus, Waves } from "lucide-react";
import Link from "next/link";
import { Dialog as D } from "radix-ui";
import { useState } from "react";
import { PeopleCount, UrgencyPill, VulnIcons, WaterTag } from "@/components/domain";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { ApiError, type Job } from "@/lib/api";
import { ago, clock, cn, km } from "@/lib/format";
import { newClientId, sendOrQueue } from "@/lib/offline";
import { useUi } from "@/lib/store";
import { clockLeft } from "@/lib/water";
import { useField } from "./shell";

type Status = "started" | "reached" | "completed" | "failed";

const CLOSED = { completed: "jobDone", failed: "jobFailed", cancelled: "jobCancelled" } as const;

function Sheet({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <D.Content className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl bg-bg px-5 pt-5 pb-[max(env(safe-area-inset-bottom),1.25rem)] text-text shadow-float animate-in">
          <D.Title className="text-[18px] font-semibold">{title}</D.Title>
          <div className="mt-4">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

export function JobCard({ job, primary = true }: { job: Job; primary?: boolean }) {
  const { t } = useField();
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const { assignment: a, case: c } = job;
  const [busy, setBusy] = useState(false);
  const [rescueOpen, setRescueOpen] = useState(false);
  const [failOpen, setFailOpen] = useState(false);
  const [count, setCount] = useState(c.people_count ?? 1);
  const [reason, setReason] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const now = Date.now();
  // the water clock, and whether this crew beats the water there
  const left = a.status in CLOSED ? null : clockLeft(c.water_clock, now);
  const due = left != null ? now + left * 60_000 : null;
  const margin = due != null && a.eta ? Math.round((due - new Date(a.eta).getTime()) / 60_000) : null;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["field-now"] });
    qc.invalidateQueries({ queryKey: ["field-job", a.id] });
  };

  const update = async (status: Status, extra: Record<string, unknown> = {}) => {
    setBusy(true);
    try {
      const r = await sendOrQueue(`/api/v1/field/assignments/${a.id}`, "PATCH", {
        status,
        client_id: newClientId(),
        at: new Date().toISOString(),
        ...extra,
      });
      // optimistic: the crew sees the next button even before the signal comes back,
      // on the home card and on this job's own page alike
      const done = status === "completed" || status === "failed";
      const advance = (j: Job): Job => ({ ...j, assignment: { ...j.assignment, status } });
      qc.setQueryData(["field-now"], (old: unknown) => {
        const o = old as { current?: Job } | undefined;
        if (!o?.current || o.current.assignment.id !== a.id) return old;
        return { ...o, current: done ? null : advance(o.current) };
      });
      qc.setQueryData(["field-job", a.id], (old: Job | undefined) => (old ? advance(old) : old));
      if (r === "sent") refresh();
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Could not send",
      });
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const directions =
    c.lat != null && c.lng != null
      ? `https://www.google.com/maps/dir/?api=1&destination=${c.lat},${c.lng}&travelmode=driving`
      : null;
  const reasons = [
    ["deep", t("tooDeep")],
    ["blocked", t("blocked")],
    ["missing", t("notFoundPeople")],
    ["other", t("otherReason")],
  ] as const;

  return (
    <article
      className={
        primary
          ? "rounded-2xl border border-line bg-raised p-5 shadow-card"
          : "rounded-2xl border border-line bg-panel p-4"
      }
    >
      <div className="flex items-center gap-2">
        <UrgencyPill level={c.urgency_level} score={c.urgency_score} size="md" />
        <span className="font-mono text-[13px] text-muted">{c.tracking_code}</span>
        <span className="ml-auto text-[13px] text-muted tnum">
          {t("waiting", { t: ago(c.first_reported_at, now) })}
        </span>
      </div>
      <p className={primary ? "mt-3 text-[20px] font-semibold leading-snug" : "mt-2 text-[16px] font-medium"}>
        {c.summary}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[15px]">
        <PeopleCount n={c.people_count} />
        <VulnIcons c={c} />
        <WaterTag level={c.water_level} rising={c.water_rising} />
      </div>
      <p className="mt-3 text-[16px] text-text">{c.address_text ?? c.locality ?? "Location being confirmed"}</p>
      <p className="mt-1 text-[14px] text-muted tnum">
        {a.eta ? `ETA ${clock(a.eta)}` : ""}
        {a.distance_m ? ` · ${km(a.distance_m)}` : ""}
      </p>
      {left != null ? (
        <output
          className={cn(
            "mt-3 block rounded-lg px-4 py-3 text-[15px] font-medium",
            left < 60 ? "bg-critical/10 text-critical" : "bg-panel text-text",
          )}
        >
          <p className="flex items-center gap-2">
            <Waves className="size-4 shrink-0" aria-hidden="true" />
            {left < 1 ? t("waterNow") : t("waterClock", { m: Math.round(left) })}
          </p>
          {margin != null ? (
            <p className="mt-1 text-[14px] font-normal text-muted">
              {margin >= 0 ? t("beforeWater", { m: margin }) : t("afterWater", { m: -margin })}
            </p>
          ) : null}
        </output>
      ) : null}

      {primary && a.status in CLOSED ? (
        <p className="mt-4 rounded-lg bg-panel px-4 py-3 text-[15px] text-muted">
          {t(CLOSED[a.status as keyof typeof CLOSED])}
        </p>
      ) : primary ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {c.contact_phone ? (
              <a
                href={`tel:${c.contact_phone}`}
                className="flex h-12 items-center justify-center gap-2 rounded-lg border border-line-strong text-[15px] font-medium"
              >
                <Phone className="size-4" /> {t("callFamily")}
              </a>
            ) : null}
            {directions ? (
              <a
                href={directions}
                target="_blank"
                rel="noopener"
                className={`flex h-12 items-center justify-center gap-2 rounded-lg border border-line-strong text-[15px] font-medium ${c.contact_phone ? "" : "col-span-2"}`}
              >
                <Navigation className="size-4" /> {t("navigate")}
              </a>
            ) : null}
          </div>
          <div className="mt-4 space-y-3">
            {a.status === "approved" ? (
              <Button size="xl" loading={busy} onClick={() => update("started")}>
                {t("start")}
              </Button>
            ) : a.status === "started" ? (
              <Button size="xl" loading={busy} onClick={() => update("reached")}>
                {t("reached")}
              </Button>
            ) : (
              <Button size="xl" variant="go" loading={busy} onClick={() => setRescueOpen(true)}>
                {t("rescued")}
              </Button>
            )}
            <Button size="xl" variant="danger" onClick={() => setFailOpen(true)}>
              {t("cantReach")}
            </Button>
          </div>
          <Link
            href={`/field/assignment/${a.id}`}
            className="mt-4 block text-center text-[15px] font-medium text-accent-text"
          >
            {t("details")}
          </Link>
        </>
      ) : null}

      <Sheet open={rescueOpen} onOpenChange={setRescueOpen} title={t("howMany")}>
        <div className="flex items-center justify-center gap-6">
          <button
            type="button"
            aria-label="One fewer"
            onClick={() => setCount((n) => Math.max(0, n - 1))}
            className="grid size-14 place-items-center rounded-full border border-line-strong"
          >
            <Minus className="size-6" />
          </button>
          <span className="w-20 text-center text-[44px] font-semibold tnum" aria-live="polite">
            {count}
          </span>
          <button
            type="button"
            aria-label="One more"
            onClick={() => setCount((n) => n + 1)}
            className="grid size-14 place-items-center rounded-full border border-line-strong"
          >
            <Plus className="size-6" />
          </button>
        </div>
        <div className="mt-6 space-y-3">
          <Button
            size="xl"
            variant="go"
            loading={busy}
            onClick={async () => {
              await update("completed", { people_rescued: count });
              setRescueOpen(false);
            }}
          >
            {t("confirmRescue")}
          </Button>
          <Button size="xl" variant="ghost" onClick={() => setRescueOpen(false)}>
            {t("cancel")}
          </Button>
        </div>
      </Sheet>

      <Sheet open={failOpen} onOpenChange={setFailOpen} title={t("whyNot")}>
        <fieldset className="grid min-w-0 gap-2">
          <legend className="sr-only">{t("whyNot")}</legend>
          {reasons.map(([key, label]) => (
            <label
              key={key}
              className={`flex h-12 cursor-pointer items-center rounded-lg border px-4 text-[16px] has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${reason === label ? "border-accent bg-accent-soft font-medium" : "border-line-strong"}`}
            >
              <input
                type="radio"
                name="fail-reason"
                className="sr-only"
                checked={reason === label}
                onChange={() => setReason(label)}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <Textarea
          className="mt-3 text-[16px]"
          rows={2}
          placeholder={t("noteHint")}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="mt-4 space-y-3">
          <Button
            size="xl"
            variant="danger"
            disabled={!reason}
            loading={busy}
            onClick={async () => {
              await update("failed", {
                note: [reason, note].filter(Boolean).join(". "),
              });
              setFailOpen(false);
            }}
          >
            {t("sendUpdate")}
          </Button>
          <Button size="xl" variant="ghost" onClick={() => setFailOpen(false)}>
            {t("cancel")}
          </Button>
        </div>
      </Sheet>
    </article>
  );
}
