import { create } from "zustand";
import type { Level } from "./format";

export type LiveStatus = "connecting" | "live" | "reconnecting" | "offline";

export interface Toast {
  id: number;
  kind: "critical" | "rescued" | "info" | "error" | "success";
  text: string;
  caseId?: string;
  undo?: () => void;
}

interface UiState {
  selectedCaseId: string | null;
  hoverCaseId: string | null;
  pinEdit: { caseId: string; lat: number; lng: number } | null;
  levels: Level[];
  showFlood: boolean;
  showTeams: boolean;
  showRoutes: boolean;
  showWater: boolean;
  /** the forecast frame on the map: 0 is now, then one per 15 minutes */
  waterFrame: number;
  waterWorst: boolean;
  map3d: boolean;
  queueOpen: boolean;
  live: LiveStatus;
  lastMessageAt: number | null;
  toasts: Toast[];
  flyTo: { lat: number; lng: number; zoom?: number; at: number } | null;
  select: (id: string | null) => void;
  hover: (id: string | null) => void;
  startPinEdit: (caseId: string, lat: number, lng: number) => void;
  movePin: (lat: number, lng: number) => void;
  endPinEdit: () => void;
  toggleLevel: (l: Level) => void;
  setLayer: (k: "showFlood" | "showTeams" | "showRoutes" | "showWater", v: boolean) => void;
  setWaterFrame: (f: number) => void;
  setWaterWorst: (v: boolean) => void;
  setMap3d: (v: boolean) => void;
  setQueueOpen: (v: boolean) => void;
  setLive: (s: LiveStatus) => void;
  touch: () => void;
  toast: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
  fly: (lat: number, lng: number, zoom?: number) => void;
}

let toastId = 0;

export const useUi = create<UiState>((set) => ({
  selectedCaseId: null,
  hoverCaseId: null,
  pinEdit: null,
  levels: ["critical", "high", "medium", "low"],
  showFlood: true,
  showTeams: true,
  showRoutes: true,
  showWater: true,
  waterFrame: 0,
  waterWorst: false,
  map3d: false,
  queueOpen: true,
  live: "connecting",
  lastMessageAt: null,
  toasts: [],
  flyTo: null,
  select: (id) => set({ selectedCaseId: id }),
  hover: (id) => set({ hoverCaseId: id }),
  startPinEdit: (caseId, lat, lng) => set({ pinEdit: { caseId, lat, lng } }),
  movePin: (lat, lng) => set((s) => (s.pinEdit ? { pinEdit: { ...s.pinEdit, lat, lng } } : {})),
  endPinEdit: () => set({ pinEdit: null }),
  toggleLevel: (l) =>
    set((s) => ({
      levels: s.levels.includes(l) ? s.levels.filter((x) => x !== l) : [...s.levels, l],
    })),
  setLayer: (k, v) => set({ [k]: v } as Partial<UiState>),
  setWaterFrame: (waterFrame) => set({ waterFrame }),
  setWaterWorst: (waterWorst) => set({ waterWorst }),
  setMap3d: (map3d) => set({ map3d }),
  setQueueOpen: (v) => set({ queueOpen: v }),
  setLive: (live) => set({ live }),
  touch: () => set({ lastMessageAt: Date.now() }),
  toast: (t) => set((s) => ({ toasts: [...s.toasts.slice(-2), { ...t, id: ++toastId }] })),
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  fly: (lat, lng, zoom) => set({ flyTo: { lat, lng, zoom, at: Date.now() } }),
}));
