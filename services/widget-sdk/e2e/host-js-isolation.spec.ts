/**
 * VT for DI-85C95E53 acceptance criterion 3:
 *   "A host JS attempting to query or mutate widget-internal DOM
 *    (closed shadow root in the web-component variant; cross-origin
 *    frame in the iframe variant) is rejected by browser sandboxing."
 *
 * Atlas trace:
 *   DI: DI-85C95E53
 *   Risk mitigated: R-4965BCD2
 *
 * Web component: element.shadowRoot is null (closed mode). The demo
 * page's hostile-mutation script logs this to window.__leoHostMutationLog.
 *
 * Iframe: the demo applies sandbox="allow-scripts" (no
 * allow-same-origin), which puts the iframe in a unique opaque
 * origin. iframe.contentDocument throws SecurityError.
 */

import { expect, test } from "@playwright/test";

const HOST = "/demo/host-pages/dual-variant.html";

test.describe("VT-DI-85C95E53-AC3 host JS cannot reach widget DOM", () => {
  test("TC-1 web component: shadowRoot is null from host scope", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page.waitForFunction(
      () =>
        Array.isArray(
          (window as unknown as { __leoHostMutationLog?: unknown[] })
            .__leoHostMutationLog,
        ) &&
        ((window as unknown as { __leoHostMutationLog: unknown[] })
          .__leoHostMutationLog.length ?? 0) >= 2,
      undefined,
      { timeout: 5000 },
    );
    const log = await page.evaluate(
      () =>
        (window as unknown as {
          __leoHostMutationLog: Array<{ kind: string; value: string }>;
        }).__leoHostMutationLog,
    );
    const wcEntry = log.find((e) => e.kind === "wc-shadowRoot");
    expect(wcEntry).toBeDefined();
    expect(wcEntry!.value).toBe("null");
  });

  test("TC-2 iframe: contentDocument access throws SecurityError", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page.waitForFunction(
      () =>
        Array.isArray(
          (window as unknown as { __leoHostMutationLog?: unknown[] })
            .__leoHostMutationLog,
        ) &&
        ((window as unknown as { __leoHostMutationLog: unknown[] })
          .__leoHostMutationLog.length ?? 0) >= 2,
      undefined,
      { timeout: 5000 },
    );
    const log = await page.evaluate(
      () =>
        (window as unknown as {
          __leoHostMutationLog: Array<{ kind: string; value: string }>;
        }).__leoHostMutationLog,
    );
    const iframeEntry = log.find((e) => e.kind === "iframe-contentDocument");
    expect(iframeEntry).toBeDefined();
    // Sandboxed iframe without allow-same-origin: contentDocument is
    // either inaccessible (returns null in some engines) or throws
    // SecurityError. Both outcomes satisfy the AC.
    expect(
      iframeEntry!.value === "null" ||
        iframeEntry!.value.startsWith("throws:"),
    ).toBe(true);
  });

  test("TC-3 web component: querySelector from document does not see disclosure", async ({
    page,
  }) => {
    await page.goto(HOST);
    await page.evaluate(async () => {
      const wc = document.getElementById("wc-widget");
      if (!wc) return;
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
    });
    const reachable = await page.evaluate(
      () =>
        document.querySelector('[data-testid="leo-disclosure-background"]') !==
        null,
    );
    expect(reachable).toBe(false);
  });
});
