/**
 * Playwright stubs for VAL-4EAC0FF0 (AI and cloud costs per patient case).
 */

import type { Page } from "@playwright/test";

export const PATIENT_ID = "p-val-cost";
export const PATIENT_COST = "$0.1234";
export const ORG_ID = "org-val-cost";
export const ORG_NAME = "Oak Trust";
export const RAW_COST = "$10.0000";
export const LIST_AT_75 = "$40.0000";
export const LIST_AT_80 = "$50.0000";
export const DISCOUNT_COPY = "Year 1 launch promo";
export const PLATFORM_TYPE = "gold_training";

export const putMarginBodies: Record<string, unknown>[] = [];
export const postDiscountBodies: Record<string, unknown>[] = [];

const RAW = 10;
let targetMargin = 0.75;
let discountRate = 0;
const discounts: Record<string, unknown>[] = [];

function json(
  route: { fulfill: (r: object) => Promise<void> },
  body: unknown,
  status = 200,
) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function applyPricing() {
  const listPriceUsd = RAW / (1 - targetMargin);
  const capped = Math.min(discountRate, 1);
  const billableUsd = listPriceUsd * (1 - capped);
  const grossMargin =
    billableUsd > 0 ? (billableUsd - RAW) / billableUsd : 0;
  return { listPriceUsd, billableUsd, grossMargin };
}

function orgSpend() {
  const pricing = applyPricing();
  return {
    orgId: ORG_ID,
    orgName: ORG_NAME,
    runCount: 1,
    inputTokens: 1000,
    outputTokens: 200,
    cachedTokens: 100,
    rawCostUsd: RAW,
    discountRate,
    targetMargin,
    activeDiscounts: discounts,
    ...pricing,
  };
}

function sessionPayload() {
  return {
    user: { email: "e2e.admin@example.com", name: "E2E Admin" },
    isPlatformAdmin: true,
    organizations: [
      {
        id: ORG_ID,
        name: ORG_NAME,
        odsCode: "OAK",
        shortName: "Oak",
        scopeType: "gp",
      },
    ],
    idleTimeoutMinutes: 30,
    selected_role: "platform_admin",
    allowed_roles: ["platform_admin"],
    needs_role_choice: false,
    density_preference: "comfortable",
  };
}

function spendRuns() {
  return {
    runs: [
      {
        runId: "run-val-cost",
        patientId: PATIENT_ID,
        encounterId: "",
        status: "completed",
        durationMs: 1200,
        inputTokens: 1000,
        outputTokens: 200,
        cachedTokens: 100,
        costUsd: 0.1234,
        createdAt: "2026-08-22T12:00:00Z",
      },
    ],
    totals: {
      runCount: 1,
      inputTokens: 1000,
      outputTokens: 200,
      cachedTokens: 100,
      costUsd: 0.1234,
      cacheHitRate: 0.1,
    },
  };
}

type PriceRoute = {
  request: () => { url: () => string; method: () => string; postDataJSON: () => unknown };
  fulfill: (r: object) => Promise<void>;
  continue: () => Promise<void>;
};

function fulfillConfig(route: PriceRoute, method: string) {
  if (method === "PUT") {
    const body = route.request().postDataJSON() as { targetMargin?: number };
    putMarginBodies.push(body);
    if (typeof body.targetMargin === "number") {
      targetMargin = body.targetMargin;
    }
    return json(route, { targetMargin, status: "updated" });
  }
  return json(route, {
    targetMargin,
    updatedBy: "e2e.admin@example.com",
    updatedAt: "2026-08-22T12:00:00Z",
    isDefault: false,
  });
}

function fulfillDiscounts(route: PriceRoute, method: string) {
  if (method === "POST") {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    postDiscountBodies.push(body);
    if (typeof body.rate === "number") {
      discountRate = body.rate;
    }
    discounts.push({
      discountId: "disc-val-1",
      orgId: ORG_ID,
      description: body.description,
      rate: body.rate,
      type: body.type,
      validFrom: body.validFrom,
      validTo: body.validTo,
      isActive: true,
      createdBy: "e2e.admin@example.com",
      createdAt: "2026-08-22T12:00:00Z",
    });
    return json(route, { status: "created" }, 201);
  }
  return json(route, { discounts });
}

function fulfillOrgs(route: PriceRoute) {
  const pricing = applyPricing();
  return json(route, {
    orgs: [orgSpend()],
    targetMargin,
    totals: { rawCostUsd: RAW, billableUsd: pricing.billableUsd, orgCount: 1 },
  });
}

function fulfillPlatform(route: PriceRoute) {
  return json(route, {
    breakdown: [
      {
        eventType: PLATFORM_TYPE,
        runCount: 2,
        inputTokens: 500,
        outputTokens: 80,
        cachedTokens: 0,
        rawCostUsd: 1.5,
      },
    ],
    targetMargin,
    totals: {
      rawCostUsd: 1.5,
      listPriceUsd: 1.5 / (1 - targetMargin),
      note: "internal",
    },
  });
}

function fulfillPricing(route: PriceRoute) {
  const url = route.request().url();
  const method = route.request().method();
  if (url.includes("/pricing/config")) return fulfillConfig(route, method);
  if (url.includes("/discounts")) return fulfillDiscounts(route, method);
  if (url.includes("/pricing/orgs")) return fulfillOrgs(route);
  if (url.includes("/pricing/platform-spend")) return fulfillPlatform(route);
  return route.continue();
}

export async function stubCostTrackingValRoutes(page: Page): Promise<void> {
  putMarginBodies.length = 0;
  postDiscountBodies.length = 0;
  targetMargin = 0.75;
  discountRate = 0;
  discounts.length = 0;

  await page.route("**/auth/session", (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    return json(route, sessionPayload());
  });
  await page.route("**/api/analytics/llm-spend/**", (route) =>
    json(route, spendRuns()),
  );
  await page.route("**/api/pricing/**", (route) => fulfillPricing(route));
}
