"use client";

import { createContext, useContext } from "react";
import type { CaseOut, DisasterOut, TeamOut } from "@/lib/api";

interface ShellValue {
  disasterId: string | null;
  disaster: DisasterOut | undefined;
  cases: CaseOut[];
  teams: TeamOut[];
  now: number;
  canEdit: boolean;
  loading: boolean;
}

export const ShellContext = createContext<ShellValue | null>(null);

/** What every command page shares: the disaster, its cases and teams, and the clock. */
export function useShell(): ShellValue {
  const v = useContext(ShellContext);
  if (!v) throw new Error("useShell outside CommandShell");
  return v;
}
