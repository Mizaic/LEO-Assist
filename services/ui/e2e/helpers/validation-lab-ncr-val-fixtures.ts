/**
 * Playwright stubs for VAL-CF997D18 (Validation Lab product records).
 */

import type { Page } from "@playwright/test";

export const OPEN_NCR_TITLE = "Missed code on letter check";
export const NEW_NCR_TITLE = "Missed finding in letter";
export const NHS_NUMBER = "9990000001";
export const UBRN = "000012345678";
export const PATIENT_NAME = "VAL Lab Case";

const PRODUCT_ID = "PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4";

export const createdBodies: Record<string, unknown>[] = [];
export const eventBodies: Record<string, unknown>[] = [];

const openNcr = {
  id: "ncr-open-1",
  title: OPEN_NCR_TITLE,
  description: "LEO missed a finding on a letter check.",
  severity: "minor",
  status: "identified",
  created_at: "2026-08-22T12:00:00Z",
  product_id: PRODUCT_ID,
};

const createdNcr = {
  id: "ncr-created-1",
  title: NEW_NCR_TITLE,
  description: "LEO missed a finding. Check the letter again.",
  severity: "minor",
  status: "identified",
  created_at: "2026-08-22T12:05:00Z",
  product_id: PRODUCT_ID,
};

const patientRun = {
  run_id: "run-val-1",
  status: "done",
  created_at: "2026-08-22T11:00:00Z",
  plan_id: "plan-1",
  patient_id: "p-val-1",
  patient_name: PATIENT_NAME,
  nhs_number: NHS_NUMBER,
  ubrn: UBRN,
};

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function stubValidationLabNcrValRoutes(page: Page): Promise<void> {
  createdBodies.length = 0;
  eventBodies.length = 0;

  await page.route("**/api/validation-lab/cases**", (route) => json(route, []));
  await page.route("**/api/validation-lab/findings**", (route) => json(route, []));
  await page.route("**/api/validation-lab/clinical-patients**", (route) =>
    json(route, [patientRun]),
  );
  await page.route("**/api/validation-lab/pipeline-runs**", (route) =>
    json(route, [patientRun]),
  );

  await page.route("**/api/validation-lab/ncrs**", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      createdBodies.push(body);
      return json(route, createdNcr);
    }
    return json(route, { items: [openNcr] });
  });
  await page.route("**/api/validation-lab/ncrs/**/investigation", (route) =>
    json(route, { nc_id: createdNcr.id, title: createdNcr.title, cases: [] }),
  );
  await page.route("**/api/validation-lab/ncrs/**/investigation/cases", (route) =>
    json(route, { nc_id: createdNcr.id, cases: [patientRun] }),
  );
  await page.route("**/api/validation-lab/ncrs/**/investigation/events", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      eventBodies.push(body);
      return json(route, { atlas_ok: true, atlas_text: String(body.text || "") });
    }
    return route.continue();
  });
}
