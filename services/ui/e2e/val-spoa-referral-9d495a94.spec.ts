/**
 * VAL-9D495A94 -- Elective Single Point of Access consultant review.
 *
 * Atlas:
 *   UN: UN-9805B48E
 *   DI: DI-5133534D, DI-0C8DC7AB, DI-45F32638, DI-4AF9CB8D
 *   DO: DO-EBD03C23, DO-8DF3E4A3
 *   VAL: VAL-9D495A94
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  ADVISORY_TEXT,
  DISPOSITION,
  LETTER_TITLE,
  OFFER_NOT_SUPPORT,
  OTHER_GUIDELINES,
  PATIENT_ID,
  PATIENT_NAME,
  PRIMARY_SUPPORT,
  SERVICE_NAME,
  stubSpoaReferralValRoutes,
} from "./helpers/spoa-referral-val-fixtures";
import {
  finishValPass,
  runValTest,
} from "./helpers/validation-spec-runner";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";

loadPlaywrightEnv();

const VAL_ID = "VAL-9D495A94";
const UN_ID = "UN-9805B48E";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open the patient record. Confirm Assessment names the receiving healthcare service from the inbound referral.",
  "Confirm Assessment shows whether coded clinical facts are supported by that service's guidelines first.",
  "When they are not, confirm other guidelines that would support the request are listed.",
  "Confirm one advisory Single Point of Access (SPoA) disposition. Confirm LEO does not book tests, slots, or send letters without a person confirming.",
  "Confirm Assessment and Recommendation clearly state the output is advisory.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-9D495A94 elective SPoA consultant review @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records elective SPoA consultant review evidence",
    {
      tag: ["@UN-9805B48E", "@VAL-9D495A94"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-9D495A94 - Elective Single Point of Access consultant review - quality validation",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID },
        protocol: PROTOCOL,
        body: async (ctx) => {
          await stubSpoaReferralValRoutes(ctx.page);
          await ctx.page.goto("/care/patients/" + PATIENT_ID);
          await expect(ctx.page.getByText(PATIENT_NAME)).toBeVisible({
            timeout: 15_000,
          });
          await expect(ctx.page.getByTestId("epr-latest-sbar")).toBeVisible();
          await ctx.page.getByRole("tab", { name: "Documents" }).click();
          await ctx.page
            .getByRole("button", { name: new RegExp(`^${LETTER_TITLE}`) })
            .click();
          await expect(ctx.page.getByText(SERVICE_NAME).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            notes: "Assessment names receiving service Gastroenterology (Hepatology).",
          });
          ctx.lastCompletedStep.value = 0;

          await expect(ctx.page.getByText(PRIMARY_SUPPORT).first()).toBeVisible();
          await expect(ctx.page.getByText(OFFER_NOT_SUPPORT).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            notes: "Primary receiving-service guideline support is shown as no.",
          });
          ctx.lastCompletedStep.value = 1;

          await expect(ctx.page.getByText(OTHER_GUIDELINES).first()).toBeVisible();
          await expect(
            ctx.page.getByText("NG12 suspected-cancer colorectal").first(),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            notes: "Other supporting guidelines are listed when primary does not match.",
          });
          ctx.lastCompletedStep.value = 2;

          await expect(ctx.page.getByText(DISPOSITION).first()).toBeVisible();
          await expect(
            ctx.page.getByRole("button", { name: /book (a )?test/i }),
          ).toHaveCount(0);
          await expect(
            ctx.page.getByRole("button", { name: /book slot/i }),
          ).toHaveCount(0);
          await expect(
            ctx.page.getByRole("button", { name: /send letter/i }),
          ).toHaveCount(0);
          await ctx.page.getByRole("tab", { name: "Overview" }).click();
          await expect(ctx.page.getByTestId("leo-sbar-download-pdf")).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 3,
            notes:
              "One advisory SPoA disposition. No book, slot, or send-letter action. PDF download is reviewer-only.",
          });
          ctx.lastCompletedStep.value = 3;

          await ctx.page.getByRole("tab", { name: "Documents" }).click();
          await ctx.page
            .getByRole("button", { name: new RegExp(`^${LETTER_TITLE}`) })
            .click();
          await expect(ctx.page.getByText(DISPOSITION).first()).toBeVisible();
          await expect(ctx.page.getByText(ADVISORY_TEXT).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 4,
            notes:
              "Recommendation labels the SPoA disposition as advisory. Assessment and Recommendation carry the clinician-review disclaimer.",
          });
          ctx.lastCompletedStep.value = 4;

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 5,
            notes: "Screenshots captured for each protocol step.",
          });
          ctx.lastCompletedStep.value = 5;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "VAL-9D495A94 elective SPoA consultant review evidence recorded. Not a human pass.",
          );
        },
      });
    },
  );
});
