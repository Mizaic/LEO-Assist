/**
 * VAL -- Validation Lab RAS / SPoA referral wizard chrome
 * (no live pipeline submit in CI).
 *
 * Atlas: DI-D6E5F94E / DO-E981C7B1 / VT-BE867D10
 */

import { test, expect } from "@playwright/test";

test.describe("Validation Lab SPoA RAS referral wizard chrome", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/admin/validation-lab");
  });

  test("RAS referral scenario shows GP consult, reason, and PMH preview", async ({
    page,
  }) => {
    await expect(page.getByTestId("create-patient-wizard")).toBeVisible();
    await page.getByTestId("wizard-scenario").click();
    await page.getByRole("option", { name: "RAS: Referral" }).click();
    await page.getByTestId("wizard-title").fill("RAS referral chrome case");
    await expect(page.getByTestId("wizard-nhs-number")).toBeVisible();
    await expect(page.getByTestId("wizard-gp-practice")).toBeVisible();
    await page.getByTestId("wizard-next").click();
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-gp-consult")).toBeVisible();
    await page.getByTestId("wizard-gp-consult-text").fill("GP consult for RAS chrome");
    await page.getByTestId("wizard-next").click();
    await expect(page.getByTestId("wizard-step-referral")).toBeVisible();
    await expect(page.getByTestId("wizard-reason-for-submission")).toBeVisible();
    await expect(page.getByTestId("wizard-preview-pmh")).toBeVisible();
    await expect(page.getByTestId("wizard-referral-text")).toBeVisible();
  });
});
