/**
 * VAL-8AE95F1A -- Staff enter with assigned role.
 *
 * Atlas:
 *   UN: UN-555D1547
 *   DI: DI-9C9F58BE, DI-9A42B933, DI-FDC9F12F
 *   DO: DO-1B883270, DO-3BF46FFA, DO-6FE21EE0
 *   VAL: VAL-8AE95F1A
 */

import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  BANNER_COPY,
  EXIT_LABEL,
  FIRST_ROLE,
  patchedRoles,
  setRoleEntryMode,
  stubRoleEntryValRoutes,
} from "./helpers/role-entry-val-fixtures";
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

const VAL_ID = "VAL-8AE95F1A";
const UN_ID = "UN-555D1547";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Sign in as staff with more than one allowed role. Confirm there is no role picker. Confirm the assigned role landing is shown.",
  "Sign in with no selected role. Confirm the first allowed role is applied. Confirm there is still no role picker.",
  "Confirm GET /auth/session returns needs_role_choice false.",
  "Sign in as a platform admin in a clinician role. Confirm the impersonation banner. Exit to platform admin. Confirm the banner is gone.",
  "Capture screenshots and record the run.",
] as const;

async function readSession(page: Page) {
  return page.evaluate(async () => {
    const res = await fetch("/auth/session", { credentials: "include" });
    return res.json();
  });
}

test.describe("VAL-8AE95F1A staff enter with assigned role @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records assigned-role entry evidence",
    {
      tag: ["@UN-555D1547", "@VAL-8AE95F1A"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-8AE95F1A - Staff enter with assigned role - quality validation",
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
          await stubRoleEntryValRoutes(ctx.page);
          await ctx.page.goto("/care/patients");
          await expect(
            ctx.page.getByRole("heading", { name: "Patients" }),
          ).toBeVisible({ timeout: 15_000 });
          await expect(
            ctx.page.getByTestId("role-picker-overlay"),
          ).toHaveCount(0);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            notes:
              "Assigned-role staff land on Patients. Role picker overlay is absent.",
          });
          ctx.lastCompletedStep.value = 0;

          patchedRoles.length = 0;
          setRoleEntryMode("auto_role");
          await ctx.page.goto("/care/patients");
          await expect(
            ctx.page.getByTestId("role-picker-overlay"),
          ).toHaveCount(0);
          await expect.poll(() => patchedRoles[0]).toBe(FIRST_ROLE);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            notes:
              "No selected role. First allowed role applied. Role picker still absent.",
          });
          ctx.lastCompletedStep.value = 1;

          const sessionBody = (await readSession(ctx.page)) as {
            needs_role_choice?: boolean;
          };
          expect(sessionBody.needs_role_choice).toBe(false);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            notes: "GET /auth/session returns needs_role_choice false.",
          });
          ctx.lastCompletedStep.value = 2;

          setRoleEntryMode("admin_impersonate");
          await ctx.page.goto("/care/patients");
          const banner = ctx.page.getByRole("alert", {
            name: "Platform admin impersonation active",
          });
          await expect(banner).toBeVisible({ timeout: 15_000 });
          await expect(banner.getByText(BANNER_COPY)).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 3,
            screenshotTarget: banner,
            notes:
              "Impersonation banner shown. Exit to platform admin is available.",
          });
          await banner.getByRole("button", { name: EXIT_LABEL }).click();
          await expect(banner).toHaveCount(0);
          expect(patchedRoles.at(-1)).toBe("platform_admin");
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
            "VAL-8AE95F1A assigned-role entry evidence recorded. Not a human pass.",
          );
        },
      });
    },
  );
});
