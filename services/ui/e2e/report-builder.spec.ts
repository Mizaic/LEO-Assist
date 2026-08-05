import { test, expect } from "./fixtures";

test.describe("Report Builder", () => {
  test("report builder page loads", async ({ page }) => {
    await page.goto("/reports/builder");
    await expect(page.getByText("Report Builder")).toBeVisible();
  });

  test("builder has Add Element and Save buttons", async ({ page }) => {
    await page.goto("/reports/builder");
    await expect(page.getByRole("button", { name: /Add Element/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /Save/ })).toBeVisible();
  });

  test("clicking Add Element shows element palette", async ({ page }) => {
    await page.goto("/reports/builder");
    await page.getByRole("button", { name: /Add Element/ }).click();
    await expect(page.getByText("Add an element")).toBeVisible();
    await expect(page.getByText("Heading", { exact: true })).toBeVisible();
    await expect(page.getByText("KPI Card")).toBeVisible();
    await expect(page.getByText("Chart", { exact: true })).toBeVisible();
  });

  test("adding an element updates the canvas", async ({ page }) => {
    await page.goto("/reports/builder");
    await page.getByRole("button", { name: /Add Element/ }).click();
    await page.getByText("KPI Card").click();
    await expect(page.getByText("KPI")).toBeVisible();
  });
});
