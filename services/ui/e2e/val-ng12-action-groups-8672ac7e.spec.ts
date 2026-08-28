/**
 * VAL-8672AC7E -- Preferred-fallback and either/or action groups.
 *
 * Atlas artefacts
 *   VAL : VAL-8672AC7E
 *   UN  : UN-49C83395   Load, Review, and Publish Guideline Rules
 *   DI  : DI-42246DA7   Review, Edit, Approve, or Reject Guideline Rules
 *   DO  : DO-F8C56339   Rule generation, review, and edit surface
 *
 * Sister walkthroughs (same DI surface):
 *   ng12-1-2-5-preferred-fallback-walkthrough.spec.ts
 *   ng12-1-9-1-preferred-fallback-walkthrough.spec.ts
 *   ng12-1-13-nss-or-actions-walkthrough.spec.ts
 */

import { expect, test } from "./fixtures";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";
import {
  btnByLabel,
  EITHER_OR_RULE,
  FALLBACK_RULE,
  goToSuggest,
  installFixtures,
  openEditDialog,
  openProcedurePicker,
  pickProcedure,
  setStrength,
  type DecisionBody,
} from "./helpers/ng12-action-group-val-fixtures";

loadPlaywrightEnv();

const VAL_ID = "VAL-8672AC7E";
const UN_ID = "UN-49C83395";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open /admin/knowledge?tab=clinical-guidelines, open the pending review pool, expand an NG12 rule, and open Edit rule.",
  "On Suggest, pick the preferred procedure (for example CT of abdomen and pelvis). Confirm the row shows the coded term.",
  "Click If not available, add... Confirm the UI shows Prefer the first. If it is not available...",
  "Code the fallback procedure (for example ultrasound of abdomen). Confirm both rows are coded and the live preview shows If that is not available.",
  "Set strength and priority, enter a save reason, and Approve and save. Confirm the decision payload has two actions with the same group_id, group_mode preferred_fallback, and ranks 0 then 1.",
  "Open a non-site-specific symptoms NG12 rule (1.13.2/3/4). On Suggest, code three either/or procedures using Or instead, add.... Confirm the live preview shows the either/or wording.",
  "Approve and save. Confirm the decision payload has three actions with the same group_id and group_mode any.",
] as const;

