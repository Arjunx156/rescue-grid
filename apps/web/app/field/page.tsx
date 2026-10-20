"use client";

import { JobCard } from "@/components/field/job-card";
import { useField } from "@/components/field/shell";
import { Empty, Skeleton } from "@/components/ui/bits";

export default function FieldHome() {
  const { now, stale, loading, t } = useField();
  if (loading) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-72 w-full rounded-2xl" />
      </div>
    );
  }
  const onDuty = now?.team && now.team.status !== "off_duty";
  return (
    <div className="space-y-4 p-4">
      {stale ? (
        <p className="rounded-lg bg-[#fef3c7] px-3 py-2 text-[14px] text-[#92400e]">{t("showingSaved")}</p>
      ) : null}
      {now?.current ? (
        <JobCard job={now.current} />
      ) : (
        <Empty className="py-20" title={onDuty ? t("standBy") : t("goOnDuty")} />
      )}
      {now?.next ? (
        <section className="space-y-2">
          <h2 className="px-1 text-[14px] font-semibold text-muted">{t("nextJob")}</h2>
          <JobCard job={now.next} primary={false} />
        </section>
      ) : null}
    </div>
  );
}
