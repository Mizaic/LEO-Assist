import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * VT-LEO-AI-171 (Wave E Phase 7): smoke + a11y baseline for the eight
 * Knowledge tabs at /admin/knowledge. Confirms each tab loads without
 * a hard error and that the page chrome has no critical or serious
 * axe violations on the wrapper layout.
 *
 * The tab keys come from TABS in
 * services/ui/src/app/admin/knowledge/page.tsx and form part of the
 * URL contract; if a tab is renamed there it must be updated here.
 */

const KNOWLEDGE_TABS = [
  "training-data",
  "surface-forms",
  "context-rules",
  "ai-instructions",
  "clinical-guidelines",
  "pathways",
  "domains",
  "terminology",
] as const;

test.describe("knowledge tabs (VT-LEO-AI-171)", () => {
  for (const tab of KNOWLEDGE_TABS) {
    test(`tab ${tab} loads`, async ({ page }) => {
      await page.goto(`/admin/knowledge?tab=${tab}`);
      await page.waitForLoadState("networkidle");
      await expect(page).toHaveURL(new RegExp(`tab=${tab}`));
    });

    test(`tab ${tab} has zero critical or serious axe violations`, async ({
      page,
    }) => {
      await page.goto(`/admin/knowledge?tab=${tab}`);
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
  }
});
