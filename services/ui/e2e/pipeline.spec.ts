import { test, expect } from "@playwright/test";

test.describe("Processing", () => {
  test("pipeline tab renders no-code controls", async ({ page }) => {
    await page.goto("/operations");
    await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Single patient" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Bulk / cohort" })).toBeVisible();
    await expect(page.getByLabel(/Search patient/)).toBeVisible();
  });

  test("single-patient actions stay disabled until summary loads", async ({ page }) => {
    await page.goto("/operations");
    const runBtn = page.getByRole("button", { name: /Code new encounters/i });
    await expect(runBtn).toBeDisabled();
  });

  test("typed NHS number can be applied to single-patient selection", async ({ page }) => {
    await page.goto("/operations");
    await page.getByLabel(/Search patient/).fill("9990000001");
    await expect(page.getByRole("button", { name: /Use typed ID/ })).toBeVisible();
  });

  test("spaced NHS number format is accepted", async ({ page }) => {
    await page.goto("/operations");
    await page.getByLabel(/Search patient/).fill("999 000 0001");
    await expect(page.getByRole("button", { name: /Use typed ID/ })).toBeVisible();
  });

  test("cohort mode renders bulk table and actions", async ({ page }) => {
    await page.goto("/operations");
    await page.getByRole("button", { name: "Bulk / cohort" }).click();
    await expect(page.getByText("Bulk actions")).toBeVisible();
    await expect(page.getByRole("button", { name: /Select filtered/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Code new encounters/i })).toBeDisabled();
  });
});
