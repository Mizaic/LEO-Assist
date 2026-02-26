import { test, expect } from "@playwright/test";

test.describe("Processing", () => {
  test("processing page renders run controls", async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.getByRole("heading", { name: "Process Records" })).toBeVisible();
    await expect(page.getByLabel(/Patient IDs/)).toBeVisible();
  });

  test("Run button is disabled without patient IDs", async ({ page }) => {
    await page.goto("/pipeline");
    const runBtn = page.getByRole("button", { name: /Process Records/ });
    await expect(runBtn).toBeDisabled();
  });

  test("entering patient IDs enables Run button", async ({ page }) => {
    await page.goto("/pipeline");
    await page.getByLabel(/Patient IDs/).fill("4202301609");
    const runBtn = page.getByRole("button", { name: /Process Records/ });
    await expect(runBtn).toBeEnabled();
  });

  test("export section is visible", async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.getByRole("heading", { name: "Export Training Data" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Export training data/ })).toBeVisible();
  });
});
