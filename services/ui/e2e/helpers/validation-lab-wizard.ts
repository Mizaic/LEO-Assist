/**
 * Open the Validation Lab create-patient wizard from the two-door home.
 *
 * The wizard is not on the home screen. Open Run baseline tests, then
 * Make a new test.
 */

import { expect, type Page } from "@playwright/test";

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function stubValidationLabWizardRoutes(page: Page): Promise<void> {
  await page.route("**/api/validation-lab/cases**", (route) => json(route, []));
  await page.route("**/api/validation-lab/findings**", (route) => json(route, []));
  await page.route("**/api/guidance/rule-picker**", (route) => json(route, []));
}

export async function openCreatePatientWizard(page: Page): Promise<void> {
  await page.goto("/admin/validation-lab");
  await expect(page.getByTestId("validation-lab-page")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("validation-lab-mode-saved").click();
  await page.getByTestId("validation-lab-new-patient").click();
  await expect(page.getByTestId("create-patient-wizard")).toBeVisible({
    timeout: 10_000,
  });
}

export async function fillWizardField(
  page: Page,
  testId: string,
  value: string,
): Promise<void> {
  const field = page.getByTestId(testId);
  const input = field.locator("input, textarea").first();
  await input.fill(value);
}
