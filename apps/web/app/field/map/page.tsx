"use client";

import dynamic from "next/dynamic";
import { useField } from "@/components/field/shell";

const FieldMap = dynamic(() => import("@/components/map/field-map").then((m) => m.FieldMap), { ssr: false });

export default function FieldMapPage() {
  const { now, flood, position } = useField();
  const jobs = [now?.current, now?.next].filter((j): j is NonNullable<typeof j> => !!j);
  const team = now?.team;
  const me =
    position ??
    (team?.lat != null && team.lng != null ? { lat: team.lat, lng: team.lng, heading: team.heading ?? null } : null);
  return (
    <div className="h-[calc(100dvh-13rem)]">
      <FieldMap
        me={me}
        heading={me?.heading}
        flood={flood}
        route={now?.current?.assignment.route ?? null}
        stops={jobs
          .filter((j) => j.case.lat != null && j.case.lng != null)
          .map((j, i) => ({
            lat: j.case.lat as number,
            lng: j.case.lng as number,
            level: j.case.urgency_level,
            label: `${i + 1} · ${j.case.tracking_code}`,
          }))}
      />
    </div>
  );
}
