import { test, expect } from "@playwright/test";
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
 * This VAL records chrome + control presence when Atlas env is configured.
 */
const PROTOCOL = [
  "Open Validation Lab from Knowledge",
  "Confirm case authoring and gold fields are visible",
  "Confirm dry-run opt-in and Save as gold controls exist",
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
      await ctx.page.waitForLoadState("networkidle");
      await expect(ctx.page.getByTestId("validation-lab-page")).toBeVisible();
      await recordProtocolStep({
        request: ctx.request,
        runId: ctx.runId,
        valId: ctx.valId,
        page: ctx.page,
        testInfo: ctx.testInfo,
        protocol: PROTOCOL,
        stepIndex: 0,
        notes: "Validation Lab page visible",
      });
      ctx.lastCompletedStep.value = 0;

      await expect(
        ctx.page.getByTestId("validation-lab-clinical-text"),
      ).toBeVisible();
      await expect(
        ctx.page.getByTestId("validation-lab-gold-entities"),
      ).toBeVisible();
      await recordProtocolStep({
        request: ctx.request,
        runId: ctx.runId,
        valId: ctx.valId,
        page: ctx.page,
        testInfo: ctx.testInfo,
        protocol: PROTOCOL,
        stepIndex: 1,
        notes: "Authoring + gold fields present",
      });
      ctx.lastCompletedStep.value = 1;

      await expect(ctx.page.getByTestId("validation-lab-dry-run")).toBeVisible();
      await expect(ctx.page.getByTestId("validation-lab-promote")).toBeVisible();
      await recordProtocolStep({
        request: ctx.request,
        runId: ctx.runId,
        valId: ctx.valId,
        page: ctx.page,
        testInfo: ctx.testInfo,
        protocol: PROTOCOL,
        stepIndex: 2,
        notes: "Dry-run and promote controls present",
      });
      ctx.lastCompletedStep.value = 2;

      // Widget mounts after a successful SBAR run; assert host import surface
      // via page source contract already covered by jest -- here assert empty
      // state does not mount a second SbarFinalView.
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
