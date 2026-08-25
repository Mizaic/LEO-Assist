/**
 * VAL-0CE7EB38 -- Fine-tune clinical extraction rules without a code deployment.
 *
 * Atlas:
 *   UN: UN-494081B6
 *   DI: DI-34712A9A, DI-6ACD24D2, DI-DA60AC55
 *   DO: DO-F20DE29D, DO-6413D5BC
 *   VAL: VAL-0CE7EB38
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  CHANGED_BY,
  IMPACT_NOTE,
  NEW_PATTERN,
  SCOPE_ORG,
  SCOPE_PATHWAY,
  SCOPE_PLATFORM,
  createdBodies,
  stubGuardRulesValRoutes,
} from "./helpers/guard-rules-val-fixtures";
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

const VAL_ID = "VAL-0CE7EB38";
const UN_ID = "UN-494081B6";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Pipeline Guards. Add a guard rule. Confirm the Active switch. Confirm save. Confirm copy says no code change.",
  "Confirm the page stays on Pipeline Guards after save. Confirm the impact note about the next note check.",
  "Open an added rule. Confirm version history shows who changed it and when. Confirm Revert is available.",
  "Confirm listed rules include a platform-wide added rule, an organisation rule, and a pathway rule.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-0CE7EB38 fine-tune extraction rules @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records pipeline guard authoring evidence",
    {
      tag: ["@UN-494081B6", "@VAL-0CE7EB38"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-0CE7EB38 - Fine-tune extraction rules - quality validation",
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
          await stubGuardRulesValRoutes(ctx.page);
          await ctx.page.goto("/admin/knowledge?tab=guard-rules");
          await expect(ctx.page.getByTestId("guard-rules-workspace")).toBeVisible({
            timeout: 15_000,
          });
          await expect(
            ctx.page.getByText(/code change/i),
          ).toBeVisible();
          await ctx.page.getByTestId("toolbar-action-add-rule").click();
          const addDialog = ctx.page.getByRole("dialog").filter({
            has: ctx.page.getByRole("heading", { name: "Add guard rule" }),
          });
          await expect(addDialog).toBeVisible();
          await addDialog.getByLabel("Pattern").fill(NEW_PATTERN);
          await expect(addDialog.getByLabel("Active")).toBeVisible();
          await expect(ctx.page.getByTestId("rule-impact-banner")).toContainText(
            IMPACT_NOTE,
            { timeout: 8_000 },
          );
          await addDialog.getByTestId("rule-editor-save-btn").click();
          await expect.poll(() => createdBodies.length).toBe(1);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Guard rule can be added and turned off from Pipeline Guards.",
          });
          ctx.lastCompletedStep.value = 0;

          await expect(ctx.page).toHaveURL(/tab=guard-rules/);
          await expect(ctx.page.getByTestId("guard-rules-workspace")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "Save stays on Pipeline Guards. Impact note says no restart.",
          });
          ctx.lastCompletedStep.value = 1;

          await ctx.page.getByTestId("guard-family-card-scope_guard").click();
          const family = ctx.page.getByRole("dialog", { name: "Scope guard" });
          await expect(family).toBeVisible();
          await family.getByText(SCOPE_PLATFORM).click();
          await expect(ctx.page.getByTestId("rule-history-panel")).toBeVisible();
          await expect(ctx.page.getByTestId("rule-version-2")).toContainText(
            CHANGED_BY,
          );
          await expect(ctx.page.getByTestId("revert-to-v1")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "History shows who and when. Revert is available.",
          });
          ctx.lastCompletedStep.value = 2;

          await expect(family.getByText(SCOPE_PLATFORM).first()).toBeVisible();
          await expect(family.getByText(SCOPE_ORG).first()).toBeVisible();
          await expect(family.getByText(SCOPE_PATHWAY).first()).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "Platform, organisation, and pathway added rules are listed.",
          });
          ctx.lastCompletedStep.value = 3;

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes: "Pipeline Guards authoring, history, and scope evidence captured.",
          });
          ctx.lastCompletedStep.value = 4;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Pipeline Guards lets an admin add a rule without a code change. History shows who and when. Platform, organisation, and pathway rules are listed.",
          );
        },
      });
    },
  );
});
