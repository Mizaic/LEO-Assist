import { expect, test as setup } from "@playwright/test";
import path from "path";

const authFile = path.join(__dirname, ".auth", "user.json");

function isRemoteBaseUrl(baseURL: string): boolean {
  try {
    const host = new URL(baseURL).hostname;
    return host !== "localhost" && host !== "127.0.0.1";
  } catch {
    return false;
  }
}

async function authenticateWithEntra(
  page: import("@playwright/test").Page,
): Promise<void> {
  const email = process.env.PLAYWRIGHT_ENTRA_EMAIL?.trim();
  const password = process.env.PLAYWRIGHT_ENTRA_PASSWORD?.trim();
  if (!email || !password) {
    throw new Error(
      "Staging auth requires PLAYWRIGHT_ENTRA_EMAIL and PLAYWRIGHT_ENTRA_PASSWORD " +
        "(load from secrets/.env.secrets via validation-env.ts).",
    );
  }

  await page.goto("/sign-in");
  await page.getByRole("button", { name: /sign in with microsoft/i }).click();
  await page.waitForURL(/login\.microsoftonline\.com/, { timeout: 60_000 });
  await page.locator('input[type="email"]').fill(email);
  await page.getByRole("button", { name: /^next$/i }).click();
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.getByRole("button", { name: /^yes$/i }).click().catch(() => undefined);
  await page.waitForURL(/\/(operations|validation-lab|dashboard|$)/, {
    timeout: 120_000,
  });

  const session = await page.request.get("/auth/session");
  const body = await session.json();
  if (!body?.user) {
    throw new Error("Entra sign-in did not return an authenticated session.");
  }
}

/**
 * Auth setup for e2e tests.
 *
 * Local (default): NEXT_PUBLIC_E2E_MODE=true bypasses Entra and injects a mock
 * session when the Playwright webServer starts the dev app.
 *
 * Staging: set PLAYWRIGHT_BASE_URL to the validation host,
 * PLAYWRIGHT_REUSE_SERVER=true, and PLAYWRIGHT_ENTRA_EMAIL /
 * PLAYWRIGHT_ENTRA_PASSWORD from secrets/.env.secrets (never commit values).
 */
setup("authenticate", async ({ page, baseURL }) => {
  if (isRemoteBaseUrl(baseURL ?? "")) {
    await authenticateWithEntra(page);
    await page.context().storageState({ path: authFile });
    return;
  }

  // E2E mode serves a mock session from app/auth/session/route.ts. Do not open
  // "/" here: the dashboard polls /api/proxy/analytics/* via core-api on :8000,
  // which is not started in CI and prevents networkidle from ever settling.
  await expect
    .poll(async () => {
      const session = await page.request.get("/auth/session");
      const body = await session.json();
      return body?.user?.email ?? null;
    })
    .toBe("e2e.clinician@example.com");

  await page.context().storageState({ path: authFile });
});
