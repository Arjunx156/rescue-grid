import { devices, expect, test } from "@playwright/test";
import { door, liveDisaster, publicStatus, signIn, somewhereInChennai, watch } from "./helpers";

// docs/03-App-Flow.md, journey 1: an SOS becomes a rescue
test("an SOS becomes a rescue", async ({ browser }) => {
  // a relative asks for help from their phone
  const phone = await browser.newContext({
    ...devices["Pixel 7"],
    geolocation: somewhereInChennai(),
    permissions: ["geolocation"],
  });
  const sos = await phone.newPage();
  await sos.goto("/sos");
  await sos
    .getByLabel("What is happening?")
    .fill(
      `Door no ${door()}, my father (78, on dialysis) and mother stuck on the first floor. ` +
        "Water is waist deep and rising.",
    );
  await sos.getByRole("button", { name: "One more" }).click();
  await sos.getByRole("button", { name: "Use my current location" }).click();
  await expect(sos.getByRole("button", { name: "Location added" })).toBeVisible();
  await sos.getByRole("button", { name: "Send SOS" }).click();
  await sos.waitForURL(/\/sos\/RG-/);
  const code = sos.url().split("/").pop() as string;
  await expect(sos.getByRole("heading", { name: code })).toBeVisible();

  // the pipeline reads, places and scores it
  await expect.poll(() => publicStatus(sos.request, code)).not.toBe("received");

  // the coordinator finds it and sends a boat
  const desk = await browser.newContext();
  const coord = await desk.newPage();
  await signIn(coord, "coordinator");
  const { disaster_id } = await liveDisaster(coord.request);
  await watch(coord, disaster_id);
  await coord.goto("/command");
  // the queue fills once the app is live, so shortcuts are wired by then
  await expect(coord.getByRole("region", { name: "Open cases" }).getByRole("button").first()).toBeVisible();
  await coord.keyboard.press("Control+k");
  await coord.getByRole("combobox", { name: "Search cases" }).fill(code);
  await coord.getByRole("option").filter({ hasText: code }).click();
  await coord.getByRole("button", { name: /^(Assign team|Reassign)$/ }).click();
  const dialog = coord.getByRole("dialog", { name: `Assign a team to ${code}` });
  await dialog.getByRole("listitem").filter({ hasText: "B-01" }).getByRole("button", { name: "Assign" }).click();
  await expect(coord.getByText(`B-01 assigned to ${code}`)).toBeVisible();

  // B-01's lead works the job from the field app
  const cases = await (await coord.request.get(`/api/v1/disasters/${disaster_id}/cases?status=open`)).json();
  const theCase = cases.find((c: { tracking_code: string }) => c.tracking_code === code);
  const assignments = await (await coord.request.get(`/api/v1/disasters/${disaster_id}/assignments`)).json();
  const job = assignments.find(
    (a: { case_id: string; status: string }) =>
      a.case_id === theCase.id && !["cancelled", "failed", "completed"].includes(a.status),
  );
  const boat = await browser.newContext({ ...devices["Pixel 7"] });
  const crew = await boat.newPage();
  await signIn(crew, "field_lead");
  await crew.goto(`/field/assignment/${job.id}`);
  await crew.getByRole("button", { name: "Start", exact: true }).click();
  await crew.getByRole("button", { name: "Reached", exact: true }).click();
  await crew.getByRole("button", { name: "Rescued", exact: true }).click();
  await crew.getByRole("button", { name: "Confirm rescue" }).click();

  // and the family sees it close
  await expect.poll(() => publicStatus(sos.request, code)).toBe("rescued");
  await sos.reload();
  await expect(sos.getByText("Rescued", { exact: true }).first()).toBeVisible();

  await Promise.all([phone.close(), desk.close(), boat.close()]);
});
