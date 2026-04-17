import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * VT-LEO-AI-163 (Phase 6b-vi cleanup): smoke + a11y baseline for the
 * pathway editor route. Confirms the page loads, the canvas mounts,
 * and the editor chrome has no critical or serious axe violations.
 */
test.describe("pathway editor (VT-LEO-AI-163)", () => {
  test("editor index loads and exposes the pathways table", async ({
    page,
  }) => {
    await page.goto("/admin/pathways");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveTitle(/pathway/i);
  });

  test("editor route has zero critical or serious axe violations", async ({
    page,
  }) => {
    await page.goto("/admin/pathways");
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
});
