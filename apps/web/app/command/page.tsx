"use client";

import { useShell } from "@/components/command/context";
import { QueuePanel } from "@/components/command/queue-panel";

export default function MapPage() {
  const { cases, teams, now } = useShell();
  return <QueuePanel cases={cases} teams={teams} now={now} />;
}
