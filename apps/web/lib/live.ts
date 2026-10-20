"use client";

import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import type { AssignmentOut, CaseDetail, CaseOut, Counters, TeamOut } from "./api";
import { keys, type ReplayState } from "./queries";
import { useUi } from "./store";

const OPEN = new Set(["new", "needs_review", "queued", "assigned", "en_route", "on_scene", "unreachable"]);

interface Message {
  type: string;
  data: unknown;
  at: string;
}

function wsBase(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  if (configured) return configured;
  const { protocol, host } = window.location;
  return `${protocol === "https:" ? "wss" : "ws"}://${host}`;
}

function upsertCases(qc: QueryClient, disasterId: string, incoming: CaseOut[]) {
  qc.setQueryData<CaseOut[]>(keys.cases(disasterId), (old) => {
    if (!old) return old;
    const byId = new Map(old.map((c) => [c.id, c]));
    for (const c of incoming) {
      const prev = byId.get(c.id);
      if (prev && prev.version > c.version) continue; // an older event arrived late
      if (OPEN.has(c.status)) byId.set(c.id, c);
      else byId.delete(c.id);
    }
    return [...byId.values()];
  });
  for (const c of incoming) {
    qc.setQueryData<CaseDetail>(keys.case(c.id), (old) => (old ? { ...old, ...c } : old));
    // the drawer's timeline and sources change with every event: refetch when someone is looking
    qc.invalidateQueries({ queryKey: keys.case(c.id), refetchType: "active" });
  }
}

function apply(qc: QueryClient, disasterId: string, msg: Message) {
  const ui = useUi.getState();
  switch (msg.type) {
    case "hello": {
      const data = msg.data as { counters?: Counters };
      if (data.counters) qc.setQueryData(keys.counters(disasterId), data.counters);
      return;
    }
    case "case.upsert":
      upsertCases(qc, disasterId, [(msg.data as { case: CaseOut }).case]);
      qc.invalidateQueries({
        queryKey: keys.review(disasterId),
        refetchType: "active",
      });
      return;
    case "cases.upsert":
      upsertCases(qc, disasterId, (msg.data as { cases: CaseOut[] }).cases);
      return;
    case "team.upsert": {
      const t = msg.data as TeamOut;
      qc.setQueryData<TeamOut[]>(keys.teams(disasterId), (old) =>
        old
          ? old.some((x) => x.id === t.id)
            ? old.map((x) => (x.id === t.id ? { ...x, ...t } : x))
            : [...old, t]
          : old,
      );
      return;
    }
    case "team.location": {
      const p = msg.data as {
        id: string;
        lat: number;
        lng: number;
        heading: number | null;
        at: string;
      };
      qc.setQueryData<TeamOut[]>(keys.teams(disasterId), (old) =>
        old?.map((x) =>
          x.id === p.id
            ? {
                ...x,
                lat: p.lat,
                lng: p.lng,
                heading: p.heading,
                location_updated_at: p.at,
              }
            : x,
        ),
      );
      return;
    }
    case "assignment.upsert": {
      const a = msg.data as AssignmentOut;
      qc.setQueryData<AssignmentOut[]>(keys.assignments(disasterId), (old) => {
        if (!old) return old;
        const active = ["approved", "started", "reached"].includes(a.status);
        const rest = old.filter((x) => x.id !== a.id);
        return active ? [...rest, a] : rest;
      });
      return;
    }
    case "plan.updated":
    case "plan.stale":
      qc.invalidateQueries({ queryKey: keys.plan(disasterId) });
      qc.invalidateQueries({ queryKey: keys.assignments(disasterId) });
      return;
    case "counters":
      qc.setQueryData(keys.counters(disasterId), msg.data as Counters);
      return;
    case "replay.state":
      qc.setQueryData(keys.replay(disasterId), msg.data as ReplayState);
      return;
    case "flood_zones.updated":
      qc.invalidateQueries({ queryKey: keys.flood(disasterId) });
      return;
    case "water.update":
    case "water.forcing":
      qc.invalidateQueries({ queryKey: keys.water(disasterId) });
      return;
    case "disaster.updated":
      qc.invalidateQueries({ queryKey: keys.disasters });
      return;
    case "toast": {
      const t = msg.data as {
        kind: "critical" | "rescued";
        text: string;
        case_id?: string;
      };
      ui.toast({ kind: t.kind, text: t.text, caseId: t.case_id });
      return;
    }
  }
}

/** Keeps the command centre's caches in step with the server over one WebSocket. */
export function useLive(disasterId: string | null) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!disasterId) return;
    let socket: WebSocket | null = null;
    let attempt = 0;
    let closed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const { setLive, touch } = useUi.getState();

    const connect = () => {
      setLive(attempt === 0 ? "connecting" : "reconnecting");
      socket = new WebSocket(`${wsBase()}/ws/disasters/${disasterId}`);
      socket.onopen = () => {
        if (attempt > 0) {
          // we may have missed events while away: resync everything for this disaster
          for (const k of ["cases", "teams", "plan", "assignments", "review", "counters", "replay"]) {
            qc.invalidateQueries({ queryKey: [k, disasterId] });
          }
        }
        attempt = 0;
        setLive("live");
        touch();
      };
      socket.onmessage = (ev) => {
        touch();
        try {
          apply(qc, disasterId, JSON.parse(ev.data) as Message);
        } catch {
          /* a malformed frame is not worth crashing the board */
        }
      };
      socket.onclose = (ev) => {
        if (closed) return;
        if (ev.code === 1008) {
          setLive("offline");
          return; // signed out or no access: reconnecting will not help
        }
        attempt += 1;
        setLive("reconnecting");
        const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5)) * (0.75 + Math.random() / 2);
        timer = setTimeout(connect, delay);
      };
    };
    connect();
    const online = () => {
      if (socket?.readyState === WebSocket.CLOSED) {
        clearTimeout(timer);
        connect();
      }
    };
    window.addEventListener("online", online);
    return () => {
      closed = true;
      clearTimeout(timer);
      window.removeEventListener("online", online);
      socket?.close();
    };
  }, [disasterId, qc]);
}
