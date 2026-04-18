import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * VT-LEO-AI-185 -- AI Summarisation Playground end-to-end smoke
 *
 * Verifies the SBAR playground tab under /admin/knowledge:
 *   - Loads with the test-only safety banner up front (R-LEO-AI-185).
 *   - Renders all input controls and a disabled submit until the
 *     reviewer enters a patient id and at least one background source.
 *   - Has zero critical or serious axe violations on the chrome.
 *
 * Submitting the job and watching the SSE stream is gated on a worker
 * being reachable, so we stop short of clicking submit -- the
 * orchestrator is exercised by the Python integration tests.
 */
test.describe("SBAR playground (VT-LEO-AI-185)", () => {
  test("renders the safety banner and submit form", async ({ page }) => {
    await page.goto("/admin/knowledge?tab=ai-summarisation");
    await page.waitForLoadState("networkidle");

    await expect(
      page.getByTestId("sbar-test-only-banner"),
    ).toContainText("Test only");
    await expect(page.getByTestId("sbar-patient-id")).toBeVisible();
    await expect(page.getByTestId("sbar-add-artifact")).toBeVisible();
    await expect(page.getByTestId("sbar-add-background")).toBeVisible();
    await expect(page.getByTestId("sbar-submit")).toBeVisible();
    await expect(page.getByTestId("sbar-submit")).toBeDisabled();
  });

  test("submit becomes enabled once required fields are populated", async ({
    page,
  }) => {
    await page.goto("/admin/knowledge?tab=ai-summarisation");
    await page.waitForLoadState("networkidle");

    await page.getByTestId("sbar-patient-id").fill("pat-test-1");
    const bgInputs = page.locator('input[label="Node id"], input[aria-label]');
    await page.getByLabel("Node id").first().fill("enc-test-1");

    await expect(page.getByTestId("sbar-submit")).toBeEnabled();
  });

  test("zero critical or serious axe violations", async ({ page }) => {
    await page.goto("/admin/knowledge?tab=ai-summarisation");
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const blockers = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(
      blockers,
      JSON.stringify(blockers, null, 2),
    ).toEqual([]);
  });
});
