import type { Page, Route } from "@playwright/test";

const EMPTY_LIST = { items: [], total: 0, offset: 0, limit: 50 };

const AUDIT_SUMMARY_STUB = {
  total_episodes: 0,
  active_episodes: 0,
  confirmed_cancers: 0,
};

const LLM_SPEND_STUB = {
  runs: [],
  totals: {
    inputTokens: 0,
    outputTokens: 0,
    cachedTokens: 0,
    costUsd: 0,
    cacheHitRate: 0,
  },
};

async function fulfillJson(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function isLocalPlaywrightBaseUrl(): boolean {
  const base = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
  try {
    const host = new URL(base).hostname;
    return host === "localhost" || host === "127.0.0.1";
  } catch {
    return false;
  }
}

/**
 * Minimal core-api fallbacks for local Playwright runs where only the UI
 * dev server is started (CI ui-a11y job). Register specific routes in a test
 * after this helper; Playwright matches the most recently added route first.
 */
export async function installE2eCoreApiStubs(page: Page): Promise<void> {
  if (!isLocalPlaywrightBaseUrl()) {
    return;
  }

  // Lowest priority first -- specific handlers are registered after these.
  await page.route("**/api/proxy/**", (route) => fulfillJson(route, {}));
  await page.route("**/api/analytics/**", (route) => fulfillJson(route, {}));

  await page.route("**/api/analytics/llm-spend/**", (route) =>
    fulfillJson(route, LLM_SPEND_STUB),
  );
  await page.route("**/api/proxy/analytics/safety-netting/alerts**", (route) =>
    fulfillJson(route, []),
  );
  await page.route("**/api/proxy/analytics/safety-netting/worklist**", (route) =>
    fulfillJson(route, []),
  );
  await page.route("**/api/proxy/analytics/episodes/summary**", (route) =>
    fulfillJson(route, []),
  );
  await page.route("**/api/proxy/analytics/episodes/diagnosed**", (route) =>
    fulfillJson(route, []),
  );
  await page.route("**/api/proxy/analytics/benchmarks/kpis**", (route) =>
    fulfillJson(route, []),
  );
  await page.route("**/api/proxy/analytics/audit/summary**", (route) =>
    fulfillJson(route, AUDIT_SUMMARY_STUB),
  );

  await page.route("**/api/terminology/**", (route) => {
    const url = route.request().url();
    if (url.includes("grouped")) {
      return fulfillJson(route, EMPTY_LIST);
    }
    if (url.includes("audit-log")) {
      return fulfillJson(route, { items: [], total: 0, offset: 0, limit: 100 });
    }
    return fulfillJson(route, {});
  });

  await page.route("**/api/patients**", (route) => fulfillJson(route, EMPTY_LIST));
  await page.route("**/api/operations/**", (route) => fulfillJson(route, EMPTY_LIST));
  await page.route("**/api/pipeline/**", (route) => fulfillJson(route, {}));
  await page.route("**/api/review/**", (route) => fulfillJson(route, EMPTY_LIST));
  await page.route("**/api/nice/**", (route) => fulfillJson(route, []));
  await page.route("**/api/guidance/**", (route) => fulfillJson(route, EMPTY_LIST));
}

/**
 * Wait for the document and AppShell main region without networkidle, which
 * never settles when core-api proxy calls fail in CI.
 */
export async function waitForPageSettled(
  page: Page,
  opts?: { timeout?: number },
): Promise<void> {
  const timeout = opts?.timeout ?? 15_000;
  await page.waitForLoadState("load");
  const main = page.locator("#main-content");
  try {
    await main.waitFor({ state: "visible", timeout: 3_000 });
  } catch {
    await page.locator("body").waitFor({ state: "attached", timeout });
  }
}

export async function gotoAndSettle(
  page: Page,
  url: string,
  opts?: { timeout?: number },
): Promise<void> {
  await page.goto(url);
  await waitForPageSettled(page, opts);
}
