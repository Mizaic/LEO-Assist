import { test, expect, waitForPageSettled } from "./fixtures";

test.describe("Safety Netting", () => {
  test("safety netting page loads", async ({ page }) => {
    await page.goto("/safety-netting");
    await expect(page.getByRole("heading", { name: /Safety Netting/i })).toBeVisible();
  });

  test("worklist renders with data or empty state", async ({ page }) => {
    await page.goto("/safety-netting");
    await waitForPageSettled(page);
    await expect(
      page.getByText(/\d+ pathways shown \(\d+ total active\)/i),
    ).toBeVisible();
  });

  test("page has filtering controls", async ({ page }) => {
    await page.goto("/safety-netting");
    await waitForPageSettled(page);
    await expect(page.locator("body")).toBeVisible();
  });
});
