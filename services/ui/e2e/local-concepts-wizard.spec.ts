/**
 * Local concepts wizard -- happy path with screenshots.
 * Stubs terminology APIs so the journey is deterministic.
 */
import { expect, test } from "./fixtures";
import { fulfillJson, stubKnowledgeAdminAuth } from "./helpers/surface-forms-fixtures";

test.describe("Local concepts wizard", () => {
  test("happy path: package, define, alias, dry-run match, approve", async ({
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
              concept_count: 1,
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

    await page.route("**/api/terminology/local-concepts/dry-run-recovery", (route) =>
      fulfillJson(route, {
        matched_count: 1,
        pattern_count: 1,
        entities: [
          {
            text: "acne fulminans",
            snomed_concept_id: "LEO-LOCAL-ACNE-FULMINANS",
          },
        ],
      }),
    );

    await page.route(
      "**/api/terminology/surface-forms/create-local-with-alias",
      (route) =>
        fulfillJson(route, {
          concept: {
            id: "LEO-LOCAL-ACNE-FULMINANS",
            fsn: "Acne fulminans (LEO local)",
            code_system: "leo_local",
            concept_kind: "finding",
            active: true,
          },
          mapping: {
            normalized: "acne fulminans",
            form: "acne fulminans",
            concept_id: "LEO-LOCAL-ACNE-FULMINANS",
            status: "approved",
          },
          package_id: "pkg-leo-global-defaults",
        }),
    );

    await page.goto("/admin/guidance/local-concepts");
    await expect(page.getByTestId("local-concepts-wizard")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("wizard-step-package")).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("01-package.png"),
      fullPage: true,
    });

    await page.getByTestId("local-concept-next").click();
    await expect(page.getByTestId("wizard-step-define")).toBeVisible();
    await page.getByTestId("local-concept-display-name").fill("Acne fulminans");
    await page.screenshot({
      path: testInfo.outputPath("02-define.png"),
      fullPage: true,
    });

    await page.getByTestId("local-concept-next").click();
    await expect(page.getByTestId("wizard-step-aliases")).toBeVisible();
    await page.getByTestId("local-concept-alias").fill("acne fulminans");
    await page.screenshot({
      path: testInfo.outputPath("03-aliases.png"),
      fullPage: true,
    });

    await page.getByTestId("local-concept-next").click();
    await page
      .getByTestId("local-concept-sample-text")
      .fill("Urgently refer acne fulminans to dermatology today.");
    await page.getByTestId("local-concept-dry-run").click();
    await expect(page.getByTestId("local-concept-dry-run-result")).toContainText(
      "Matched 1",
    );
    await page.screenshot({
      path: testInfo.outputPath("04-dry-run.png"),
      fullPage: true,
    });

    await page.getByTestId("local-concept-next").click();
    await page.getByTestId("local-concept-approve").click();
    await expect(page.getByTestId("local-concept-approved")).toContainText(
      "LEO-LOCAL-ACNE-FULMINANS",
    );
    await page.screenshot({
      path: testInfo.outputPath("05-approved.png"),
      fullPage: true,
    });
  });

  test("non-happy: dry-run with no match shows warning", async ({ page }, testInfo) => {
    await stubKnowledgeAdminAuth(page);
    await page.route("**/api/terminology/local-packages**", (route) =>
      fulfillJson(route, {
        items: [
          {
            id: "pkg-leo-global-defaults",
            name: "LEO global",
            scope: "global",
            status: "active",
          },
        ],
        total: 1,
      }),
    );
    await page.route("**/api/terminology/local-concepts/dry-run-recovery", (route) =>
      fulfillJson(route, {
        matched_count: 0,
        pattern_count: 1,
        entities: [],
      }),
    );

    await page.goto("/admin/guidance/local-concepts");
    await page.getByTestId("local-concept-next").click();
    await page.getByTestId("local-concept-display-name").fill("Acne fulminans");
    await page.getByTestId("local-concept-next").click();
    await page.getByTestId("local-concept-alias").fill("acne fulminans");
    await page.getByTestId("local-concept-next").click();
    await page
      .getByTestId("local-concept-sample-text")
      .fill("No matching phrase here.");
    await page.getByTestId("local-concept-dry-run").click();
    await expect(page.getByTestId("local-concept-dry-run-result")).toContainText(
      "No match",
    );
    await page.screenshot({
      path: testInfo.outputPath("non-happy-dry-run.png"),
      fullPage: true,
    });
  });
});