test.describe("VAL-8672AC7E NG12 action groups @val", () => {
  test.setTimeout(720_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records preferred-fallback and either-or action group evidence",
    {
      tag: ["@UN-49C83395", "@VAL-8672AC7E"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-8672AC7E - Preferred-fallback and either-or action groups",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID, atlas_di_id: "DI-42246DA7" },
        protocol: PROTOCOL,
        body: async (ctx) => {
          const captured: { decision: DecisionBody | null } = {
            decision: null,
          };
          await installFixtures(ctx.page, FALLBACK_RULE, captured);

          const dialog = await openEditDialog(ctx.page, FALLBACK_RULE);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Pending NG12 1.2.5 rule opened in Edit Rule dialog.",
          });
          ctx.lastCompletedStep.value = 0;

          await goToSuggest(dialog);
          await openProcedurePicker(dialog);
          await pickProcedure(
            ctx.page,
            dialog,
            "ct abdomen",
            /Use CT of abdomen and pelvis/i,
          );
          await expect(
            dialog.getByRole("button", { name: /ct of abdomen and pelvis/i }),
          ).toBeVisible({ timeout: 10000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "Preferred CT procedure coded on Suggest.",
          });
          ctx.lastCompletedStep.value = 1;

          await dialog
            .getByRole("button", {
              name: /If not available, add another procedure after row 1/i,
            })
            .click();
          await expect(
            dialog.getByText(/Prefer the first\. If it is not available/i),
          ).toBeVisible({ timeout: 10000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Preferred-fallback row added via If not available, add...",
          });
          ctx.lastCompletedStep.value = 2;

          await pickProcedure(
            ctx.page,
            dialog,
            "ultrasound",
            /Use Ultrasound scan of abdomen/i,
          );
          await expect(
            dialog.getByRole("button", { name: /ultrasound scan of abdomen/i }),
          ).toBeVisible({ timeout: 10000 });
          await expect(
            dialog.getByText(/If that is not available:/i),
          ).toBeVisible({ timeout: 10000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "Fallback ultrasound coded; live preview shows fallback wording.",
          });
          ctx.lastCompletedStep.value = 3;

          await setStrength(
            ctx.page,
            dialog,
            0,
            /Think about this test or referral/i,
          );
          await setStrength(
            ctx.page,
            dialog,
            1,
            /Think about this test or referral/i,
          );
          const prioritySelect = dialog.locator("#edit-rule-priority");
          await prioritySelect.scrollIntoViewIfNeeded();
          await prioritySelect.click();
          await ctx.page.getByRole("option", { name: /^Urgent\b/i }).click();

          await btnByLabel(dialog, /^Next/i).click();
          await expect(
            dialog.getByRole("heading", { name: /save your change/i }),
          ).toBeVisible({ timeout: 10000 });
          await dialog
            .getByLabel(/why are you changing this rule/i)
            .fill(
              "VAL-8672AC7E: NG12 1.2.5 CT preferred, ultrasound if not available.",
            );
          await btnByLabel(dialog, /approve and save/i).click();
          await expect(dialog).toBeHidden({ timeout: 15000 });

          const fallbackActions = captured.decision?.updates?.actions ?? [];
          expect(captured.decision?.action).toBe("edit");
          expect(fallbackActions).toHaveLength(2);
          expect(fallbackActions[0].group_mode).toBe("preferred_fallback");
          expect(fallbackActions[1].group_mode).toBe("preferred_fallback");
          expect(fallbackActions[0].group_id).toBe(fallbackActions[1].group_id);
          expect(fallbackActions.map((a) => a.group_rank)).toEqual([0, 1]);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes:
              "Preferred-fallback save confirmed: group_mode preferred_fallback, ranks 0/1.",
          });
          ctx.lastCompletedStep.value = 4;

          captured.decision = null;
          await installFixtures(ctx.page, EITHER_OR_RULE, captured);
          const eitherDialog = await openEditDialog(ctx.page, EITHER_OR_RULE);
          await goToSuggest(eitherDialog);
          await openProcedurePicker(eitherDialog);
          await pickProcedure(
            ctx.page,
            eitherDialog,
            "ct abdomen",
            /Use CT of abdomen and pelvis|Use Computed tomography of abdomen and pelvis/i,
          );
          await eitherDialog
            .getByRole("button", {
              name: /Or instead, add another procedure after row 1/i,
            })
            .click();
          await expect(
            eitherDialog.getByText(/Suggest either of these/i),
          ).toBeVisible({ timeout: 10000 });
          await pickProcedure(
            ctx.page,
            eitherDialog,
            "fast track referral",
            /^Use Fast track referral$/i,
          );
          await eitherDialog
            .getByRole("button", {
              name: /Or instead, add another procedure after row 2/i,
            })
            .click();
          await pickProcedure(
            ctx.page,
            eitherDialog,
            "non-specific",
            /Use Fast track referral for suspected cancer due to non-site-specific symptoms/i,
          );
          await expect(eitherDialog.getByText(/, or /i).first()).toBeVisible({
            timeout: 10000,
          });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 5,
            notes: "Three either/or procedures coded; live preview shows or wording.",
          });
          ctx.lastCompletedStep.value = 5;

          for (let i = 0; i < 3; i++) {
            await setStrength(
              ctx.page,
              eitherDialog,
              i,
              /Offer this test or referral/i,
            );
          }
          await btnByLabel(eitherDialog, /^Next/i).click();
          await eitherDialog
            .getByLabel(/why are you changing this rule/i)
            .fill(
              "VAL-8672AC7E: NG12 1.13.2 either/or urgent investigation, 2WW, NSS.",
            );
          await btnByLabel(eitherDialog, /approve and save/i).click();
          await expect(eitherDialog).toBeHidden({ timeout: 15000 });

          const anyActions = captured.decision?.updates?.actions ?? [];
          expect(captured.decision?.action).toBe("edit");
          expect(anyActions).toHaveLength(3);
          expect(anyActions.every((a) => a.group_mode === "any")).toBe(true);
          expect(anyActions[0].group_id).toBeTruthy();
          expect(
            anyActions.every((a) => a.group_id === anyActions[0].group_id),
          ).toBe(true);
          expect(anyActions.map((a) => a.group_rank)).toEqual([0, 1, 2]);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 6,
            notes: "Either/or save confirmed: group_mode any, ranks 0/1/2.",
          });
          ctx.lastCompletedStep.value = 6;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "VAL-8672AC7E passed: preferred_fallback (1.2.5) and any (1.13.2) action groups saved with screenshots.",
          );
        },
      });
    },
  );
});
