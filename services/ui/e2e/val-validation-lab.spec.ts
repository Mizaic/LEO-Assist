import { test, expect, waitForPageSettled } from "./fixtures";
import {
  fillWizardField,
  stubValidationLabWizardRoutes,
} from "./helpers/validation-lab-wizard";

/**
 * Validation Lab chrome journey (Slice 7).
 *
 * Atlas:
 *   UN: UN-4DCE95C8
 *   DI: DI-724CD8A5, DI-2289D095, DI-9138BAC9, DI-A898556B
 *   VT: VT-22F3EF6A
 *
 * Full create->run->promote against a live API is environment-gated.
 * This spec checks the two-door home and the new-patient wizard. It never
 * submits a referral against the live API -- that would start a real pipeline.
 *
 * Atlas run recording lives on VAL-2A1EDC22 (durable SBAR). This file is
 * chrome only so it does not post a fake VAL id.
 */
test.describe("VAL Validation Lab chrome @val", () => {
  test("opens the new-patient wizard from the guideline-rule path", async ({
    page,
  }) => {
    await stubValidationLabWizardRoutes(page);
    await page.goto("/admin/knowledge?tab=validation-lab");
    await waitForPageSettled(page);
    await expect(page.getByTestId("validation-lab-page")).toBeVisible();
    await expect(page.getByTestId("validation-lab-mode-rule")).toBeVisible();
    await page.getByTestId("validation-lab-mode-rule").click();
    await page.getByRole("button", { name: "Advanced: edit the letter" }).first().click();
    await expect(page.getByTestId("create-patient-wizard")).toBeVisible();
    await expect(page.getByTestId("wizard-title")).toBeVisible();

    await fillWizardField(page, "wizard-title", "VAL chrome test patient");
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-profile")).toBeVisible();
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-encounters")).toBeVisible();
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-referral")).toBeVisible();
    await expect(page.getByTestId("wizard-referral-text")).toBeVisible();

    await fillWizardField(
      page,
      "wizard-referral-text",
      "VAL chrome test only -- this run is never submitted.",
    );
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-submit")).toBeVisible();
    await expect(page.getByTestId("wizard-submit")).toBeVisible();
    await expect(page.locator("text=SbarFinalView")).toHaveCount(0);
  });
});
