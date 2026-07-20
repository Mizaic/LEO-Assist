/**
 * Surface Forms -> Create local concept wizard (stubbed chromium).
 * Happy: open wizard with package selected.
 * Non-happy: blocked without package selection (+ screenshots).
 */
import { expect, test } from "@playwright/test";
import { fulfillJson, stubKnowledgeAdminAuth } from "./helpers/surface-forms-fixtures";

test.describe("Surface Forms local concept wizard entry", () => {
  test("happy: Create local concept opens wizard with package step", async ({
    page,
  }, testInfo) => {
    await stubKnowledgeAdminAuth(page);

    await page.route("**/api/terminology/local-packages**", (route) => {
      if (route.request().method() === "GET") {
        return fulfillJson(route, {
          items: [
            {
              id: "pkg-leo-global-defaults",
              name: "LEO global local terminology",
              scope: "global",
              org_id: null,
              status: "active",
              version: 1,
              concept_count: 3,
            },
          ],
          total: 1,
        });
      }
      return fulfillJson(route, {
        id: "pkg-new",
        name: "New",
        scope: "global",
        status: "draft",
      });
    });

    await page.route("**/api/terminology/surface-forms/**", (route) =>
      fulfillJson(route, { items: [], total: 0 }),
    );
    await page.route("**/api/terminology/surface-forms?*", (route) =>
      fulfillJson(route, { items: [], total: 0 }),
    );
    await page.route("**/api/terminology/surface-forms/grouped**", (route) =>
      fulfillJson(route, { items: [], total: 0 }),
    );

    await page.goto("/settings/surface-forms");
    await expect(
      page.getByRole("button", { name: /Create local concept/i }),
    ).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: testInfo.outputPath("01-surface-forms-toolbar.png"),
      fullPage: true,
    });

    await page.getByRole("button", { name: /Create local concept/i }).click();
    await expect(page.getByTestId("local-concepts-wizard")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("wizard-step-package")).toBeVisible();
    await expect(page.getByTestId("local-concept-package")).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("02-wizard-package-step.png"),
      fullPage: true,
    });
  });

  test("non-happy: Next blocked without package selection", async ({
    page,
  }, testInfo) => {
    await stubKnowledgeAdminAuth(page);

    await page.route("**/api/terminology/local-packages**", (route) =>
      fulfillJson(route, { items: [], total: 0 }),
    );

    await page.goto("/admin/guidance/local-concepts");
    await expect(page.getByTestId("wizard-step-package")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("local-concept-package-required")).toBeVisible();
    await expect(page.getByTestId("local-concept-next")).toBeDisabled();
    await page.screenshot({
      path: testInfo.outputPath("03-missing-package-blocked.png"),
      fullPage: true,
    });
  });
});
