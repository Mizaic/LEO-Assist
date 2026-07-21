import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Validation Lab smoke (replaces retired AI Summarisation playground e2e).
 *
 * Atlas: UN-4DCE95C8 / DI-A898556B / VT-22F3EF6A
 */
test.describe("Validation Lab (retired SBAR playground)", () => {
  test("loads Validation Lab chrome with the new-patient wizard", async ({
    page,
  }) => {
    await page.goto("/admin/knowledge?tab=validation-lab");
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("validation-lab-page")).toBeVisible();
    await expect(page.getByTestId("validation-lab-cases-panel")).toBeVisible();
    await expect(page.getByTestId("validation-lab-new-patient")).toBeVisible();
    await expect(page.getByTestId("create-patient-wizard")).toBeVisible();
    await expect(page.getByTestId("wizard-title")).toBeVisible();
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
