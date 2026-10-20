"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Crosshair, GitMerge, ShieldCheck, Split } from "lucide-react";
import { useMemo } from "react";
import { useShell } from "@/components/command/context";
import { SidePanel } from "@/components/command/panel";
import { Confidence, PeopleCount, UrgencyPill, VulnIcons } from "@/components/domain";
import { Empty, ErrorNote, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { ApiError, api, type CaseOut, type ReviewPairOut } from "@/lib/api";
import { ago, REASON_LABEL } from "@/lib/format";
import { keys, useReview } from "@/lib/queries";
import { useUi } from "@/lib/store";

const LOCATION = new Set(["location_unknown", "low_confidence_location"]);
const SAFE = new Set(["reported_rescued", "possibly_rescued"]);

function Group({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  if (!count) return null;
  return (
    <section className="border-b border-line py-3 last:border-0">
      <h2 className="flex items-center gap-2 px-4 pb-2 text-[13px] font-semibold">
        {title}
        <span className="font-normal text-muted tnum">{count}</span>
      </h2>
      <ul className="space-y-2 px-3">{children}</ul>
    </section>
  );
}

function CaseLine({ c, now, children }: { c: CaseOut; now: number; children?: React.ReactNode }) {
  const select = useUi((s) => s.select);
  return (
    <li className="rounded-lg border border-line bg-bg/40 p-3">
      <button type="button" onClick={() => select(c.id)} className="block w-full text-left">
        <div className="flex items-center gap-2">
          <UrgencyPill level={c.urgency_level} score={c.urgency_score} />
          <span className="font-mono text-xs text-muted">{c.tracking_code}</span>
          <span className="ml-auto text-xs text-muted tnum">{ago(c.first_reported_at, now)}</span>
        </div>
        <p className="mt-1.5 text-[13px] text-text">{c.summary}</p>
        <div className="mt-1.5 flex items-center gap-2.5 text-xs text-muted">
          <PeopleCount n={c.people_count} />
          <VulnIcons c={c} max={4} showMedical={false} />
          <span className="truncate">{c.address_text ?? c.locality ?? "No place matched"}</span>
          <span className="ml-auto">
            <Confidence value={c.location_confidence} source={c.location_source} />
          </span>
        </div>
      </button>
      {children ? <div className="mt-2.5 flex flex-wrap gap-2">{children}</div> : null}
    </li>
  );
}

function PairCard({ pair, a, b, now }: { pair: ReviewPairOut; a: CaseOut; b: CaseOut; now: number }) {
  const qc = useQueryClient();
  const { toast, select } = useUi();
  const { disasterId } = useShell();
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.review(disasterId ?? "") });
    },
    onError: (e) =>
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "That did not work",
      }),
  });
  const [keep, drop] = a.urgency_score >= b.urgency_score ? [a, b] : [b, a];
  const reasons = (pair.reasons as { detail: string; weight: number }[]).filter((r) => r.weight > 0).slice(0, 4);
  return (
    <li className="rounded-lg border border-line bg-bg/40 p-3">
      <div className="grid grid-cols-2 gap-3">
        {[a, b].map((c) => (
          <button key={c.id} type="button" onClick={() => select(c.id)} className="min-w-0 text-left">
            <div className="flex items-center gap-1.5 text-xs">
              <span className="font-mono text-muted">{c.tracking_code}</span>
              <span className="text-muted">· {ago(c.first_reported_at, now)}</span>
            </div>
            <p className="mt-1 line-clamp-3 text-[13px] text-text">{c.summary}</p>
            <p className="mt-1 truncate text-xs text-muted">{c.address_text ?? c.locality}</p>
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        <span className="text-text tnum">{Math.round(pair.score * 100)}% alike</span>
        {reasons.length ? ` · ${reasons.map((r) => r.detail).join(", ")}` : ""}
      </p>
      <div className="mt-2.5 flex gap-2">
        <Button
          size="sm"
          icon={<GitMerge className="size-3.5" />}
          loading={act.isPending}
          onClick={() =>
            act.mutate(
              () =>
                api.post(`/api/v1/cases/${keep.id}/merge`, {
                  other_case_id: drop.id,
                }),
              {
                onSuccess: () =>
                  toast({
                    kind: "success",
                    text: `Merged into ${keep.tracking_code}`,
                    undo: () => {
                      api.post(`/api/v1/cases/${drop.id}/unmerge`).catch(() => undefined);
                    },
                  }),
              },
            )
          }
        >
          Same family, merge
        </Button>
        <Button
          size="sm"
          variant="subtle"
          icon={<Split className="size-3.5" />}
          loading={act.isPending}
          onClick={() =>
            act.mutate(() => api.post(`/api/v1/review-pairs/${pair.id}/dismiss`), {
              onSuccess: () => toast({ kind: "info", text: "Kept as separate cases" }),
            })
          }
        >
          Keep separate
        </Button>
      </div>
    </li>
  );
}

export default function ReviewPage() {
  const { disasterId, now, canEdit } = useShell();
  const review = useReview(disasterId);
  const { select, startPinEdit, toast, fly } = useUi();
  const qc = useQueryClient();
  const data = review.data;
  const byId = useMemo(() => new Map((data?.pair_cases ?? []).map((c) => [c.id, c])), [data]);
  const groups = useMemo(() => {
    const cases = data?.cases ?? [];
    return {
      location: cases.filter((c) => c.review_reasons.some((r) => LOCATION.has(r))),
      safe: cases.filter((c) => c.review_reasons.some((r) => SAFE.has(r))),
      other: cases.filter((c) =>
        c.review_reasons.every((r) => !LOCATION.has(r) && !SAFE.has(r) && r !== "possible_duplicate"),
      ),
    };
  }, [data]);
  const pairs = (data?.pairs ?? []).filter((p) => byId.has(p.case_a_id) && byId.has(p.case_b_id));
  const total = groups.location.length + groups.safe.length + groups.other.length + pairs.length;

  const patch = async (c: CaseOut, body: Record<string, unknown>, text: string) => {
    try {
      await api.patch(`/api/v1/cases/${c.id}`, body);
      toast({ kind: "success", text });
      qc.invalidateQueries({ queryKey: keys.review(disasterId ?? "") });
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "That did not work",
      });
    }
  };

  return (
    <SidePanel title="Review" aside={<span className="tnum">{total} need a look</span>}>
      {review.error ? (
        <div className="p-4">
          <ErrorNote onRetry={() => review.refetch()}>Could not load the review inbox.</ErrorNote>
        </div>
      ) : review.isLoading ? (
        <div className="space-y-2 p-4">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : total === 0 ? (
        <Empty title="Nothing to review" body="Uncertain locations, possible duplicates and safe reports land here." />
      ) : (
        <>
          <Group title="Confirm the location" count={groups.location.length}>
            {groups.location.map((c) => (
              <CaseLine key={c.id} c={c} now={now}>
                {canEdit ? (
                  <Button
                    size="sm"
                    variant="subtle"
                    icon={<Crosshair className="size-3.5" />}
                    onClick={() => {
                      select(c.id);
                      startPinEdit(c.id, c.lat ?? 13, c.lng ?? 80.2);
                      if (c.lat != null && c.lng != null) fly(c.lat, c.lng, 15);
                    }}
                  >
                    {c.lat == null ? "Place the pin" : "Check the pin"}
                  </Button>
                ) : null}
                {c.location_candidates.slice(0, 2).map((cand) => (
                  <Button
                    key={`${cand.lat}${cand.lng}`}
                    size="sm"
                    variant="ghost"
                    onClick={() => fly(cand.lat, cand.lng, 15)}
                  >
                    {cand.label}
                  </Button>
                ))}
              </CaseLine>
            ))}
          </Group>
          <Group title="Possible duplicates" count={pairs.length}>
            {pairs.map((p) => {
              const a = byId.get(p.case_a_id);
              const b = byId.get(p.case_b_id);
              return a && b ? <PairCard key={p.id} pair={p} a={a} b={b} now={now} /> : null;
            })}
          </Group>
          <Group title="Reported safe" count={groups.safe.length}>
            {groups.safe.map((c) => (
              <CaseLine key={c.id} c={c} now={now}>
                {canEdit ? (
                  <>
                    <Button
                      size="sm"
                      variant="go"
                      icon={<ShieldCheck className="size-3.5" />}
                      onClick={() =>
                        patch(c, { status: "rescued", note: "Confirmed safe" }, `${c.tracking_code} closed as safe`)
                      }
                    >
                      Confirm safe
                    </Button>
                    <Button
                      size="sm"
                      variant="subtle"
                      onClick={() => patch(c, { clear_reasons: [...SAFE] }, "Kept open")}
                    >
                      Keep open
                    </Button>
                  </>
                ) : null}
              </CaseLine>
            ))}
          </Group>
          <Group title="Other checks" count={groups.other.length}>
            {groups.other.map((c) => (
              <CaseLine key={c.id} c={c} now={now}>
                <span className="text-xs text-medium">
                  {c.review_reasons.map((r) => REASON_LABEL[r] ?? r).join(" · ")}
                </span>
              </CaseLine>
            ))}
          </Group>
        </>
      )}
    </SidePanel>
  );
}
