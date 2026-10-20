"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { create } from "zustand";
import {
  type AssignmentOut,
  api,
  type CaseDetail,
  type CaseOut,
  type Counters,
  type DisasterOut,
  type FloodZoneOut,
  type PlanOut,
  qs,
  type ReviewOut,
  type TeamOut,
  type UserOut,
  type WaterOut,
} from "./api";
import { decodeWater, type WaterField } from "./water";

export const keys = {
  me: ["me"] as const,
  disasters: ["disasters"] as const,
  cases: (d: string) => ["cases", d] as const,
  case: (id: string) => ["case", id] as const,
  teams: (d: string) => ["teams", d] as const,
  counters: (d: string) => ["counters", d] as const,
  plan: (d: string) => ["plan", d] as const,
  assignments: (d: string) => ["assignments", d] as const,
  flood: (d: string) => ["flood", d] as const,
  review: (d: string) => ["review", d] as const,
  analytics: (d: string) => ["analytics", d] as const,
  replay: (d: string) => ["replay", d] as const,
  water: (d: string) => ["water", d] as const,
};

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => api.get<UserOut>("/api/v1/auth/me"),
    staleTime: 60_000,
  });
}

export function useDisasters() {
  return useQuery({
    queryKey: keys.disasters,
    queryFn: () => api.get<DisasterOut[]>("/api/v1/disasters"),
    staleTime: 30_000,
  });
}

const STORAGE_KEY = "rg:disaster";

const useChosen = create<{ id: string | null; set: (id: string) => void }>((set) => ({
  id: null,
  set: (id) => {
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* private mode */
    }
    set({ id });
  },
}));

/** The disaster the command centre is looking at: last choice, else the newest live one. */
export function useDisasterId(): [string | null, (id: string) => void, DisasterOut | undefined] {
  const { data } = useDisasters();
  const { id, set } = useChosen();
  const [stored, setStored] = useState<string | null>(null);
  useEffect(() => {
    try {
      setStored(localStorage.getItem(STORAGE_KEY));
    } catch {
      setStored(null);
    }
  }, []);
  const resolved = useMemo(() => {
    if (!data?.length) return null;
    for (const candidate of [id, stored]) {
      if (candidate && data.some((d) => d.id === candidate)) return candidate;
    }
    return (data.find((d) => d.status !== "closed") ?? data[0]).id;
  }, [data, id, stored]);
  return [resolved, set, data?.find((d) => d.id === resolved)];
}

export function useCases(d: string | null) {
  return useQuery({
    queryKey: keys.cases(d ?? ""),
    queryFn: () => api.get<CaseOut[]>(`/api/v1/disasters/${d}/cases${qs({ status: "open" })}`),
    enabled: !!d,
    staleTime: 5 * 60_000,
  });
}

export function useCase(id: string | null) {
  return useQuery({
    queryKey: keys.case(id ?? ""),
    queryFn: () => api.get<CaseDetail>(`/api/v1/cases/${id}`),
    enabled: !!id,
  });
}

export function useTeams(d: string | null) {
  return useQuery({
    queryKey: keys.teams(d ?? ""),
    queryFn: () => api.get<TeamOut[]>(`/api/v1/teams${qs({ disaster_id: d })}`),
    enabled: !!d,
    staleTime: 5 * 60_000,
  });
}

export function useCounters(d: string | null) {
  return useQuery({
    queryKey: keys.counters(d ?? ""),
    queryFn: () => api.get<Counters>(`/api/v1/disasters/${d}/counters`),
    enabled: !!d,
    staleTime: 60_000,
  });
}

export function usePlan(d: string | null) {
  return useQuery({
    queryKey: keys.plan(d ?? ""),
    queryFn: () => api.get<PlanOut>(`/api/v1/dispatch/plan${qs({ disaster_id: d })}`),
    enabled: !!d,
    staleTime: 60_000,
  });
}

export function useAssignments(d: string | null) {
  return useQuery({
    queryKey: keys.assignments(d ?? ""),
    queryFn: () => api.get<AssignmentOut[]>(`/api/v1/disasters/${d}/assignments`),
    enabled: !!d,
    staleTime: 60_000,
  });
}

/** The flood nowcast, decoded once per forecast. `field` is null until the model has run. */
export function useWater(d: string | null): { data: WaterOut | undefined; field: WaterField | null } {
  const q = useQuery({
    queryKey: keys.water(d ?? ""),
    queryFn: () => api.get<WaterOut>(`/api/v1/disasters/${d}/water`),
    enabled: !!d,
    staleTime: 5 * 60_000,
    // the first forecast takes a few seconds after a disaster starts
    refetchInterval: (query) => (query.state.data?.available ? false : 15_000),
  });
  const field = useMemo(() => {
    const f = q.data?.forecast;
    if (!f) return null;
    try {
      return decodeWater(f);
    } catch {
      return null;
    }
  }, [q.data]);
  return { data: q.data, field };
}

export function useFloodZones(d: string | null) {
  return useQuery({
    queryKey: keys.flood(d ?? ""),
    queryFn: () => api.get<FloodZoneOut[]>(`/api/v1/disasters/${d}/flood-zones`),
    enabled: !!d,
    staleTime: 10 * 60_000,
  });
}

export function useReview(d: string | null) {
  return useQuery({
    queryKey: keys.review(d ?? ""),
    queryFn: () => api.get<ReviewOut>(`/api/v1/review${qs({ disaster_id: d })}`),
    enabled: !!d,
  });
}

export interface ReplayState {
  disaster_id: string;
  dataset: string;
  status: "playing" | "paused" | "finished" | "idle";
  speed: number;
  sim_now: string;
  starts_at: string;
  ends_at: string;
  progress: number;
  emitted: number;
  total: number;
  autopilot: boolean;
}

export function useReplayState(d: DisasterOut | undefined) {
  return useQuery({
    queryKey: keys.replay(d?.id ?? ""),
    queryFn: () => api.get<ReplayState>(`/api/v1/replay/${d?.id}/state`),
    enabled: d?.status === "replay",
    staleTime: 30_000,
  });
}

/**
 * Milliseconds "now" on the disaster's clock, ticking once a second. Live disasters use the
 * wall clock; replays run on simulated time, so "waiting 40 min" reads true at 60x.
 */
export function useDisasterNow(d: DisasterOut | undefined): number {
  const replay = useReplayState(d);
  const [wall, setWall] = useState(() => Date.now());
  const [anchor, setAnchor] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setWall(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const state = replay.data;
  useEffect(() => {
    if (state) setAnchor(Date.now());
  }, [state]);
  if (d?.status === "replay" && state) {
    const sim = new Date(state.sim_now).getTime();
    return state.status === "playing" ? sim + (wall - anchor) * state.speed : sim;
  }
  return wall;
}
