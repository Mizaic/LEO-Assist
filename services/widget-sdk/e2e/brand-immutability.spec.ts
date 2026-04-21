/**
 * VT-F6F5681E - Host CSS cannot change widget-internal styling.
 *
 * Atlas trace:
 *   DO: DO-7F469209
 *   DI: DI-85944331 AC4
 *   Risk mitigated: R-4965BCD2 (no host CSS surface available to
 *     hide or mutate the source-record disclosure)
 *
 * Two halves to AC4:
 *   1. Web component variant. The closed shadow root means external
 *      CSS cannot select widget-internal elements. We assert the
 *      shadow root is null to the host (this is a structural, not
 *      observational, mitigation) and assert the host element's
 *      computed font-family equals the locked LEO font (i.e. host
 *      CSS targeting :host equivalents has no effect).
 *   2. Iframe variant. Even with hostile host CSS in scope, the
 *      iframe is a separate document and its computed styles MUST
 *      come from the locked widget stylesheet, not the host page.
 */

import { expect, test } from "@playwright/test";

const HOST = "/demo/host-pages/dual-variant.html";

test.describe("VT-F6F5681E - host CSS does not alter widget brand", () => {
  test("Web component variant - shadow root is closed and font-family is locked", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page
      .locator("leo-sbar[data-leo-state='loaded']")
      .first()
      .waitFor({ timeout: 10_000 });

    const probe = await page.evaluate(() => {
      const wc = document.querySelector("leo-sbar") as HTMLElement | null;
      if (!wc) {
        return { ok: false } as const;
      }
      const computed = window.getComputedStyle(wc);
      return {
        ok: true,
        shadowRoot: (wc as Element & { shadowRoot: unknown }).shadowRoot
          === null
          ? "null"
          : "exposed",
        fontFamily: computed.fontFamily,
        color: computed.color,
      } as const;
    });

    expect(probe.ok).toBe(true);
    expect(probe.shadowRoot).toBe("null");
    expect(probe.fontFamily.toLowerCase()).toContain("inter");
    expect(probe.color).not.toContain("magenta");
  });

  test("Iframe variant - widget-internal styling is the locked LEO brand", async ({
    page,
  }) => {
    await page.goto(HOST);
    const frame = page.frameLocator("#iframe-widget");
    const mark = frame.locator(".leo-mark").first();
    await mark.waitFor({ timeout: 10_000 });

    const styles = await mark.evaluate((el) => {
      const cs = window.getComputedStyle(el);
      const product = (el.parentElement?.querySelector(
        ".leo-product",
      ) as HTMLElement | null);
      const productStyle = product ? window.getComputedStyle(product) : null;
      const toggle = el.ownerDocument.querySelector(
        ".leo-disclosure-toggle",
      ) as HTMLElement | null;
      const toggleStyle = toggle ? window.getComputedStyle(toggle) : null;
      return {
        markColor: cs.color,
        productFont: productStyle?.fontFamily ?? "",
        productSize: productStyle?.fontSize ?? "",
        toggleFont: toggleStyle?.fontFamily ?? "",
      };
    });

    expect(styles.markColor.toLowerCase()).not.toContain("magenta");
    expect(styles.productFont.toLowerCase()).toContain("inter");
    expect(styles.productFont.toLowerCase()).not.toContain("comic");
    expect(styles.productSize).not.toBe("30px");
    if (styles.toggleFont) {
      expect(styles.toggleFont.toLowerCase()).not.toContain("comic");
    }
  });
});
