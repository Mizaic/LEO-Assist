import { test, expect, waitForPageSettled } from "./fixtures";

test.describe("Patient Workflow", () => {
  test("patient list page loads and shows heading", async ({ page }) => {
    await page.goto("/care/patients");
    await expect(page.getByRole("heading", { name: "Patients" })).toBeVisible();
  });

  test("patient list shows patient cards after API response", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const cards = page.locator("[class*='MuiCard-root']");
    await expect(cards.first()).toBeVisible();
  });

  test("search filters patients by ID", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const searchInput = page.getByPlaceholder("Search by patient ID");
    await searchInput.fill("420230");
    const countText = page.getByText(/Showing \d+ of \d+ patients/);
    await expect(countText).toBeVisible();
  });

  test("clicking a patient navigates to encounters list", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const firstCard = page.locator("[class*='MuiCardActionArea-root']").first();
    await firstCard.click();
    await expect(page).toHaveURL(/\/care\/patients\/[^/]+$/);
  });

  test("encounter list shows encounter rows", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const firstCard = page.locator("[class*='MuiCardActionArea-root']").first();
    await firstCard.click();
    await waitForPageSettled(page);
    await expect(page.locator("body")).toContainText(/encounter/i);
  });
});
