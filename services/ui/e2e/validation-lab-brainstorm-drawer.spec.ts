/**
 * Validation Lab brainstorm drawer -- stubbed happy + non-happy journeys.
 *
 * Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
 */
import { expect, test } from "./fixtures";
import { fulfillJson, stubKnowledgeAdminAuth } from "./helpers/surface-forms-fixtures";

async function stubLabChrome(page: import("./fixtures").Page) {
  await stubKnowledgeAdminAuth(page);
  await page.route("**/api/nice/loaded", (route) =>
    fulfillJson(route, [
      {
        code: "NG12",
        title: "Suspected cancer: recognition and referral",
        guideline_source: "nice_syndication_api",
        recommendation_count: 12,
      },
    ]),
  );
  let createSeq = 0;
  await page.route("**/api/validation-lab/cases", (route) => {
    if (route.request().method() === "GET") {
      return fulfillJson(route, []);
    }
    createSeq += 1;
    return fulfillJson(
      route,
      { id: `case-created-${createSeq}`, title: "created" },
      201,
    );
  });
  await page.route("**/api/validation-lab/brainstorm", async (route) => {
    const body = route.request().postDataJSON() as {
      phase?: string;
      scenario_text?: string;
    };
    if (body.phase === "understand") {
      return fulfillJson(route, {
        needs_clarification: true,
        questions: [
          {
            id: "q1",
            question: "Which trigger path?",
            allowMultiple: true,
            maxSelections: 2,
            options: [
              { id: "age", label: "Age and sex only", recommended: true },
              { id: "pmh", label: "Prior fragility fracture", recommended: false },
            ],
          },
        ],
        guidance_message: "",
        variants: [],
      });
    }
    if (body.phase === "clarify") {
      return fulfillJson(route, {
        needs_clarification: false,
        questions: [],
        variants: [],
      });
    }
    return fulfillJson(route, {
      needs_clarification: false,
      questions: [],
      variants: [
        {
          variantId: "v1",
          label: "Age 68 female",
          rationale: "fires age branch",
          recommended: true,
          isControl: false,
          expectedTrigger: true,
          expectedTriggerReason: "verified",
          title: "Haematuria age branch",
          patientName: "Pat Example",
          patientAge: "68",
          patientSex: "female",
          referralText: "Dear colleague, unexplained haematuria.",
          pmh: [],
          observations: [],
        },
        {
          variantId: "v-control",
          label: "Control under 45",
          rationale: "should not fire",
          recommended: false,
          isControl: true,
          expectedTrigger: false,
          expectedTriggerReason: "verified",
          title: "Control under 45",
          patientAge: "30",
          patientSex: "female",
          referralText: "Dear colleague, young adult.",
          pmh: [],
        },
      ],
    });
  });
}

test.describe("Validation Lab brainstorm drawer", () => {
  test("happy path: clarify multi-select, create selected variants", async ({
    page,
  }, testInfo) => {
    await stubLabChrome(page);
    await page.goto("/admin/validation-lab");
    await expect(page.getByTestId("create-patient-wizard")).toBeVisible({
      timeout: 15_000,
    });
    await page.getByTestId("open-brainstorm-drawer").click();
    const drawer = page.getByTestId("scenario-brainstorm-drawer");
    await expect(drawer).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("01-attach.png"),
      fullPage: true,
    });

    await drawer.getByLabel("Scenario text").fill(
      "68 year old woman with unexplained haematuria for 2WW referral test",
    );
    await drawer.getByRole("button", { name: "Continue" }).click();
    await expect(
      drawer.getByRole("heading", { name: "Clarify" }),
    ).toBeVisible();
    await drawer.getByLabel(/Age and sex only/).check();
    await drawer.getByLabel(/Prior fragility fracture/).check();
    await page.screenshot({
      path: testInfo.outputPath("02-clarify.png"),
      fullPage: true,
    });
    await drawer.getByRole("button", { name: "Next" }).click();
    await expect(
      drawer.getByRole("heading", { name: "Variants" }),
    ).toBeVisible();
    await expect(drawer.getByText("trigger verified")).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("03-variants.png"),
      fullPage: true,
    });
    await drawer.getByRole("button", { name: /Create 2/ }).click();
    await expect(drawer.getByText(/created case-created-1/)).toBeVisible();
    await expect(drawer.getByText(/created case-created-2/)).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("04-review.png"),
      fullPage: true,
    });
  });

  test("non-happy: empty attach does not auto-create", async ({ page }, testInfo) => {
    await stubLabChrome(page);
    await page.goto("/admin/validation-lab");
    await page.getByTestId("open-brainstorm-drawer").click();
    const drawer = page.getByTestId("scenario-brainstorm-drawer");
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Continue" })).toBeDisabled();
    await expect(drawer.getByRole("button", { name: /Create/ })).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath("01-empty-no-create.png"),
      fullPage: true,
    });
  });
});
