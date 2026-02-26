import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test("dashboard page loads with heading", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: /Overview/i })).toBeVisible();
  });

  test("KPI cards section is visible", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    const kpiSection = page.getByText(/Referral|Diagnosis|Treatment|Consultations/i);
    await expect(kpiSection.first()).toBeVisible();
  });

  test("referral pathways chart section renders", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toContainText(/referral pathway/i);
  });

  test("safety netting alerts section is visible", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toContainText(/safety netting/i);
  });
});
