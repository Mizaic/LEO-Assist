import { test as setup } from "@playwright/test";
import path from "path";

const authFile = path.join(__dirname, ".auth", "user.json");

/**
 * Auth setup for e2e tests.
 *
 * When NEXT_PUBLIC_E2E_MODE=true the app bypasses Entra ID auth
 * and injects a mock session, so we just need to visit the app
 * once to establish the cookie/storage state.
 *
 * For production-like testing, replace this with a real Entra ID
 * login flow using Playwright's page.fill/click on the Microsoft
 * sign-in form.
 */
setup("authenticate", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const session = await page.request.get("/auth/session");
  const body = await session.json();
  if (!body?.user) {
    throw new Error("E2E auth mode did not return an authenticated session.");
  }
  await page.context().storageState({ path: authFile });
});
