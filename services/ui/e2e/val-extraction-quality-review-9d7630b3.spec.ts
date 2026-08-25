/**
 * VAL-9D7630B3 -- check a weak letter then unlock.
 *
 * Atlas:
 *   UN: UN-89E2AE36
 *   DI: DI-4A012A59
 *   VAL: VAL-9D7630B3
 *
 * Review APIs are stubbed. This run does not start a live pipeline.
 */

import { expect, test, waitForPageSettled } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import {
  type CompletePayload,
  stubExtractionQualityReviewRoutes,
  VAL_TASK_ID,
} from "./helpers/extraction-quality-review-fixtures";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";

loadPlaywrightEnv();

const VAL_ID = "VAL-9D7630B3";
const UN_ID = "UN-89E2AE36";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open My work. You should see a paused extraction in the list.",
  "Click the paused extraction. You should stay on My work and see the letter editor.",
  "Check the letter against the draft facts. Fix a wrong tag if you see one. You should still see the letter and Approve and unlock.",
  "Click Approve and unlock. You should stay on My work.",
] as const;

test.describe("VAL-9D7630B3 extraction quality review @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records pause, open letter, and unlock evidence",
    {
      tag: ["@UN-89E2AE36", "@VAL-9D7630B3"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-9D7630B3 - Check a weak letter then unlock - clinician validation",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID, atlas_di_ids: ["DI-4A012A59"] },
        protocol: PROTOCOL,
        body: async (ctx) => {
          const completeCalls: CompletePayload[] = [];
          await stubExtractionQualityReviewRoutes(ctx.page, completeCalls);
          await ctx.page.goto("/work");
          await waitForPageSettled(ctx.page);
          await expect(
            ctx.page.getByRole("heading", { name: "My work", level: 1 }),
          ).toBeVisible({ timeout: 15_000 });

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            notes: "My work is open and a paused extraction is in the list",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page
            .getByTestId("task-queue-row-extraction_quality_pause:" + VAL_TASK_ID)
            .click();
          await expect(ctx.page).toHaveURL(/\/work/);
          await expect(
            ctx.page.getByText("Check paused extraction"),
          ).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            notes: "Clicked the paused extraction. The letter editor opened on My work.",
          });
          ctx.lastCompletedStep.value = 1;

          await expect(
            ctx.page.getByTestId("extraction-quality-letter"),
          ).toContainText("Cervix");
          await expect(
            ctx.page.getByText("This form is not one we have seen before"),
          ).toBeVisible();
          await expect(ctx.page.getByText("Why this referral paused")).toHaveCount(0);
          await expect(
            ctx.page.getByRole("button", { name: "Approve and unlock" }),
          ).toBeVisible();
          await ctx.page.getByLabel("Semantic tag for Cervix").selectOption("finding");
          await expect(ctx.page.getByLabel("Semantic tag for Cervix")).toHaveValue(
            "finding",
          );
          await expect(ctx.page.getByTestId("work-fix-panel")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            notes: "Checked the letter, changed the Cervix tag, and still saw Approve and unlock",
          });
          ctx.lastCompletedStep.value = 2;

          await ctx.page.getByRole("button", { name: "Approve and unlock" }).click();
          await expect.poll(() => completeCalls.length).toBe(1);
          expect(completeCalls[0]?.task_id).toBe(VAL_TASK_ID);
          expect(
            completeCalls[0]?.reviewed_entities?.some(
              (row) => row.text === "Cervix" && row.semantic_tag === "finding",
            ),
          ).toBe(true);
          await expect(ctx.page).toHaveURL(/\/work/);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 3,
            notes: "Clicked Approve and unlock and stayed on My work",
          });
          ctx.lastCompletedStep.value = 3;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Reviewer opened My work, checked the letter, fixed a tag, and approved.",
          );
        },
      });
    },
  );
});
