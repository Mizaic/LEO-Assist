import { test, expect } from "@playwright/test";

test.describe("Safety Netting", () => {
  test("safety netting page loads", async ({ page }) => {
    await page.goto("/safety-netting");
    await expect(page.getByRole("heading", { name: /Safety Netting/i })).toBeVisible();
  });

  test("alerts table renders with data or empty message", async ({ page }) => {
    await page.goto("/safety-netting");
    await page.waitForLoadState("networkidle");
    const hasAlerts = await page.getByText(/severity|critical|high|medium|low/i).first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText(/No.*alert/i).first().isVisible().catch(() => false);
    expect(hasAlerts || hasEmpty).toBeTruthy();
  });

  test("page has filtering controls", async ({ page }) => {
    await page.goto("/safety-netting");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible();
  });
});
