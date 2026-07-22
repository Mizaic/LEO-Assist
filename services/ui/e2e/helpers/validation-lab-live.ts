import type { Locator, Page } from "@playwright/test";

export function isLiveBackendConfigured(): boolean {
  return process.env.PLAYWRIGHT_LIVE_BACKEND === "1";
}

export function liveBackendSkipReason(): string | undefined {
  if (isLiveBackendConfigured()) {
    return undefined;
  }
  return "Set PLAYWRIGHT_LIVE_BACKEND=1 for G5.9 durable Validation Lab run.";
}

/** MUI TextField puts data-testid on the FormControl root, not the input. */
export function wizardField(page: Page, testId: string): Locator {
  return page.getByTestId(testId).locator("input, textarea").first();
}

/** E2E UI session is mocked; live Core API calls need service auth. */
export async function installLiveBackendServiceAuth(page: Page): Promise<void> {
  const secret = process.env.SERVICE_AUTH_SECRET?.trim();
  if (!secret) {
    throw new Error(
      "SERVICE_AUTH_SECRET is required for PLAYWRIGHT_LIVE_BACKEND=1.",
    );
  }
  await page.route("**/api/validation-lab**", async (route) => {
    const headers = {
      ...route.request().headers(),
      Authorization: `Bearer ${secret}`,
    };
    await route.continue({ headers });
  });
}
