import { test as base, expect } from "@playwright/test";
import {
  gotoAndSettle,
  installE2eCoreApiStubs,
  waitForPageSettled,
} from "./helpers/page-settle";

const STUB_SKIP_PROJECTS = new Set(["stubbed-chromium"]);

/**
 * Extended Playwright test with local core-api fallbacks and page-settle
 * helpers. Import from here in e2e specs instead of @playwright/test.
 */
export const test = base.extend<{
  patientListPage: void;
}>({
  page: async ({ page }, use, testInfo) => {
    if (!STUB_SKIP_PROJECTS.has(testInfo.project.name)) {
      await installE2eCoreApiStubs(page);
    }
    await use(page);
  },
  patientListPage: async ({ page }, use) => {
    await gotoAndSettle(page, "/care/patients");
    await page.waitForSelector("text=Patients");
    await use();
  },
});

export { expect, gotoAndSettle, waitForPageSettled };
export type { Page, Route, Locator } from "@playwright/test";

// Synthetic NHS test number -- 999-prefix range is reserved by NHS for testing
export const TEST_PATIENT_ID = "9990000001";
export const TEST_ENCOUNTER_ID = "E001";
