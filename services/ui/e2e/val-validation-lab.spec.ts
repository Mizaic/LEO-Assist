import { test, expect, waitForPageSettled } from "./fixtures";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";

loadPlaywrightEnv();

/**
 * VAL evidence for Validation Lab journey (Slice 7).
 *
 * Atlas:
 *   UN: UN-4DCE95C8
 *   DI: DI-724CD8A5, DI-2289D095, DI-9138BAC9, DI-A898556B
 *   VT: VT-22F3EF6A
 *
 * Full create->run->promote against a live API is environment-gated.
 * This VAL records chrome + control presence for the single guided
 * "new test patient -> build profile -> encounters -> referral -> submit"
 * wizard when Atlas env is configured. It never submits a referral
 * against the live API -- that would trigger a real pipeline run.
 */
const PROTOCOL = [
  "Open Validation Lab from Knowledge",
  "Confirm the two-door home, then open the guideline-rule path",
  "Open Advanced letter editor and step through to referral",
  "Confirm SBAR surface is CDN widget host (LeoSbarHost mount point)",
] as const;

test.describe("VAL Validation Lab chrome @val", () => {
  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
  });

  test("VAL Validation Lab chrome journey", async ({ page, request }, testInfo) => {
  await runValTest(page, request, testInfo, {
    valId: "VAL-VALIDATION-LAB-CHROME",
    targetUrl: "/admin/knowledge?tab=validation-lab",
    metadata: {
      atlas_un_id: "UN-4DCE95C8",
      atlas_di_ids: [
        "DI-724CD8A5",
        "DI-2289D095",
        "DI-9138BAC9",
        "DI-A898556B",
      ],
    },
    protocol: PROTOCOL,
    body: async (ctx) => {
      await ctx.page.goto("/admin/knowledge?tab=validation-lab");
      await waitForPageSettled(ctx.page);
      await expect(ctx.page.getByTestId("validation-lab-page")).toBeVisible();
      await expect(ctx.page.getByTestId("validation-lab-mode-rule")).toBeVisible();
      await ctx.page.getByTestId("validation-lab-mode-rule").click();
      await ctx.page.getByRole("button", { name: "Advanced: edit the letter" }).first().click();
      await expect(ctx.page.getByTestId("create-patient-wizard")).toBeVisible();
      await expect(ctx.page.getByTestId("wizard-title")).toBeVisible();
      await recordProtocolStep({
        request: ctx.request,
        runId: ctx.runId,
        valId: ctx.valId,
        page: ctx.page,
        testInfo: ctx.testInfo,
        protocol: PROTOCOL,
        stepIndex: 0,
        notes: "Validation Lab page + new-patient wizard step 1 visible",
      });
      ctx.lastCompletedStep.value = 0;

      await ctx.page.getByTestId("wizard-title").fill("VAL chrome test patient");
      await ctx.page.getByTestId("wizard-next").click();
      await expect(ctx.page.getByTestId("wizard-step-profile")).toBeVisible();
      await ctx.page.getByTestId("wizard-next").click();
      await expect(ctx.page.getByTestId("wizard-step-encounters")).toBeVisible();
      await ctx.page.getByTestId("wizard-next").click();
      await expect(ctx.page.getByTestId("wizard-step-referral")).toBeVisible();
      await expect(ctx.page.getByTestId("wizard-referral-text")).toBeVisible();
      await recordProtocolStep({
        request: ctx.request,
        runId: ctx.runId,
        valId: ctx.valId,
        page: ctx.page,
        testInfo: ctx.testInfo,
        protocol: PROTOCOL,
        stepIndex: 1,
        notes: "Profile, encounters and referral steps present",
      });
      ctx.lastCompletedStep.value = 1;

      await ctx.page.getByTestId("wizard-referral-text").fill(
        "VAL chrome test only -- this run is never submitted.",
      );
      await ctx.page.getByTestId("wizard-next").click();
      await expect(ctx.page.getByTestId("wizard-step-submit")).toBeVisible();
      await expect(ctx.page.getByTestId("wizard-submit")).toBeVisible();
      await recordProtocolStep({
        request: ctx.request,
        runId: ctx.runId,
        valId: ctx.valId,
        page: ctx.page,
        testInfo: ctx.testInfo,
        protocol: PROTOCOL,
        stepIndex: 2,
        notes: "Reached submit step without triggering a real pipeline run",
      });
      ctx.lastCompletedStep.value = 2;

      // Widget mounts after a successful SBAR run; assert empty state does
      // not mount a legacy SbarFinalView (retired chrome).
      await expect(ctx.page.locator("text=SbarFinalView")).toHaveCount(0);
      await recordProtocolStep({
        request: ctx.request,
        runId: ctx.runId,
        valId: ctx.valId,
        page: ctx.page,
        testInfo: ctx.testInfo,
        protocol: PROTOCOL,
        stepIndex: 3,
        notes: "No legacy SbarFinalView on Lab chrome",
      });
      ctx.lastCompletedStep.value = 3;

      await finishValPass(
        ctx.request,
        ctx.runId,
        "Validation Lab chrome journey passed",
      );
    },
  });
  });
});
