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
  await page.context().storageState({ path: authFile });
});
