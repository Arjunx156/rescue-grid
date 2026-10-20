// usage: bun scripts-shot.mjs <out-dir> <role|none> <width> <path> [<path>...]
import { chromium } from "@playwright/test";

const [out, role, width, ...paths] = process.argv.slice(2);
const base = process.env.BASE ?? "http://localhost:3100";
const browser = await chromium.launch({ channel: "chrome" });
const ctx = await browser.newContext({
  viewport: { width: Number(width), height: Number(width) < 600 ? 860 : 900 },
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});
page.on("pageerror", (e) => errors.push(String(e)));
page.on("requestfailed", (r) => errors.push(`FAILED ${r.url().slice(0, 120)} ${r.failure()?.errorText}`));
page.on("response", (r) => {
  if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url().slice(0, 120)}`);
});
if (role !== "none") {
  await page.goto(`${base}/login`);
  const r = await page.request.post(`${base}/api/v1/auth/demo`, {
    data: { role },
    headers: { "X-Requested-With": "rescuegrid" },
  });
  if (!r.ok()) {
    console.log("demo login failed", r.status(), await r.text());
  }
}
for (const p of paths) {
  const [path, wait, ...rest] = p.split("|");
  const action = rest.join("|");
  await page.goto(`${base}${path}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(Number(wait ?? 3500));
  if (action) {
    await page.evaluate(action);
    await page.waitForTimeout(Number(process.env.AFTER ?? 1500));
  }
  const name = `${out}/${path.replace(/[/?=&]+/g, "_") || "_root"}-${width}${action ? "-act" : ""}.png`;
  const canvas = await page.evaluate(() => {
    const c = document.querySelector(".maplibregl-canvas");
    return c ? `${c.clientWidth}x${c.clientHeight}` : "none";
  });
  console.log("canvas", canvas);
  await page.screenshot({ path: name });
  console.log("shot", name);
}
console.log("errors:", errors.slice(0, 8).join("\n  "));
await browser.close();
