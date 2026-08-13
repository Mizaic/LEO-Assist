/**
 * VT-F0A6B9F4 -- Mark a fact as wrong in Validation Lab run review.
 *
 * Atlas: DI-C953EF73 / DI-238DA59A / DO-4FD76836
 */
import { expect, test } from "./fixtures";
import { stubKnowledgeAdminAuth, fulfillJson } from "./helpers/surface-forms-fixtures";

const INSPECTOR = {
  lab_run_id: "lab-1",
  pipeline_run_id: "pipe-1",
  lab_status: "completed",
  pipeline_status: "completed",
  plan_id: "pd-referral-assessment",
  plan_steps: [],
  plan_edges: [],
  spans: [
    {
      step_id: "extract",
      status: "completed",
      work_preview: {
        headline: "Found 1 fact",
        items: [{ kind: "fact", text: "chest pain" }],
      },
    },
  ],
  sse_path: "/api/pipeline/progress/pipe-1",
};

test.describe("Validation Lab mark as wrong (VT-F0A6B9F4)", () => {
  test("pick a rule, open review, mark a fact wrong, see Fix", async ({ page }) => {
    await stubKnowledgeAdminAuth(page);
    await page.route("**/api/validation-lab/cases", (route) => {
      if (route.request().method() === "POST") {
        return fulfillJson(route, {
          id: "case-1",
          title: "Rule test",
          referral_text: "chest pain",
        });
      }
      return fulfillJson(route, []);
    });
    await page.route("**/api/validation-lab/findings", (route) =>
      fulfillJson(route, []),
    );
    await page.route("**/api/guidance/rule-picker**", (route) =>
      fulfillJson(route, [
        {
          rule_id: "rule:NG12:1",
          name: "1.1.1",
          guideline_title: "NG12",
          recommendation_text: "Refer people with chest pain",
          trigger_terms: ["chest pain"],
        },
      ]),
    );
    await page.route("**/api/validation-lab/cases/case-1/runs", (route) =>
      fulfillJson(route, {
        run: { id: "lab-1", status: "completed", outputs: {} },
        case: { id: "case-1", title: "Rule test" },
      }),
    );
    await page.route("**/api/validation-lab/cases/case-1/runs/lab-1**", (route) => {
      const url = route.request().url();
      if (url.includes("/inspector")) {
        return fulfillJson(route, INSPECTOR);
      }
      return fulfillJson(route, {
        run: { id: "lab-1", status: "completed", outputs: {} },
        case: { id: "case-1" },
      });
    });
    await page.route("**/api/validation-lab/runs/lab-1/findings", (route) => {
      if (route.request().method() === "POST") {
        return fulfillJson(route, {
          id: "f1",
          run_id: "lab-1",
          stage_id: "extract",
          category: "extraction",
          target: "chest pain",
          note: "missed",
          status: "open",
        });
      }
      return fulfillJson(route, []);
    });

    await page.goto("/admin/knowledge?tab=validation-lab");
    await expect(page.getByTestId("validation-lab-page")).toBeVisible();
    await expect(page.getByTestId("validation-lab-mode-rule")).toBeVisible();
    await expect(page.getByTestId("validation-lab-mode-clinical")).toBeVisible();
    await page.getByTestId("validation-lab-mode-rule").click();
    await page.getByText("1.1.1").click();
    await expect(page.getByTestId("validation-lab-check-case")).toBeVisible();
    await page.getByRole("button", { name: "Run pipeline" }).click();
    await expect(page.getByTestId("validation-lab-run-review")).toBeVisible();
    await page.getByTestId("validation-lab-mark-wrong").click();
    await expect(page.getByTestId("validation-lab-mark-wrong-dialog")).toBeVisible();
    await page.getByTestId("validation-lab-flag-extraction").click();
    await page.getByTestId("validation-lab-mark-wrong-save").click();
    await expect(page.getByTestId("validation-lab-fix-open")).toBeVisible();
  });
});
