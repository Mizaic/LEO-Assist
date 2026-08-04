import { expect, test } from "./fixtures";

test.describe("Encounter batch recode", () => {
  test("encounters page renders search and batch controls", async ({ page }) => {
    await page.goto("/care/encounters");
    await expect(page.getByRole("heading", { name: "Encounters" })).toBeVisible();
    await expect(
      page.getByLabel("Search encounters (hybrid)")
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Search" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Reset \+ recode selected/ })
    ).toBeVisible();
  });
});
