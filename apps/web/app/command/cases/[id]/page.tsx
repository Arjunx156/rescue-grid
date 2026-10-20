"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useShell } from "@/components/command/context";
import { QueuePanel } from "@/components/command/queue-panel";
import { useUi } from "@/lib/store";

/** A shareable link to one case: the map with that case open. */
export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const { cases, teams, now } = useShell();
  const select = useUi((s) => s.select);
  useEffect(() => {
    if (id) select(id);
  }, [id, select]);
  return <QueuePanel cases={cases} teams={teams} now={now} />;
}
