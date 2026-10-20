import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { signIn } from "./helpers";

async function noSeriousA11yIssues(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // MapLibre's own controls are third-party markup
    .exclude(".maplibregl-ctrl")
    .analyze();
  const serious = violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .flatMap((v) =>
      v.nodes.map((n) => {
        // for contrast, say which colours failed so the fix is obvious from the report
        const c = n.any[0]?.data as { fgColor?: string; bgColor?: string; contrastRatio?: number } | undefined;
        const colours = c?.fgColor ? ` (${c.fgColor} on ${c.bgColor}, ${c.contrastRatio}:1)` : "";
        return `${v.id}: ${n.target.join(" ")}${colours}`;
      }),
    );
  expect(serious).toEqual([]);
}

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  return errors;
}

const PUBLIC = ["/", "/sos", "/login", "/privacy", "/terms"];

for (const path of PUBLIC) {
  test(`public page ${path} renders cleanly`, async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto(path);
    await expect(page.locator("h1").first()).toBeVisible();
    await noSeriousA11yIssues(page);
    expect(errors).toEqual([]);
  });
}

test("every link on the public pages leads somewhere", async ({ page }) => {
  const seen = new Set<string>();
  for (const path of PUBLIC) {
    await page.goto(path);
    const hrefs = await page.locator("a[href]").evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).href));
    for (const href of hrefs) seen.add(href.split("#")[0]);
  }
  const internal = [...seen].filter((h) => h.startsWith(new URL(page.url()).origin));
  const broken: string[] = [];
  for (const href of internal) {
    const r = await page.request.get(href, { maxRedirects: 0 });
    if (r.status() >= 400) broken.push(`${r.status()} ${href}`);
  }
  expect(internal.length).toBeGreaterThan(4);
  expect(broken).toEqual([]);
});

test("an admin can hand someone a password reset link", async ({ page }) => {
  await signIn(page, "admin");
  await page.goto("/admin/users");
  const row = page.getByRole("row").filter({ hasText: "viewer@demo.rescuegrid.in" });
  await row.getByRole("button", { name: "Reset password" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/works once, for 24 hours/)).toBeVisible();
  const link = (await dialog.locator("code").textContent()) ?? "";
  expect(link).toMatch(/\/invite\/[\w-]+$/);
  await page.goto(new URL(link).pathname);
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
});

test("an unknown tracking code says so", async ({ page }) => {
  await page.goto("/sos/RG-NOPE00");
  await expect(page.getByRole("alert")).toBeVisible();
});

for (const path of ["/command", "/command/queue", "/command/review", "/command/dispatch", "/command/analytics"]) {
  test(`command page ${path} renders cleanly`, async ({ page }) => {
    const errors = watchErrors(page);
    await signIn(page, "coordinator");
    await page.goto(path);
    await expect(page.getByRole("navigation").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    await noSeriousA11yIssues(page);
    expect(errors).toEqual([]);
  });
}

test("the field app renders cleanly", async ({ page }) => {
  const errors = watchErrors(page);
  await signIn(page, "field_lead");
  await page.goto("/field");
  await page.waitForLoadState("networkidle");
  await noSeriousA11yIssues(page);
  expect(errors).toEqual([]);
});
