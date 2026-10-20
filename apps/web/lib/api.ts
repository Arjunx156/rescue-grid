import type { components } from "./api-types";

type S = components["schemas"];
export type CaseOut = S["CaseOut"];
export type CaseDetail = S["CaseDetail"];
export type TeamOut = S["TeamOut"];
export type DisasterOut = S["DisasterOut"];
export type PlanOut = S["PlanOut"];
export type PlanStop = S["PlanStop"];
export type AssignmentOut = S["AssignmentOut"];
export type Counters = S["Counters"];
export type UserOut = S["UserOut"];
export type FloodZoneOut = S["FloodZoneOut"];
export type ReviewOut = S["ReviewOut"];
export type ReviewPairOut = S["ReviewPairOut"];
export type PublicStatus = S["PublicStatus"];
export type FieldNow = S["FieldNow"];
export type Job = S["Job"];
export type Factor = S["Factor"];
export type SourceOut = S["SourceOut"];
export type EventOut = S["EventOut"];
export type WaterOut = S["WaterOut"];
export type WaterForecast = S["WaterForecast"];
export type WaterClockOut = S["WaterClockOut"];
export type FloodModelIn = S["FloodModelIn"];
export type FloodModelOut = S["FloodModelOut"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

let refreshing: Promise<boolean> | null = null;

/** One refresh at a time, however many requests hit a 401 together. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "include",
    headers: { "X-Requested-With": "rescuegrid" },
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      setTimeout(() => {
        refreshing = null;
      }, 0);
    });
  return refreshing;
}

async function detail(r: Response): Promise<string> {
  try {
    const body = await r.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg).join("; ");
    }
  } catch {
    /* not json */
  }
  return r.status >= 500 ? "The server had a problem. Try again." : `Request failed (${r.status})`;
}

export async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Requested-With", "rescuegrid");
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "No connection. Check your network.");
  }
  if (r.status === 401 && retry && !path.startsWith("/api/v1/auth/")) {
    if (await refreshSession()) return request<T>(path, init, false);
    // the failed refresh also cleared the cookies, so the proxy will not bounce us back
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.assign(`/login?next=${next}`);
    }
  }
  if (!r.ok) throw new ApiError(r.status, await detail(r));
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : JSON.stringify(body ?? {}),
    }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export function qs(params: Record<string, string | number | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}
