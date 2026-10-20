import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

interface Disaster {
  id: string;
  status: string;
  created_at: string;
}

// docs/03-App-Flow.md, journey 3: the replay demo streams real-shaped traffic
test("a replay streams messages into a fresh board", async ({ page }) => {
  await signIn(page, "coordinator");
  await page.goto("/command/replay");
  await page
    .getByRole("button", { name: /^(Start|Restart) replay$/ })
    .first()
    .click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();

  const disasters = (await (await page.request.get("/api/v1/disasters")).json()) as Disaster[];
  const replay = disasters
    .filter((d) => d.status === "replay")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/replay/${replay.id}/state`)).json()).emitted, {
      timeout: 60_000,
    })
    .toBeGreaterThan(0);

  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeHidden();
});
