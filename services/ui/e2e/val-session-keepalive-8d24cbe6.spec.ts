/**
 * VAL-8D24CBE6 -- Stay signed in while working.
 *
 * Atlas:
 *   UN: UN-1C8660C6
 *   DI: DI-8A96990F
 *   DO: DO-F7C82FB5
 *   VAL: VAL-8D24CBE6
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  IDLE_OFF_COPY,
  IDLE_WARN_COPY,
  patchedBodies,
  stubSessionKeepaliveValRoutes,
} from "./helpers/session-keepalive-val-fixtures";
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

const VAL_ID = "VAL-8D24CBE6";
const UN_ID = "UN-1C8660C6";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open the product while signed in. Use a working page. Confirm I am not asked to sign in again.",
  "Leave the workstation unused for the idle period. Confirm I am warned and must sign in again if I do not stay.",
  "Open Login and Security. Set idle timeout to 0 (Off). Confirm idle expiry is turned off.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-8D24CBE6 stay signed in while working @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records stay-signed-in session evidence",
    {
      tag: ["@UN-1C8660C6", "@VAL-8D24CBE6"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-8D24CBE6 - Stay signed in while working - quality validation",
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
          await ctx.page.clock.install();
          await stubSessionKeepaliveValRoutes(ctx.page);
          await ctx.page.goto("/admin/portal");
          await expect(
            ctx.page.getByRole("heading", { name: "Platform Management" }),
          ).toBeVisible({ timeout: 15_000 });
          await expect(ctx.page).not.toHaveURL(/sign-in/);
          await expect(
            ctx.page.getByRole("heading", { name: "Are you still there?" }),
          ).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            notes: "Signed-in working page. No forced sign-in. Idle warning is not shown.",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page.clock.fastForward(90_000);
          const idleDialog = ctx.page.getByRole("dialog");
          await expect(idleDialog).toBeVisible();
          await expect(
            idleDialog.getByRole("heading", { name: "Are you still there?" }),
          ).toBeVisible();
          await expect(
            idleDialog.getByRole("button", { name: "Stay signed in" }),
          ).toBeVisible();
          await expect(
            idleDialog.getByRole("button", { name: "Sign out now" }),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            screenshotTarget: idleDialog,
            notes:
              "Unused workstation shows idle warning. Sign out now requires a new sign-in.",
          });
          ctx.lastCompletedStep.value = 1;

          await idleDialog.getByRole("button", { name: "Stay signed in" }).click();
          await expect(idleDialog).toHaveCount(0);
          await ctx.page.getByRole("tab", { name: "Login & Security" }).click();
          await expect(ctx.page.getByText(IDLE_WARN_COPY)).toBeVisible();
          await ctx.page.locator('input[type="number"]').fill("0");
          await expect(ctx.page.getByText("Off", { exact: true })).toBeVisible();
          await expect(ctx.page.getByText(IDLE_OFF_COPY)).toBeVisible();
          await ctx.page.getByRole("button", { name: "Save changes" }).click();
          await expect(ctx.page.getByText("Settings saved.")).toBeVisible();
          expect(patchedBodies[0]?.idle_timeout_minutes).toBe(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            notes:
              "Idle timeout set to 0. Off chip shown. Save sends idle_timeout_minutes 0.",
          });
          ctx.lastCompletedStep.value = 2;

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 3,
            notes: "Screenshots captured for each protocol step.",
          });
          ctx.lastCompletedStep.value = 3;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "VAL-8D24CBE6 stay-signed-in evidence recorded. Not a human pass.",
          );
        },
      });
    },
  );
});
