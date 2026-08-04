import { test, expect, waitForPageSettled } from "./fixtures";

test.describe("Dashboard", () => {
  test("dashboard page loads with heading", async ({ page }) => {
    await page.goto("/care/dashboard");
    await waitForPageSettled(page);
    await expect(page.getByRole("heading", { name: "Care Overview", exact: true })).toBeVisible();
  });

  test("KPI cards section is visible", async ({ page }) => {
    await page.goto("/care/dashboard");
    await waitForPageSettled(page);
    const kpiSection = page.getByText(/Cancer pathways|Referrals by cancer type/i);
    await expect(kpiSection.first()).toBeVisible();
  });

  test("referral pathways chart section renders", async ({ page }) => {
    await page.goto("/care/dashboard");
    await waitForPageSettled(page);
    await expect(page.locator("body")).toContainText(/Referrals by cancer type/i);
  });

  test("safety netting alerts section is visible", async ({ page }) => {
    await page.goto("/care/dashboard");
    await waitForPageSettled(page);
    await expect(page.locator("body")).toContainText(/safety netting/i);
  });
});
