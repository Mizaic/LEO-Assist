import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Validation Lab smoke (replaces retired AI Summarisation playground e2e).
 *
 * Atlas: UN-4DCE95C8 / DI-A898556B / VT-22F3EF6A
 */
test.describe("Validation Lab (retired SBAR playground)", () => {
  test("loads Validation Lab chrome with gold + run controls", async ({
    page,
  }) => {
    await page.goto("/admin/knowledge?tab=validation-lab");
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("validation-lab-page")).toBeVisible();
    await expect(page.getByTestId("validation-lab-tab-cases")).toBeVisible();
    await expect(page.getByTestId("validation-lab-tab-fixtures")).toBeVisible();
    await expect(page.getByTestId("validation-lab-create")).toBeVisible();
    await expect(page.getByTestId("validation-lab-run")).toBeVisible();
    await expect(page.getByTestId("validation-lab-promote")).toBeVisible();
    await expect(page.getByTestId("validation-lab-dry-run")).toBeVisible();
    await expect(
      page.getByTestId("validation-lab-gold-entities"),
    ).toBeVisible();
  });

  test("Fixtures view hosts the former Test Patients library", async ({
    page,
  }) => {
    await page.goto("/admin/knowledge?tab=validation-lab&view=fixtures");
    await page.waitForLoadState("networkidle");
    await expect(
      page.getByTestId("validation-lab-fixtures-panel"),
    ).toBeVisible();
    await expect(
      page.getByTestId("test-patients-lab-gold-notice"),
    ).toBeVisible();
  });

  test("legacy ai-summarisation URL redirects toward Validation Lab", async ({
    page,
  }) => {
    await page.goto("/admin/ai-summarisation");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/validation-lab/);
  });

  test("zero critical or serious axe violations", async ({ page }) => {
    await page.goto("/admin/knowledge?tab=validation-lab");
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const blockers = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(blockers).toEqual([]);
  });
});
