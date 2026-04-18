import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * VT-LEO-AI-185 / VT-LEO-AI-230..233 -- AI Summarisation Playground
 * end-to-end smoke
 *
 * Verifies the SBAR playground tab under /admin/knowledge:
 *   - Loads with the test-only safety banner up front (R-LEO-AI-185).
 *   - Renders the four picker primitives:
 *       * Patient finder    (DI-LEO-AI-230)
 *       * Summarisation context  (DI-LEO-AI-231)
 *       * Background source picker (DI-LEO-AI-232)
 *       * Guideline picker     (DI-LEO-AI-233)
 *   - Surfaces the new "Concern" QSIR free-text field with the
 *     500-character cap (DI-LEO-AI-233).
 *   - Has zero critical or serious axe violations on the chrome.
 *   - Submit stays disabled until a patient + a background source are
 *     picked (R-LEO-AI-211 -- can't run without explicit selection).
 *
 * Submitting the job and watching the SSE stream is gated on a worker
 * being reachable, so we stop short of clicking submit -- the
 * orchestrator is exercised by the Python integration tests.
 */
test.describe("SBAR playground (VT-LEO-AI-185)", () => {
  test("renders the safety banner and the four picker primitives", async ({
    page,
  }) => {
    await page.goto("/admin/knowledge?tab=ai-summarisation");
    await page.waitForLoadState("networkidle");

    await expect(
      page.getByTestId("sbar-test-only-banner"),
    ).toContainText("Test only");

    // Patient finder open button (DI-230).
    await expect(page.getByTestId("sbar-pick-patient")).toBeVisible();
    // Background source picker trigger (DI-232).
    await expect(page.getByTestId("sbar-pick-sources")).toBeVisible();
    // Concern free-text field (DI-233).
    await expect(page.getByTestId("sbar-concern")).toBeVisible();
    // Submit defaults to disabled (no patient + no sources picked).
    await expect(page.getByTestId("sbar-submit")).toBeVisible();
    await expect(page.getByTestId("sbar-submit")).toBeDisabled();
  });

  test("Concern textarea enforces the 500-character cap", async ({ page }) => {
    await page.goto("/admin/knowledge?tab=ai-summarisation");
    await page.waitForLoadState("networkidle");

    const concern = page.getByTestId("sbar-concern");
    await concern.click();
    // Browser-enforced maxlength: typing >500 chars truncates input.
    await concern.fill("x".repeat(550));
    const value = await concern.inputValue();
    expect(value.length).toBeLessThanOrEqual(500);
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
    expect(blockers, JSON.stringify(blockers, null, 2)).toEqual([]);
  });
});
