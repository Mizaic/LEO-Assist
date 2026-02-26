import { test, expect } from "@playwright/test";

test.describe("Referral Pathways", () => {
  test("referral pathways page loads", async ({ page }) => {
    await page.goto("/episodes");
    await expect(page.getByRole("heading", { name: /Referral Pathways/i })).toBeVisible();
  });

  test("referral pathways page shows list or empty message", async ({ page }) => {
    await page.goto("/episodes");
    const card = page.locator("[class*='MuiCard-root']").first();
    const empty = page.getByText(/No referral pathways found/i);
    await expect(card.or(empty)).toBeVisible({ timeout: 15000 });
  });

  test("pathway timeline shows milestones when pathway is selected", async ({ page }) => {
    await page.goto("/episodes");
    const card = page.locator("[class*='MuiCard-root']").first();
    const empty = page.getByText(/No referral pathways found/i);
    await expect(card.or(empty)).toBeVisible({ timeout: 15000 });

    if (await card.isVisible().catch(() => false)) {
      await card.click({ force: true });
      const stepper = page.locator("[class*='MuiStepper-root']");
      const emptyMilestones = page.getByText(/No milestones recorded/i);
      await expect(stepper.or(emptyMilestones)).toBeVisible({ timeout: 10000 });
    }
  });
});
