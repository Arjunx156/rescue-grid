import { expect, test } from "@playwright/test";
import { door, liveDisaster, publicStatus, signIn, watch, XRW } from "./helpers";

// docs/03-App-Flow.md, journey 2: a location the system is unsure of gets a human pin
test("a coordinator places an uncertain pin and the case moves on", async ({ page }) => {
  // no pin and no place name the gazetteer can trust
  const sent = await page.request.post("/api/v1/sos", {
    headers: XRW,
    data: {
      text: `Door ${door()}, 3 people on the terrace next to the old water tank, water up to the knees`,
      people: 3,
      needs: ["rescue"],
    },
  });
  expect(sent.ok(), await sent.text()).toBeTruthy();
  const { tracking_code: code } = await sent.json();
  await expect.poll(() => publicStatus(page.request, code)).toBe("reviewing");

  await signIn(page, "coordinator");
  const { disaster_id } = await liveDisaster(page.request);
  await watch(page, disaster_id);
  await page.goto("/command/review");
  await page
    .getByRole("listitem")
    .filter({ hasText: code })
    .getByRole("button", { name: /^(Place|Check) the pin$/ })
    .click();

  const map = page.locator(".maplibregl-canvas");
  await expect(map).toBeVisible();
  const box = await map.boundingBox();
  if (!box) throw new Error("map has no size");
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.getByRole("button", { name: "Save pin" }).click();
  await expect(page.getByText("Location saved. The plan will update.")).toBeVisible();

  await expect.poll(() => publicStatus(page.request, code)).not.toBe("reviewing");
});
