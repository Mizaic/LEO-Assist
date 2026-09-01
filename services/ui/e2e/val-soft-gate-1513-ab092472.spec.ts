/**
 * VAL-AB092472 -- 1.5.13 Assessment names first presentation.
 *
 * Atlas:
 *   UN: UN-5F3BF083
 *   DI: DI-C93802C8
 *   VAL: VAL-AB092472
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  COULD_NOT_CONFIRM,
  FIRST_PRESENTATION_ASKED,
  LETTER_TITLE,
  NOT_ON_FIT_LIST,
  PATIENT_ID,
  PATIENT_NAME,
  RULE_LINE,
  SCAN_STILL_OFFERED,
  UBRN,
  stubSoftGate1513ValRoutes,
} from "./helpers/soft-gate-1513-val-fixtures";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";

loadPlaywrightEnv();

const VAL_ID = "VAL-AB092472";
const UN_ID = "UN-5F3BF083";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open the Assessment for Unique Booking Reference Number 000481914514",
  "Confirm 1.5.13 can fire as consider ultrasound",
  "Confirm the Assessment names first presentation and says it could not be confirmed",
  "Confirm the Assessment says the scan was still offered so a possible cancer is not missed",
  "Confirm this letter is not on a missing-FIT list",
  "Capture a named screenshot at each step",
] as const;

test.describe("VAL-AB092472 1.5.13 first-presentation Assessment @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records 1.5.13 Assessment first-presentation evidence",
    {
      tag: ["@UN-5F3BF083", "@VAL-AB092472"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-AB092472 - 1.5.13 Assessment names first presentation on a real letter",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID, atlas_di_id: "DI-C93802C8" },
        protocol: PROTOCOL,
        body: async (ctx) => {
          await stubSoftGate1513ValRoutes(ctx.page);
          await ctx.page.goto("/care/patients/" + PATIENT_ID);
          await expect(ctx.page.getByText(PATIENT_NAME)).toBeVisible({
            timeout: 15_000,
          });
          await ctx.page.getByRole("tab", { name: "Documents" }).click();
          await ctx.page
            .getByRole("button", { name: new RegExp(LETTER_TITLE) })
            .click();
          await expect(ctx.page.getByText(UBRN).first()).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: `Opened Assessment for Unique Booking Reference Number ${UBRN}.`,
          });
          ctx.lastCompletedStep.value = 0;

          await expect(ctx.page.getByText(RULE_LINE).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "1.5.13 can fire as consider ultrasound.",
          });
          ctx.lastCompletedStep.value = 1;

          await expect(
            ctx.page.getByText(FIRST_PRESENTATION_ASKED).first(),
          ).toBeVisible();
          await expect(
            ctx.page.getByText(COULD_NOT_CONFIRM).first(),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes:
              "Assessment names first presentation and says it could not be confirmed.",
          });
          ctx.lastCompletedStep.value = 2;

          await expect(
            ctx.page.getByText(SCAN_STILL_OFFERED).first(),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes:
              "Assessment says the scan was still offered so a possible cancer is not missed.",
          });
          ctx.lastCompletedStep.value = 3;

          await expect(ctx.page.getByText(NOT_ON_FIT_LIST).first()).toBeVisible();
          await expect(
            ctx.page.getByText(/investigation_status=missing/i),
          ).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes:
              "This letter is not on a missing faecal immunochemical test list.",
          });
          ctx.lastCompletedStep.value = 4;

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 5,
            notes: "Named screenshots captured for each protocol step.",
          });
          ctx.lastCompletedStep.value = 5;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "1.5.13 Assessment names first presentation. Scan still offered. No missing FIT list.",
          );
        },
      });
    },
  );
});
