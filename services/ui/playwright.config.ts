import { defineConfig, devices } from "@playwright/test";
import { loadPlaywrightEnv } from "./e2e/helpers/validation-env";

loadPlaywrightEnv();

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const devPort = new URL(baseURL).port || "3000";
const isRemoteBaseUrl = (() => {
  try {
    const host = new URL(baseURL).hostname;
    return host !== "localhost" && host !== "127.0.0.1";
  } catch {
    return false;
  }
})();
const skipLocalWebServer =
  process.env.PLAYWRIGHT_SKIP_WEBSERVER === "1" || isRemoteBaseUrl;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",

  use: {
    baseURL,
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "e2e/.auth/user.json",
        colorScheme: "light",
        contextOptions: { reducedMotion: "reduce" },
      },
      dependencies: ["setup"],
    },
    {
      name: "firefox",
      use: {
        ...devices["Desktop Firefox"],
        storageState: "e2e/.auth/user.json",
      },
      dependencies: ["setup"],
    },
    {
      name: "mobile-chrome",
      use: {
        ...devices["Pixel 5"],
        storageState: "e2e/.auth/user.json",
      },
      dependencies: ["setup"],
    },
    // Fully API-stubbed journeys that mock auth/session themselves.
    {
      name: "stubbed-chromium",
      testMatch:
        /(local-concepts-wizard|surface-forms-local-concept-wizard|validation-lab-brainstorm-drawer|validation-lab-mark-as-wrong|work-task-dialogs-walkthrough|val-soft-gate-1513-ab092472|val-form-not-recognised-bc73aa10|val-add-form-template-skip-boxes)\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        storageState: { cookies: [], origins: [] },
        colorScheme: "light",
        contextOptions: { reducedMotion: "reduce" },
      },
    },
  ],

  ...(skipLocalWebServer
    ? {}
    : {
        webServer: {
          command: `cross-env NEXT_PUBLIC_E2E_MODE=true PORT=${devPort} npm run dev`,
          url: baseURL,
          reuseExistingServer: process.env.PLAYWRIGHT_REUSE_SERVER === "true",
        },
      }),
});
