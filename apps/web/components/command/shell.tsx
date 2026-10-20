"use client";

import { WifiOff } from "lucide-react";
import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { clock } from "@/lib/format";
import { useLive } from "@/lib/live";
import {
  useAssignments,
  useCases,
  useCounters,
  useDisasterId,
  useDisasterNow,
  useDisasters,
  useFloodZones,
  useMe,
  usePlan,
  useReplayState,
  useTeams,
  useWater,
} from "@/lib/queries";
import { useUi } from "@/lib/store";
import { WaterControls } from "../map/water-controls";
import { Toasts } from "../toasts";
import { Empty } from "../ui/bits";
import { ButtonLink } from "../ui/button";
import { CaseDrawer } from "./case-drawer";
import { ShellContext } from "./context";
import { Palette } from "./palette";
import { NAV_KEYS, Sidebar } from "./sidebar";
import { TopBar } from "./topbar";

// MapLibre is large and needs the DOM: load it after the shell paints
const CommandMap = dynamic(() => import("../map/command-map").then((m) => m.CommandMap), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-bg" />,
});

function LiveBanner() {
  const { live, lastMessageAt } = useUi();
  if (live !== "reconnecting" && live !== "offline") return null;
  return (
    <output className="absolute top-3 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-lg border border-medium/50 bg-[#2a2410] px-3 py-1.5 text-[13px] text-[#fde68a] shadow-float">
      <WifiOff className="size-4" />
      {live === "offline" ? "Live updates stopped. Sign in again to resume." : "Live updates paused, reconnecting…"}
      {lastMessageAt ? <span className="text-[#fde68a]/70">Last update {clock(new Date(lastMessageAt))}</span> : null}
    </output>
  );
}

export function CommandShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const me = useMe();
  const disasters = useDisasters();
  const [disasterId, setDisasterId, disaster] = useDisasterId();
  const cases = useCases(disasterId);
  const teams = useTeams(disasterId);
  const assignments = useAssignments(disasterId);
  const flood = useFloodZones(disasterId);
  const water = useWater(disasterId);
  const counters = useCounters(disasterId);
  const plan = usePlan(disasterId);
  const replay = useReplayState(disaster);
  const now = useDisasterNow(disaster);
  const { selectedCaseId, select, fly } = useUi();
  const [palette, setPalette] = useState(false);
  useLive(disasterId);

  const role = me.data?.role;
  const canEdit = role === "admin" || role === "coordinator";
  useEffect(() => {
    if (role === "field_lead") router.replace("/field");
  }, [role, router]);

  // a new disaster means a new board
  // biome-ignore lint/correctness/useExhaustiveDependencies: the effect exists to run when disasterId changes
  useEffect(() => {
    select(null);
  }, [disasterId, select]);

  // ⌘K search, g+letter navigation
  useEffect(() => {
    let g = false;
    let gTimer: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
        return;
      }
      const t = e.target instanceof Element ? e.target : null;
      if (t?.closest("input, textarea, select, [contenteditable], [role=dialog]")) return;
      if (e.key === "/") {
        e.preventDefault();
        setPalette(true);
      } else if (e.key === "g") {
        g = true;
        clearTimeout(gTimer);
        gTimer = setTimeout(() => {
          g = false;
        }, 800);
      } else if (g) {
        const hit = NAV_KEYS.find((n) => n.key === e.key);
        if (hit) router.push(hit.href);
        g = false;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  const proposed = useMemo(
    () => (path.startsWith("/command/dispatch") ? (plan.data?.stops ?? []) : []),
    [path, plan.data],
  );
  const counts = {
    review: counters.data?.needs_review ?? 0,
    dispatch: plan.data?.stops.filter((s) => s.status === "proposed").length ?? 0,
  };
  const caseList = cases.data ?? [];
  const teamList = teams.data ?? [];

  const noDisaster = disasters.isSuccess && disasters.data.length === 0;

  return (
    <div className="theme-dark grid h-dvh grid-cols-[auto_minmax(0,1fr)] overflow-hidden bg-bg text-text">
      <Sidebar counts={counts} isAdmin={role === "admin"} />
      <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)]">
        <TopBar
          disasters={disasters.data ?? []}
          disaster={disaster}
          onDisaster={setDisasterId}
          counters={counters.data}
          replay={replay.data}
          simNow={now}
          me={me.data}
          onSearch={() => setPalette(true)}
        />
        <main className="relative min-h-0 overflow-hidden">
          {noDisaster ? (
            <Empty
              className="h-full"
              title="No active event"
              body="Create a disaster, or start a replay to see Rescue Grid at work."
              action={
                <div className="flex gap-2">
                  <ButtonLink href="/command/replay">Start a replay</ButtonLink>
                  {role === "admin" ? (
                    <ButtonLink href="/admin/disasters" variant="outline">
                      Create a disaster
                    </ButtonLink>
                  ) : null}
                </div>
              }
            />
          ) : (
            <>
              <CommandMap
                disaster={disaster}
                cases={caseList}
                teams={teamList}
                assignments={assignments.data ?? []}
                proposed={proposed}
                flood={flood.data ?? []}
                water={water.field}
                now={now}
              />
              <LiveBanner />
              {path === "/command" ? (
                <div className="absolute top-3 left-3 z-20">
                  <WaterControls water={water.data} field={water.field} now={now} />
                </div>
              ) : null}
              <ShellContext.Provider
                value={{
                  disasterId,
                  disaster,
                  cases: caseList,
                  teams: teamList,
                  now,
                  canEdit,
                  loading: cases.isLoading,
                }}
              >
                {children}
              </ShellContext.Provider>
              {selectedCaseId ? (
                <CaseDrawer
                  key={selectedCaseId}
                  caseId={selectedCaseId}
                  cases={caseList}
                  teams={teamList}
                  now={now}
                  canEdit={canEdit}
                  water={water.field}
                />
              ) : null}
            </>
          )}
        </main>
      </div>
      <Palette
        open={palette}
        onOpenChange={setPalette}
        cases={caseList}
        now={now}
        onPick={(c) => {
          select(c.id);
          if (c.lat != null && c.lng != null) fly(c.lat, c.lng, 14.5);
          if (
            !path.startsWith("/command") ||
            path.startsWith("/command/analytics") ||
            path.startsWith("/command/intake") ||
            path.startsWith("/command/queue")
          )
            router.push("/command");
        }}
      />
      <Toasts />
    </div>
  );
}
