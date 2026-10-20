import { type APIRequestContext, expect, type Page } from "@playwright/test";

export const XRW = { "X-Requested-With": "rescuegrid" };

export type Role = "coordinator" | "admin" | "viewer" | "field_lead";

/** The demo sign-in the login page offers; it sets the same cookies a real login does. */
export async function signIn(page: Page, role: Role) {
  const r = await page.request.post("/api/v1/auth/demo", { data: { role }, headers: XRW });
  expect(r.ok(), await r.text()).toBeTruthy();
}

export async function liveDisaster(request: APIRequestContext): Promise<{ disaster_id: string; name: string }> {
  const ctx = await (await request.get("/api/v1/sos/context")).json();
  expect(ctx.available, "no live disaster: run `just seed`").toBeTruthy();
  return ctx;
}

/** Point the command centre at a disaster before it loads, as a coordinator's last choice would. */
export async function watch(page: Page, disasterId: string) {
  await page.addInitScript((id) => localStorage.setItem("rg:disaster", id), disasterId);
}

export async function publicStatus(request: APIRequestContext, code: string): Promise<string> {
  const r = await request.get(`/api/v1/sos/${code}`);
  return r.ok() ? (await r.json()).status : "missing";
}

/** Somewhere in south Chennai, nudged per run so repeat runs are not merged as duplicates. */
export function somewhereInChennai() {
  return { latitude: 12.97 + Math.random() * 0.06, longitude: 80.2 + Math.random() * 0.04 };
}

export function door() {
  return 100 + Math.floor(Math.random() * 800);
}
