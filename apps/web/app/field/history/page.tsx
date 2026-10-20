"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { useField } from "@/components/field/shell";
import { Empty, Skeleton } from "@/components/ui/bits";
import { api, type Job } from "@/lib/api";
import { stamp } from "@/lib/format";

export default function FieldHistory() {
  const { t } = useField();
  const q = useQuery({
    queryKey: ["field-history"],
    queryFn: () => api.get<Job[]>("/api/v1/field/history"),
  });
  if (q.isLoading)
    return (
      <div className="p-4">
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (!q.data?.length) return <Empty className="py-20" title={t("noHistory")} />;
  return (
    <ul className="divide-y divide-line">
      {q.data.map(({ assignment: a, case: c }) => (
        <li key={a.id} className="flex gap-3 px-4 py-4">
          {a.status === "completed" ? (
            <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-go" />
          ) : (
            <XCircle className="mt-0.5 size-5 shrink-0 text-critical" />
          )}
          <div className="min-w-0">
            <p className="text-[16px] font-medium">{c.summary}</p>
            <p className="text-[14px] text-muted">{c.address_text ?? c.locality}</p>
            <p className="mt-1 text-[13px] text-muted tnum">
              {stamp(a.completed_at)} ·{" "}
              {a.status === "completed" ? t("peopleN", { n: a.outcome_people_rescued ?? 0 }) : a.outcome_note}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
