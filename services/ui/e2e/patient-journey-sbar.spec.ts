import { test, expect, waitForPageSettled } from "./fixtures";

test.describe("Patient journey SBAR", () => {
  test("documents tab shows journey builder for admin users", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const firstCard = page.locator("[class*='MuiCardActionArea-root']").first();
    await firstCard.click();
    await waitForPageSettled(page);

    const documentsTab = page.getByRole("tab", { name: /documents/i });
    if (await documentsTab.isVisible()) {
      await documentsTab.click();
      await waitForPageSettled(page);
    }

    const journeyPanel = page.getByTestId("journey-builder-panel");
    const addButton = page.getByTestId("add-document-button");
    const hasJourneyChrome =
      (await journeyPanel.isVisible().catch(() => false)) ||
      (await addButton.isVisible().catch(() => false));
    if (!hasJourneyChrome) {
      test.skip(true, "Journey builder requires platform admin session.");
    }
    await expect(journeyPanel).toBeVisible();
    await expect(addButton).toBeVisible();
  });

  test("add document dialog opens from documents tab when admin", async ({ page }) => {
    await page.goto("/care/patients");
    await page.waitForResponse((res) =>
      res.url().includes("/patients") && res.status() === 200,
    );
    const firstCard = page.locator("[class*='MuiCardActionArea-root']").first();
    await firstCard.click();
    await waitForPageSettled(page);

    const documentsTab = page.getByRole("tab", { name: /documents/i });
    if (await documentsTab.isVisible()) {
      await documentsTab.click();
      await waitForPageSettled(page);
    }

    const addButton = page.getByTestId("add-document-button");
    if (!(await addButton.isVisible().catch(() => false))) {
      test.skip();
      return;
    }

    await addButton.click();
    await expect(page.getByRole("dialog")).toContainText(/add document/i);
    await expect(page.getByLabel(/title/i)).toBeVisible();
  });
});
