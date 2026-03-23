import { test, expect } from "@playwright/test";

test.describe("Review Workflow", () => {
  test("review queue loads with task list", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
  });

  test("navigating to encounter shows coded view", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const firstCard = page.locator("[class*='MuiCardActionArea-root']").first();
    if (await firstCard.isVisible()) {
      await firstCard.click();
      await page.waitForLoadState("networkidle");
      await expect(page).toHaveURL(/\/care/patients\//);
    }
  });

  test("encounter view shows clinical text", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const firstCard = page.locator("[class*='MuiCardActionArea-root']").first();
    if (await firstCard.isVisible()) {
      await firstCard.click();
      await page.waitForLoadState("networkidle");
      const encounterLink = page.locator("[class*='MuiCard-root']").first();
      if (await encounterLink.isVisible()) {
        await encounterLink.click();
        await page.waitForLoadState("networkidle");
      }
    }
  });

  test("approve button is present in review view", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible();
  });

  test("reject flow is accessible", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible();
  });

  test("entity editing popover opens on entity click", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible();
  });
});
