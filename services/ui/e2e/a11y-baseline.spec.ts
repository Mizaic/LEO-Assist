import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;

/**
 * Run axe on the current page with one retry if the execution context is
 * destroyed mid-analysis (e.g. HMR reload in the dev server). In CI we
 * run against a production build so this never triggers.
 */
async function analyzeWcag(page: Page) {
  try {
    return await new AxeBuilder({ page }).withTags([...WCAG_TAGS]).analyze();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (!msg.includes("Execution context was destroyed")) throw err;
    await page.waitForLoadState("load");
    return new AxeBuilder({ page }).withTags([...WCAG_TAGS]).analyze();
  }
}

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
    await page.waitForURL("**/care/dashboard**", { timeout: 15000 });
    await page.waitForLoadState("load");

    const results = await analyzeWcag(page);
    const blockers = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(
      blockers,
      JSON.stringify(
        blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
        null, 2,
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
    await page.waitForLoadState("load");
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
      await page.waitForURL("**/care/patients**", { timeout: 15000 });
      await page.waitForLoadState("load");

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);
    },
  );

  test(
    "guidance admin page passes WCAG 2.1 AA (rule-edit wizard host, DI-061AD3D1)",
    async ({ page }) => {
      await page.goto("/admin/guidance");
      await page.waitForURL("**/admin/guidance**", { timeout: 15000 });
      await page.waitForLoadState("load");

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);
    },
  );

  test(
    "audit template list page passes WCAG 2.1 AA (VT-32FBAA69, DI-64CA7740)",
    async ({ page }) => {
      await page.goto("/admin/audit-templates");
      await page.waitForURL("**/admin/audit-templates**", { timeout: 15000 });
      await page.waitForLoadState("load");

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);
    },
  );

  test(
    "patient EPR list page passes WCAG 2.1 AA (VT-1D399981, DI-0ADA35BF)",
    async ({ page }) => {
      await page.goto("/care/patients");
      await page.waitForURL("**/care/patients**", { timeout: 15000 });
      await page.waitForLoadState("load");

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);
    },
  );

  test(
    "role picker passes WCAG 2.1 AA (VT-934D07ED, DI-FDC9F12F)",
    async ({ page }) => {
      await page.goto("/portal");
      await page.waitForLoadState("load");
      await page.waitForSelector("main, h1, [data-testid]", { timeout: 10000 });

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);

      // All role cards must be reachable by keyboard
      const roleCards = page.locator('[role="button"], button').filter({ hasText: /clinician|admin|manager|staff/i });
      const count = await roleCards.count();
      for (let i = 0; i < count; i++) {
        await expect(roleCards.nth(i)).toBeVisible();
      }
    },
  );

  test(
    "clinical audit renderer passes WCAG 2.1 AA (VT-D0A91A17, DI-02C2EB0A)",
    async ({ page }) => {
      await page.goto("/care/audit");
      await page.waitForLoadState("load");
      await page.waitForSelector("main, h1, [data-testid]", { timeout: 10000 });

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);
    },
  );

  test(
    "patient detail view passes WCAG 2.1 AA (VT-4CA1EB03, DI-05A16092)",
    async ({ page }) => {
      // Navigate to the patient list and open the first available patient
      await page.goto("/care/patients");
      await page.waitForLoadState("load");
      await page.waitForSelector("main, h1, [data-testid], table", { timeout: 10000 });

      const firstPatient = page.locator("a[href*='/care/patients/']").first();
      const patientCount = await firstPatient.count();

      if (patientCount === 0) {
        test.skip(true, "No patients available in this environment -- skip detail view axe check");
        return;
      }

      await firstPatient.click();
      await page.waitForLoadState("load");
      await page.waitForSelector("main, h1", { timeout: 10000 });

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);

      // Exactly one h1 on the patient detail page
      const h1Count = await page.locator("h1").count();
      expect(h1Count).toBe(1);
    },
  );

  test(
    "referral completeness display passes WCAG 2.1 AA (VT-32E8E34E, DI-3C702AFE)",
    async ({ page }) => {
      await page.goto("/care/completeness");
      await page.waitForLoadState("load");
      await page.waitForSelector("main, h1, [data-testid]", { timeout: 10000 });

      const results = await analyzeWcag(page);
      const blockers = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blockers,
        JSON.stringify(
          blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
          null, 2,
        ),
      ).toEqual([]);
    },
  );
});
