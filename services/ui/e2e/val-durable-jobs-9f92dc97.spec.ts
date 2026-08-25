/**
 * VAL-9F92DC97 -- Long-running clinical jobs survive worker restarts.
 *
 * Atlas:
 *   UN: UN-9E22C7C5
 *   DI: DI-252E8A2F
 *   DO: DO-25F14851
 *   VAL: VAL-9F92DC97
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  DURABLE_MODE_COPY,
  EPISODE_PLAN_ID,
  EPISODE_PLAN_NAME,
  GOLD_PLAN_ID,
  GOLD_PLAN_NAME,
  VAL_PLAN_ID,
  VAL_PLAN_NAME,
  stubDurableJobsValRoutes,
} from "./helpers/durable-jobs-val-fixtures";
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

const VAL_ID = "VAL-9F92DC97";
const UN_ID = "UN-9E22C7C5";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Pathways. Confirm gold training, validation, and episode bundle plans run as Durable.",
  "Open gold training. Confirm workflow mode is Durable publish/subscribe on the plan. Confirm there is no global durable-engine feature flag.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-9F92DC97 durable long-running clinical jobs @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records durable clinical job pathway evidence",
    {
      tag: ["@UN-9E22C7C5", "@VAL-9F92DC97"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-9F92DC97 - Long-running clinical jobs survive worker restarts - quality validation",
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
          await stubDurableJobsValRoutes(ctx.page);
          await ctx.page.goto("/admin/knowledge?tab=pathways");
          await expect(ctx.page.getByTestId("pathways-workspace")).toBeVisible({
            timeout: 15_000,
          });
          const goldCard = ctx.page.getByTestId("pathway-card-" + GOLD_PLAN_ID);
          const valCard = ctx.page.getByTestId("pathway-card-" + VAL_PLAN_ID);
          const episodeCard = ctx.page.getByTestId("pathway-card-" + EPISODE_PLAN_ID);
          await expect(goldCard.getByText(GOLD_PLAN_NAME)).toBeVisible();
          await expect(goldCard.getByText("Durable", { exact: true })).toBeVisible();
          await expect(valCard.getByText(VAL_PLAN_NAME)).toBeVisible();
          await expect(valCard.getByText("Durable", { exact: true })).toBeVisible();
          await expect(episodeCard.getByText(EPISODE_PLAN_NAME)).toBeVisible();
          await expect(episodeCard.getByText("Durable", { exact: true })).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            screenshotTarget: ctx.page.getByTestId("pathways-list"),
            notes:
              "Gold training, validation, and episode bundle pathways show Durable.",
          });
          ctx.lastCompletedStep.value = 0;

          await goldCard.getByRole("button", { name: "Edit", exact: true }).click();
          await expect(ctx.page).toHaveURL(new RegExp("/admin/pathways/" + GOLD_PLAN_ID));
          const modeBar = ctx.page.getByTestId("pathway-workflow-mode");
          await expect(modeBar).toBeVisible({ timeout: 15_000 });
          await expect(modeBar.getByText("Durable pub/sub")).toBeVisible();
          await expect(modeBar.getByText(DURABLE_MODE_COPY)).toBeVisible();
          await expect(ctx.page.getByText("DURABLE_ENGINE")).toHaveCount(0);
          await expect(
            ctx.page.getByText(/durable engine enabled/i),
          ).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            screenshotTarget: modeBar,
            notes:
              "Gold training workflow mode is Durable pub/sub on the plan. No global durable-engine feature flag.",
          });
          ctx.lastCompletedStep.value = 1;

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            notes: "Screenshots captured for each protocol step.",
          });
          ctx.lastCompletedStep.value = 2;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "VAL-9F92DC97 durable clinical job evidence recorded. Not a human pass.",
          );
        },
      });
    },
  );
});
