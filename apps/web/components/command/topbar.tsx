"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, CircleUser, LogOut, Search, Settings } from "lucide-react";
import { useRouter } from "next/navigation";
import { api, type Counters, type DisasterOut, type UserOut } from "@/lib/api";
import { clock, cn } from "@/lib/format";
import type { ReplayState } from "@/lib/queries";
import { useUi } from "@/lib/store";
import { Kbd } from "../ui/bits";
import { Menu, MenuItem, MenuLabel, MenuSeparator } from "../ui/overlay";
import { RollingNumber } from "./number";

function Stat({ label, value, tone }: { label: string; value: number | undefined; tone?: string }) {
  return (
    <div className="flex flex-row-reverse items-baseline justify-end gap-1.5 whitespace-nowrap px-3 first:pl-0">
      <dt className="text-xs text-muted">{label}</dt>
      <dd>
        <RollingNumber value={value ?? 0} className={cn("text-[15px] font-semibold", tone)} />
      </dd>
    </div>
  );
}

function LiveDot() {
  const { live, lastMessageAt } = useUi();
  const map = {
    live: ["bg-go", "Live"],
    connecting: ["bg-medium", "Connecting"],
    reconnecting: ["bg-medium", "Reconnecting"],
    offline: ["bg-critical", "Offline"],
  } as const;
  const [color, label] = map[live];
  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs text-muted"
      title={lastMessageAt ? `Last update ${new Date(lastMessageAt).toLocaleTimeString()}` : undefined}
    >
      <span
        className={cn("size-1.5 rounded-full", color, live === "live" && "motion-safe:animate-pulse")}
        aria-hidden
      />
      {label}
    </span>
  );
}

export function TopBar({
  disasters,
  disaster,
  onDisaster,
  counters,
  replay,
  simNow,
  me,
  onSearch,
}: {
  disasters: DisasterOut[];
  disaster: DisasterOut | undefined;
  onDisaster: (id: string) => void;
  counters: Counters | undefined;
  replay: ReplayState | undefined;
  simNow: number;
  me: UserOut | undefined;
  onSearch: () => void;
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const signOut = async () => {
    await api.post("/api/v1/auth/logout").catch(() => undefined);
    qc.clear();
    router.replace("/login");
  };
  return (
    <header className="flex h-12 items-center gap-4 border-b border-line bg-bg px-4">
      <Menu
        align="start"
        trigger={
          <button
            type="button"
            className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1 -ml-2 text-[14px] font-medium hover:bg-panel-2"
          >
            <span className="max-w-72 truncate">{disaster?.name?.replace(" (replay)", "") ?? "Choose a disaster"}</span>
            {disaster?.status === "replay" ? <span className="text-xs font-normal text-muted">Replay</span> : null}
            <ChevronDown className="size-4 text-muted" />
          </button>
        }
      >
        <MenuLabel>Disasters you can see</MenuLabel>
        {disasters.map((d) => (
          <MenuItem key={d.id} onSelect={() => onDisaster(d.id)}>
            <span className="flex w-full items-center justify-between gap-4">
              <span className={cn("truncate", d.id === disaster?.id && "font-medium")}>{d.name}</span>
              <span className="text-xs text-muted capitalize">{d.status}</span>
            </span>
          </MenuItem>
        ))}
      </Menu>

      <dl className="hidden items-center divide-x divide-line lg:flex" aria-label="Live counters">
        <Stat label="open" value={counters?.open} />
        <Stat label="critical" value={counters?.critical} tone={counters?.critical ? "text-critical" : undefined} />
        <Stat label="review" value={counters?.needs_review} tone={counters?.needs_review ? "text-medium" : undefined} />
        <Stat label={`/ ${counters?.teams_on_duty ?? 0} teams out`} value={counters?.teams_active} />
        <Stat label="rescued" value={counters?.people_rescued} tone="text-go" />
      </dl>

      <div className="ml-auto flex items-center gap-3">
        {disaster?.status === "replay" && replay ? (
          <span className="hidden items-center gap-2 whitespace-nowrap rounded-md border border-line px-2 py-1 text-xs text-muted md:inline-flex">
            <span className="font-mono text-text tnum">{clock(new Date(simNow))}</span>
            <span>
              {replay.status === "playing" ? `${replay.speed}x` : replay.status === "finished" ? "Finished" : "Paused"}
            </span>
          </span>
        ) : null}
        <LiveDot />
        <button
          type="button"
          onClick={onSearch}
          className="inline-flex h-8 items-center gap-2 whitespace-nowrap rounded-md border border-line px-2.5 text-xs text-muted hover:border-line-strong hover:text-text"
          aria-label="Find a case"
        >
          <Search className="size-3.5" />
          <span className="hidden 2xl:inline">Find a case</span>
          <Kbd>⌘K</Kbd>
        </button>
        <Menu
          trigger={
            <button
              type="button"
              aria-label="Account"
              className="grid size-8 place-items-center rounded-full bg-panel-2 text-[12px] font-semibold text-text"
            >
              {me?.name
                ?.split(" ")
                .map((p) => p[0])
                .slice(0, 2)
                .join("") ?? <CircleUser className="size-4" />}
            </button>
          }
        >
          <MenuLabel>
            <span className="block text-text">{me?.name}</span>
            <span className="capitalize">{me?.role?.replace("_", " ")}</span>
            {me?.organization ? <span> · {me.organization}</span> : null}
          </MenuLabel>
          <MenuSeparator />
          <MenuItem icon={<Settings />} onSelect={() => router.push("/settings")}>
            Settings
          </MenuItem>
          <MenuItem icon={<LogOut />} onSelect={signOut}>
            Sign out
          </MenuItem>
        </Menu>
      </div>
    </header>
  );
}
