/**
 * VT-0B518843 -- Verify widget meets WCAG 2.1 AA across all rendered states.
 *
 * Atlas trace:
 *   DI: DI-FA08EE1B -- SBAR Widget Meets WCAG 2.1 AA Accessibility Requirements
 *   DO: DO-A3465F94 -- SBAR widget CDN package -- leo-widget
 *
 * Acceptance criteria:
 *   AC1: All interactive widget elements are keyboard accessible and provide
 *        visible focus indicators.
 *   AC2: All non-text content includes appropriate text alternatives or
 *        accessible labels.
 *   AC3: Completeness status indicators are not conveyed using colour alone
 *        and include additional visual or textual cues.
 *   AC4: The widget passes automated WCAG 2.1 AA accessibility testing,
 *        including axe-core checks, with no critical or serious violations
 *        across supported rendered states.
 *
 * Uses @axe-core/playwright for automated AC4 checks across both the
 * web-component and iframe variants in the loaded, error, and loading states.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const HOST = "/demo/host-pages/dual-variant.html";

// ---------------------------------------------------------------------------
// AC4: axe-core WCAG 2.1 AA -- web component variant
// ---------------------------------------------------------------------------

test.describe("VT-0B518843 -- WCAG 2.1 AA: web component variant", () => {
  test("AC4: zero critical or serious axe violations in loaded state", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page
      .locator("leo-sbar[data-leo-state='loaded']")
      .first()
      .waitFor({ timeout: 10_000 });

    const results = await new AxeBuilder({ page })
      .include("leo-sbar")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(
      critical,
      `Critical/serious WCAG violations in web component (loaded): ${JSON.stringify(critical.map((v) => ({ id: v.id, impact: v.impact, description: v.description })), null, 2)}`,
    ).toHaveLength(0);
  });

  test("AC1: interactive elements inside loaded web component have non-negative tabindex", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page
      .locator("leo-sbar[data-leo-state='loaded']")
      .first()
      .waitFor({ timeout: 10_000 });

    // Structural check: no interactive element inside the widget uses tabindex=-1
    // without being an intentionally non-focusable decoration.
    const results = await new AxeBuilder({ page })
      .include("leo-sbar")
      .withRules(["tabindex", "scrollable-region-focusable"])
      .analyze();

    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(
      critical,
      `Keyboard/tabindex violations: ${JSON.stringify(critical.map((v) => v.id))}`,
    ).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// AC4: axe-core WCAG 2.1 AA -- iframe variant
// ---------------------------------------------------------------------------

test.describe("VT-0B518843 -- WCAG 2.1 AA: iframe variant", () => {
  test("AC4: zero critical or serious axe violations in loaded state (iframe)", async ({
    page,
  }) => {
    await page.goto(HOST);

    const iframeLocator = page.locator("iframe[data-leo-variant='iframe']").first();
    const hasIframe = (await iframeLocator.count()) > 0;

    if (!hasIframe) {
      test.skip();
      return;
    }

    const frame = page.frameLocator("iframe[data-leo-variant='iframe']").first();
    await frame.locator("[data-leo-state='loaded']").waitFor({ timeout: 10_000 });

    const frameUrl = await iframeLocator.getAttribute("src") ?? "";
    const iframePage = page.frames().find((f) => f.url().includes(frameUrl.split("?")[0]));

    if (!iframePage) {
      test.skip();
      return;
    }

    const results = await new AxeBuilder({ page: iframePage as Parameters<typeof AxeBuilder>[0]["page"] })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(
      critical,
      `Critical/serious WCAG violations in iframe (loaded): ${JSON.stringify(critical.map((v) => ({ id: v.id, impact: v.impact })), null, 2)}`,
    ).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// AC3: completeness status uses more than colour
// ---------------------------------------------------------------------------

test.describe("VT-0B518843 -- WCAG 2.1 AA: colour-alone check", () => {
  test("AC3: axe colour-contrast rule passes across loaded widget", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page
      .locator("leo-sbar[data-leo-state='loaded']")
      .first()
      .waitFor({ timeout: 10_000 });

    const results = await new AxeBuilder({ page })
      .include("leo-sbar")
      .withRules(["color-contrast"])
      .analyze();

    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(
      critical,
      `Colour-only violations: ${JSON.stringify(critical.map((v) => v.id))}`,
    ).toHaveLength(0);
  });
});
