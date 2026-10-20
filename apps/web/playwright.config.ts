import { defineConfig, devices } from "@playwright/test";

const CI = !!process.env.CI;

// journeys run against a live stack: `just dev` locally, the built app in CI
export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.e2e.ts",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  workers: 1,
  retries: CI ? 1 : 0,
  reporter: CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3100",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chrome",
      // locally use the installed Chrome; CI installs Playwright's Chromium
      use: { ...devices["Desktop Chrome"], channel: CI ? undefined : "chrome" },
    },
  ],
});
