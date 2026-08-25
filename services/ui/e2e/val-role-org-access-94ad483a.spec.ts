/**
 * VAL-94AD483A -- Role and organisation access.
 *
 * Atlas:
 *   UN: UN-E9B9E7A9
 *   DI: DI-CC9077EF, DI-D2F780A7, DI-F2B4FFDC
 *   DO: DO-19BA3D73, DO-912E75A6, DO-CE0CC81B
 *   VAL: VAL-94AD483A
 */

import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  ACCESS_DENIED,
  DENIED_ID,
  DENIED_NHS,
  HIDDEN_NAME,
  REFERRED_ID,
  setRoleAccessMode,
  stubRoleAccessValRoutes,
} from "./helpers/role-org-access-val-fixtures";
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

const VAL_ID = "VAL-94AD483A";
const UN_ID = "UN-E9B9E7A9";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open a clinical page with no LEO role. Confirm the no-access screen. Confirm clinical menus are hidden.",
  "Sign in as a Service Provider clinician. Confirm a referred patient is on the list. Open a patient with no referral. Confirm access is denied and no clinical details are shown.",
  "Confirm Patients is in the menu for a Service Provider. Sign in as an Integrated Care Board (ICB) clinician. Confirm Patients is hidden.",
  "Capture screenshots and record the run.",
] as const;

function patientsNav(page: Page) {
  return page.getByRole("navigation").getByText("Patients", { exact: true });
}

test.describe("VAL-94AD483A role and organisation access @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records role and organisation access evidence",
    {
      tag: ["@UN-E9B9E7A9", "@VAL-94AD483A"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-94AD483A - Role and organisation access - quality validation",
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
          await stubRoleAccessValRoutes(ctx.page);
          await ctx.page.goto("/care/patients");
          await expect(
            ctx.page.getByRole("heading", { name: "You do not have access" }),
          ).toBeVisible({ timeout: 15_000 });
          await expect(
            ctx.page.getByRole("button", { name: "Sign out" }),
          ).toBeVisible();
          await expect(ctx.page.getByRole("navigation")).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            notes:
              "No LEO role. No-access screen shown. Clinical menus hidden.",
          });
          ctx.lastCompletedStep.value = 0;

          setRoleAccessMode("service_provider");
          await ctx.page.goto("/care/patients");
          await expect(
            ctx.page.getByRole("heading", { name: "Patients" }),
          ).toBeVisible({ timeout: 15_000 });
          await expect(ctx.page.getByText(REFERRED_ID)).toBeVisible();
          await expect(ctx.page.getByText("1 referral")).toBeVisible();
          await expect(ctx.page.getByText(DENIED_ID)).toHaveCount(0);
          await ctx.page.goto("/care/patients/" + DENIED_ID);
          await expect(ctx.page.getByText(ACCESS_DENIED)).toBeVisible({
            timeout: 15_000,
          });
          await expect(ctx.page.getByText(HIDDEN_NAME)).toHaveCount(0);
          await expect(ctx.page.getByText(DENIED_NHS)).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            notes:
              "Service Provider list shows referred patient. Unreferred patient is denied with no clinical details.",
          });
          ctx.lastCompletedStep.value = 1;

          await expect(patientsNav(ctx.page).first()).toBeVisible();
          setRoleAccessMode("icb");
          await ctx.page.goto("/settings");
          await expect(ctx.page.getByRole("navigation").first()).toBeVisible({
            timeout: 15_000,
          });
          await expect(patientsNav(ctx.page)).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            screenshotTarget: ctx.page.getByRole("navigation").first(),
            notes:
              "Patients menu visible for Service Provider. Hidden for Integrated Care Board clinician.",
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
            "VAL-94AD483A role and organisation access evidence recorded. Not a human pass.",
          );
        },
      });
    },
  );
});
