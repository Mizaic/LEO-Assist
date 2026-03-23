import { test as base, expect } from "@playwright/test";

/**
 * Extended test fixtures for e2e tests.
 * API mocking helpers and common navigation utilities.
 */
export const test = base.extend<{
  /** Navigate to patient list and wait for it to load */
  patientListPage: void;
}>({
  patientListPage: async ({ page }, use) => {
    await page.goto("/care/patients");
    await page.waitForSelector("text=Patients");
    await use();
  },
});

export { expect };

// Synthetic NHS test number — 999-prefix range is reserved by NHS for testing
export const TEST_PATIENT_ID = "9990000001";
export const TEST_ENCOUNTER_ID = "E001";
