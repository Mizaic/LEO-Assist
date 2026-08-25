/**
 * VAL -- Validation Lab A&G wizard chrome (no live pipeline submit in CI).
 *
 * Atlas: DI-D01C6EC8 / DI-D6E5F94E
 */

import { test, expect } from "./fixtures";
import {
  fillWizardField,
  openCreatePatientWizard,
  stubValidationLabWizardRoutes,
} from "./helpers/validation-lab-wizard";

test.describe("Validation Lab A&G wizard chrome", () => {
  test.beforeEach(async ({ page }) => {
    await stubValidationLabWizardRoutes(page);
    await openCreatePatientWizard(page);
  });

  test("shows scenario selector and A&G thread builder", async ({ page }) => {
    await page.getByTestId("wizard-scenario").click();
    await page.getByRole("option", { name: "Generic A&G" }).click();
    await fillWizardField(page, "wizard-title", "A&G chrome case");
    await page.getByTestId("wizard-next").click();
    await page.getByTestId("wizard-next").click();
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-ag-thread")).toBeVisible();
    await page.getByTestId("wizard-ag-add-requester").click();
    await expect(page.getByTestId(/wizard-ag-turn-note-/)).toBeVisible();
    await expect(page.getByTestId("wizard-ag-formal-response")).toBeVisible();
  });

  test("SPoA A&G scenario shows GP consult and reason fields", async ({ page }) => {
    await page.getByTestId("wizard-scenario").click();
    await page.getByRole("option", { name: "SPoA: A&G request" }).click();
    await fillWizardField(page, "wizard-title", "SPoA A&G chrome case");
    await expect(page.getByTestId("wizard-spoa-demographics")).toBeVisible();
    await page.getByTestId("wizard-next").click();
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-gp-consult")).toBeVisible();
    await fillWizardField(page, "wizard-gp-consult-text", "GP consult note for chrome");
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-reason-for-submission")).toBeVisible();
    await expect(page.getByTestId("wizard-preview-pmh")).toBeVisible();
  });
});
