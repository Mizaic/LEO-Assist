/**
 * VAL-469227B6 -- Unified patient record.
 *
 * Atlas:
 *   UN: UN-F4580C34
 *   DI: DI-0ADA35BF, DI-357A7468
 *   DO: DO-EBF0B124, DO-5D3EA371
 *   VAL: VAL-469227B6
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  MIXED_ID,
  MIXED_NAME,
  PRIMARY_ID,
  PRIMARY_NAME,
  TIMELINE_LABELS,
  stubUnifiedPatientRecordValRoutes,
} from "./helpers/unified-patient-record-val-fixtures";
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

const VAL_ID = "VAL-469227B6";
const UN_ID = "UN-F4580C34";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open a patient who has a cancer episode, a referral episode, and a primary care episode. Confirm all three episodes are shown.",
  "Open a patient who is not on a cancer pathway. Confirm the record does not show empty cancer fields or not-applicable labels.",
  "Open the Timeline tab. Confirm all clinical activity is listed in date order with type labels.",
  "Confirm the patient view loads for a patient who has no cancer diagnosis.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-469227B6 unified patient record @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records unified patient record evidence",
    {
      tag: ["@UN-F4580C34", "@VAL-469227B6"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-469227B6 - Unified patient record - clinician validation",
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
          await stubUnifiedPatientRecordValRoutes(ctx.page);
          await ctx.page.goto("/care/patients");
          await expect(
            ctx.page.getByRole("heading", { name: "Patients" }),
          ).toBeVisible({ timeout: 15_000 });
          await expect(ctx.page.getByText(MIXED_ID)).toBeVisible();
          await expect(ctx.page.getByText(PRIMARY_ID)).toBeVisible();
          await expect(ctx.page.getByText(/cancer type/i)).toHaveCount(0);
          await ctx.page.getByText(MIXED_ID).click();
          await expect(ctx.page.getByText(MIXED_NAME)).toBeVisible({
            timeout: 15_000,
          });
          const overview = ctx.page.getByTestId("epr-overview-panel");
          await expect(overview).toBeVisible();
          await expect(overview.getByText(/^breast$/i)).toBeVisible();
          await expect(overview.getByText(/^referral$/i)).toBeVisible();
          await expect(overview.getByText(/primary care/i)).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            notes:
              "Mixed-episode patient shows cancer, referral, and primary care episodes.",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page.goto("/care/patients/" + PRIMARY_ID);
          await expect(ctx.page.getByText(PRIMARY_NAME)).toBeVisible({
            timeout: 15_000,
          });
          const primaryOverview = ctx.page.getByTestId("epr-overview-panel");
          await expect(primaryOverview).toBeVisible();
          await expect(primaryOverview.getByText(/primary care/i)).toBeVisible();
          await expect(ctx.page.getByText(/^Stage /)).toHaveCount(0);
          await expect(ctx.page.getByText(/Cancer confirmed/i)).toHaveCount(0);
          await expect(ctx.page.getByText(/not applicable/i)).toHaveCount(0);
          await expect(ctx.page.getByText(/\bN\/A\b/)).toHaveCount(0);
          await expect(ctx.page.getByText(/tumour type/i)).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            notes:
              "Primary care record has no empty cancer fields or not-applicable labels.",
          });
          ctx.lastCompletedStep.value = 1;

          await ctx.page.getByRole("tab", { name: "Timeline" }).click();
          const activity = ctx.page.getByTestId("epr-timeline-activity");
          await expect(activity).toBeVisible({ timeout: 15_000 });
          await expect(activity.getByText("Encounter", { exact: true })).toBeVisible();
          await expect(activity.getByText("Episode", { exact: true })).toBeVisible();
          await expect(activity.getByText("Alert", { exact: true })).toBeVisible();
          await expect(activity.getByText("Document", { exact: true })).toBeVisible();
          const activityText = await activity.innerText();
          const encounterAt = activityText.indexOf(TIMELINE_LABELS.encounter);
          const episodeAt = activityText.indexOf(TIMELINE_LABELS.episode);
          const alertAt = activityText.indexOf(TIMELINE_LABELS.alert);
          const documentAt = activityText.indexOf(TIMELINE_LABELS.document);
          expect(encounterAt).toBeGreaterThanOrEqual(0);
          expect(encounterAt).toBeLessThan(episodeAt);
          expect(episodeAt).toBeLessThan(alertAt);
          expect(alertAt).toBeLessThan(documentAt);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            screenshotTarget: activity,
            notes:
              "Timeline lists encounter, episode, alert, and document newest first.",
          });
          ctx.lastCompletedStep.value = 2;

          await expect(ctx.page.getByText(PRIMARY_NAME)).toBeVisible();
          await expect(ctx.page.getByText(/TypeError/i)).toHaveCount(0);
          await expect(
            ctx.page.getByText(/Unable to load patient/i),
          ).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 3,
            notes:
              "Patient view loads for a patient with no cancer diagnosis.",
          });
          ctx.lastCompletedStep.value = 3;

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 4,
            notes: "Screenshots captured for each protocol step.",
          });
          ctx.lastCompletedStep.value = 4;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "VAL-469227B6 unified patient record evidence recorded. Not a human pass.",
          );
        },
      });
    },
  );
});
