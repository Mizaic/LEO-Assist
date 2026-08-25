/**
 * G5.9 -- Validation Lab durable referral run with real SBAR output.
 *
 * Atlas:
 *   UN: UN-4DCE95C8
 *   VAL: VAL-2A1EDC22 (Gate 5 item G5.9)
 *
 * Manual / staging only per docs/GATE5-TEST-POLICY.md. Requires Atlas env
 * plus PLAYWRIGHT_LIVE_BACKEND=1 and a running API + pipeline worker.
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { blockRun } from "./helpers/validation-blocked";
import {
  finishValPass,
  runValTest,
} from "./helpers/validation-spec-runner";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";
import {
  installLiveBackendServiceAuth,
  isLiveBackendConfigured,
  liveBackendSkipReason,
  wizardField,
} from "./helpers/validation-lab-live";
import { openCreatePatientWizard } from "./helpers/validation-lab-wizard";

loadPlaywrightEnv();

const VAL_ID = "VAL-2A1EDC22";
const UN_ID = "UN-4DCE95C8";
const TARGET_URL =
  process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Validation Lab and start a generic referral test patient",
  "Submit the case and poll until the durable pipeline run completes",
  "Confirm SBAR widget host renders Situation through Recommendation",
  "Capture compliance or recall review alerts when present",
] as const;

const RUN_TIMEOUT_MS = 180_000;

test.describe("G5.9 Validation Lab durable SBAR @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records durable Validation Lab SBAR evidence",
    {
      tag: ["@UN-4DCE95C8", "@VAL-2A1EDC22"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-2A1EDC22 - Validation Lab durable referral SBAR run",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: `${TARGET_URL}/admin/knowledge?tab=validation-lab`,
        metadata: {
          atlas_un_id: UN_ID,
          gate: "G5.9",
        },
        protocol: PROTOCOL,
        body: async (ctx) => {
          if (!isLiveBackendConfigured()) {
            await blockRun(
              ctx.request,
              ctx.runId,
              PROTOCOL[0],
              liveBackendSkipReason() ?? "Live backend not configured.",
            );
          }

          await installLiveBackendServiceAuth(ctx.page);

          await openCreatePatientWizard(ctx.page);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            screenshotTarget: ctx.page.getByTestId("create-patient-wizard"),
            notes: "Validation Lab wizard ready for referral case",
          });
          ctx.lastCompletedStep.value = 0;

          const stamp = Date.now();
          await wizardField(ctx.page, "wizard-title").fill(
            `G5.9 durable ${stamp}`,
          );
          await ctx.page.getByTestId("wizard-next").click();
          await ctx.page.getByTestId("wizard-next").click();
          await ctx.page.getByTestId("wizard-next").click();
          await wizardField(ctx.page, "wizard-referral-text").fill(
            "62-year-old with progressive dysphagia and weight loss. " +
              "Refer under 2WW upper GI pathway.",
          );
          await ctx.page.getByTestId("wizard-next").click();
          await expect(ctx.page.getByTestId("wizard-step-submit")).toBeVisible();
          await ctx.page.getByTestId("wizard-submit").click();

          const status = ctx.page.getByTestId("wizard-run-status");
          await expect(status).toBeVisible({ timeout: 30_000 });
          await expect(status).toContainText(/completed|failed/, {
            timeout: RUN_TIMEOUT_MS,
          });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            screenshotTarget: status,
            notes: "Durable pipeline run reached terminal status",
          });
          ctx.lastCompletedStep.value = 1;

          const runText = (await status.textContent()) ?? "";
          if (!runText.includes("completed")) {
            throw new Error(`Pipeline run did not complete: ${runText}`);
          }

          await expect(ctx.page.getByTestId("wizard-sbar")).toBeVisible({
            timeout: 30_000,
          });
          await expect(ctx.page.getByTestId("leo-sbar-host")).toBeVisible();
          await expect(ctx.page.getByTestId("leo-sbar-widget")).toBeVisible({
            timeout: 60_000,
          });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            screenshotTarget: ctx.page.getByTestId("leo-sbar-widget"),
            notes: "LeoSbarHost mounted with leo-sbar widget",
          });
          ctx.lastCompletedStep.value = 2;

          const alertCount =
            (await ctx.page.getByTestId("leo-sbar-compliance-alert").count()) +
            (await ctx.page.getByTestId("leo-sbar-recall-alert").count());
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 3,
            screenshotTarget: ctx.page.getByTestId("leo-sbar-host"),
            notes: `SBAR chrome visible; alert surfaces present=${alertCount > 0}`,
          });
          ctx.lastCompletedStep.value = 3;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "G5.9 durable Validation Lab SBAR journey passed",
          );
        },
      });
    },
  );
});
