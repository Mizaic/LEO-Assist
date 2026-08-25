/**
 * Playwright stubs for VAL-25DA430F (phone-home quality records).
 */

import type { Page } from "@playwright/test";

export const DIGEST_TITLE = "LEO phone-home: hitl_coding [a1b2c3d4e5f6]";
export const ESCALATE_TITLE =
  "LEO phone-home: hitl_escalated [f6e5d4c3b2a1]";

const PRODUCT_ID = "PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4";

function phoneHomeNcrs() {
  return [
    {
      id: "ncr-ph-coding",
      title: DIGEST_TITLE,
      description:
        "Repeated pipeline issue. Family: hitl_coding. Seen: 22 times. " +
        "Gate: digest. Signature: LEO-PH|hitl_coding|a1b2c3d4e5f6. " +
        "No person identifiers.",
      severity: "minor",
      status: "identified",
      created_at: "2026-08-22T12:00:00Z",
      product_id: PRODUCT_ID,
    },
    {
      id: "ncr-ph-escalated",
      title: ESCALATE_TITLE,
      description:
        "Repeated pipeline issue. Family: hitl_escalated. Seen: 1 times. " +
        "Gate: escalate. Signature: LEO-PH|hitl_escalated|f6e5d4c3b2a1. " +
        "No person identifiers.",
      severity: "minor",
      status: "identified",
      created_at: "2026-08-22T12:01:00Z",
      product_id: PRODUCT_ID,
    },
    {
      id: "ncr-ph-coding-closed",
      title: DIGEST_TITLE,
      description: "Closed duplicate of the same coding family.",
      severity: "minor",
      status: "closed",
      created_at: "2026-08-01T12:00:00Z",
      product_id: PRODUCT_ID,
    },
  ];
}

export async function stubPhoneHomeValRoutes(page: Page): Promise<void> {
  await page.route("**/api/validation-lab/cases**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/validation-lab/findings**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/validation-lab/ncrs**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: phoneHomeNcrs() }),
    }),
  );
}
