/**
 * Playwright stubs for VAL-DAC2B005 (default and organisation lab ranges).
 */

import type { Page } from "@playwright/test";

export const CONCEPT_ID = "271649006";
export const DISPLAY_NAME = "Haemoglobin";
export const ORG_OVERLAY_NAME = "Oak GP";
export const ORG_FALLBACK_NAME = "Pine ICB";
export const PLATFORM_OWNER = "Platform default";

const OAK_ID = "org-oak";
const PINE_ID = "org-pine";

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function summary() {
  return {
    concept_id: CONCEPT_ID,
    display_name: DISPLAY_NAME,
    canonical_unit: "g/L",
    source: "manual",
    range_count: 2,
    conversion_count: 0,
    interpretation_count: 0,
  };
}

function detail() {
  return {
    ...summary(),
    conversions: [],
    interpretations: [],
    ranges: [
      {
        range_id: "range-default",
        org_id: "",
        sex: "all",
        age_min: null,
        age_max: null,
        low: 115,
        high: 165,
        critical_low: 70,
        critical_high: 200,
        source: "manual",
      },
      {
        range_id: "range-oak",
        org_id: OAK_ID,
        sex: "all",
        age_min: null,
        age_max: null,
        low: 120,
        high: 170,
        critical_low: 70,
        critical_high: 200,
        source: "local",
      },
    ],
  };
}

function orgs() {
  return [
    {
      id: OAK_ID,
      name: ORG_OVERLAY_NAME,
      type: "gp",
      odsCode: "A12345",
      labels: [],
      patient_count: 0,
    },
    {
      id: PINE_ID,
      name: ORG_FALLBACK_NAME,
      type: "icb",
      odsCode: "B99999",
      labels: [],
      patient_count: 0,
    },
  ];
}

export async function stubLabRangeValRoutes(page: Page): Promise<void> {
  await page.route("**/api/admin/orgs**", (route) => json(route, orgs()));
  await page.route("**/api/lab-result-configs**", (route) => {
    const url = route.request().url();
    if (url.includes("/lab-result-configs/" + CONCEPT_ID)) {
      return json(route, { item: detail() });
    }
    return json(route, { items: [summary()] });
  });
}
