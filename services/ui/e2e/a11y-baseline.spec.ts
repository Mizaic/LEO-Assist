import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Verifies the WCAG 2.1 AA baseline for a representative staff route
 * rendering the AppShell. Patient-reachable routes are verified in the
 * per-route Playwright specs added in later waves.
 *
 * See VT-LEO-AI-115.
 */
test.describe("a11y baseline (VT-LEO-AI-115)", () => {
  test("care dashboard has zero critical or serious axe violations", async ({
    page,
  }) => {
    await page.goto("/care/dashboard");
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const blockers = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );

    expect(
      blockers,
      JSON.stringify(
        blockers.map((v) => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          nodes: v.nodes.map((n) => n.target).flat(),
        })),
        null,
        2,
      ),
    ).toEqual([]);
  });

  test("skip link is reachable via keyboard and targets main content", async ({
    page,
  }) => {
    await page.goto("/care/dashboard");
    await page.keyboard.press("Tab");
    const focused = page.locator(":focus");
    await expect(focused).toHaveText(/skip to main content/i);
    await expect(focused).toHaveAttribute("href", "#main-content");
  });

  test("AppShell rail or full drawer announces the active route", async ({
    page,
  }) => {
    await page.goto("/care/audit");
    await page.waitForLoadState("networkidle");
    const activeItems = page.locator('[aria-current="page"]');
    await expect(activeItems.first()).toBeVisible();
  });

  test(
    "in_review patient list passes WCAG 2.1 AA (Reconcile Pathway entry, DI-9DCC9F84)",
    async ({ page }) => {
      // The Reconcile Pathway drawer is rendered from the in_review
      // patient view; auditing the patient list with this filter
      // exercises the surface that contains the entry button + chip
      // affordances introduced by Wave E.
      await page.goto("/care/patients?lifecycle_bucket=in_review");
      await page.waitForLoadState("networkidle");

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );

      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            nodes: v.nodes.map((n) => n.target).flat(),
          })),
          null,
          2,
        ),
      ).toEqual([]);
    },
  );
});
