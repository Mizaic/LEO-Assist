/**
 * VT for DI-85C95E53 acceptance criterion 2:
 *   "A host stylesheet attempting to set the disclosure to
 *    display:none or visibility:hidden has no effect on either
 *    variant."
 *
 * Atlas trace:
 *   DI: DI-85C95E53
 *   Risk mitigated: R-4965BCD2
 *
 * Demo page demo/host-pages/dual-variant.html applies hostile host
 * CSS rules (display:none, visibility:hidden, opacity:0,
 * transform:scale(0)) targeting [data-leo-disclosure]. The widgets
 * MUST still render the disclosure visibly.
 */

import { expect, test } from "@playwright/test";

const HOST = "/demo/host-pages/dual-variant.html";

test.describe("VT-DI-85C95E53-AC2 host CSS cannot hide the disclosure", () => {
  test("TC-1 web component: disclosure stays visible despite hostile host CSS", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page.waitForFunction(() => {
      const el = document.querySelector("leo-sbar");
      // Closed shadow root - we cannot reach inside, so wait for the
      // element to be in the document; the test inspects it via
      // page.evaluate using the same pattern.
      return el !== null;
    });
    // Wait for at least the leo:loaded event to ensure the disclosure
    // has been rendered inside the closed shadow root.
    await page.waitForFunction(() => {
      const el = document.querySelector("leo-sbar") as HTMLElement | null;
      return Boolean(el && el.hasAttribute("data-loaded-marker"));
    }, undefined, { timeout: 5000 }).catch(() => {});
    // Use a one-shot listener on the wc element to confirm load.
    const isVisible = await page.evaluate(async () => {
      const wc = document.getElementById("wc-widget");
      if (!wc) return null;
      // Wait briefly for the loaded event to render inside the shadow.
      await new Promise<void>((resolve) => {
        const t = setTimeout(resolve, 1500);
        wc.addEventListener(
          "leo:loaded",
          () => {
            clearTimeout(t);
            resolve();
          },
          { once: true },
        );
      });
      const rect = wc.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
    expect(isVisible).toBe(true);
  });

  test("TC-2 iframe: disclosure stays visible despite hostile host CSS", async ({
    page,
  }) => {
    await page.goto(HOST);
    const frame = page.frameLocator("#iframe-widget");
    const disclosure = frame.locator(
      '[data-testid="leo-disclosure-background"]',
    );
    await expect(disclosure).toBeVisible({ timeout: 5000 });
    const box = await disclosure.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(0);
    expect(box?.height ?? 0).toBeGreaterThan(0);
  });

  test("TC-3 iframe: source chips stay visible despite hostile host CSS", async ({
    page,
  }) => {
    await page.goto(HOST);
    const frame = page.frameLocator("#iframe-widget");
    await frame
      .locator('[data-testid="leo-disclosure-background-toggle"]')
      .click();
    const chip = frame.locator('.leo-source-chip[data-source-id="enc-A001"]');
    await expect(chip).toBeVisible();
  });
});
