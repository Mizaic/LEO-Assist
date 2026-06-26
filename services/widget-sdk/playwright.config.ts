import { defineConfig, devices } from "@playwright/test";

// LEO widget SDK Playwright config.
//
// Atlas trace: VTs for DI-85C95E53 acceptance criteria 2, 3, 4
//   (host-CSS isolation, host-JS isolation, embed-contract parity).
// Look up: get_design_control(dc_type="design-input", dc_id="DI-85C95E53").
//
// The demo server (`npm run demo`) serves a static page at
// http://localhost:5173 hosting both widget variants side-by-side. That
// page is the AC fixture for the trust-boundary verification tests.

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run demo",
    url: "http://localhost:5173/demo/host-pages/dual-variant.html",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
