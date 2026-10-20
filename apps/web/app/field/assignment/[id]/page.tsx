"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { JobCard } from "@/components/field/job-card";
import { useField } from "@/components/field/shell";
import { ErrorNote, Skeleton } from "@/components/ui/bits";
import { api, type Job } from "@/lib/api";

const FieldMap = dynamic(() => import("@/components/map/field-map").then((m) => m.FieldMap), { ssr: false });

export default function AssignmentPage() {
  const { id } = useParams<{ id: string }>();
  const { t, flood, position, now } = useField();
  const q = useQuery({
    queryKey: ["field-job", id],
    queryFn: () => api.get<Job>(`/api/v1/field/assignments/${id}`),
  });
  const job = q.data;
  const team = now?.team;
  const me =
    position ??
    (team?.lat != null && team.lng != null ? { lat: team.lat, lng: team.lng, heading: team.heading ?? null } : null);
  return (
    <div className="space-y-4 p-4">
      <Link href="/field" className="inline-flex items-center gap-1.5 text-[15px] text-muted">
        <ArrowLeft className="size-4" /> {t("tabJob")}
      </Link>
      {q.error ? <ErrorNote onRetry={() => q.refetch()}>{t("loadFailed")}</ErrorNote> : null}
      {!job ? (
        <Skeleton className="h-80 w-full rounded-2xl" />
      ) : (
        <>
          <div className="h-64 overflow-hidden rounded-2xl border border-line">
            <FieldMap
              me={me}
              heading={me?.heading}
              flood={flood}
              route={job.assignment.route}
              stops={
                job.case.lat != null && job.case.lng != null
                  ? [
                      {
                        lat: job.case.lat,
                        lng: job.case.lng,
                        level: job.case.urgency_level,
                        label: job.case.tracking_code,
                      },
                    ]
                  : []
              }
            />
          </div>
          {["approved", "started", "reached"].includes(job.assignment.status) ? (
            <JobCard job={job} />
          ) : (
            <JobCard job={job} primary={false} />
          )}
          {job.assignment.reasons.length ? (
            <section className="rounded-2xl border border-line p-4">
              <h2 className="text-[15px] font-semibold">{t("whyYou")}</h2>
              <ul className="mt-2 space-y-1 text-[15px] text-muted">
                {job.assignment.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
