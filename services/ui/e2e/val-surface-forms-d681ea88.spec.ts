/**
 * VAL-D681EA88 -- local wording dictionary supports safe coding.
 *
 * Records Atlas validation execution runs with Playwright screencapture for
 * the automated admin UI protocol steps defined in Atlas.
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  buildGroupedSurfaceFormsPayload,
  fulfillJson,
  gotoSurfaceFormsTab,
  runSurfaceFormApprovalFlow,
  stubSurfaceFormAuditLog,
  stubSurfaceFormRoutes,
  SURFACE_FORM_NORMALIZED,
} from "./helpers/surface-forms-fixtures";
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

const VAL_ID = "VAL-D681EA88";
const UN_ID = "UN-72B60B2D";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const PROTOCOL = [
  "Step 1 - Automated API and policy checks: from repo root run .venv/bin/python -m pytest tests/test_surface_forms_management.py -v --no-coverage.",
  "Step 2 - Automated admin UI journey: from services/ui run npx playwright test e2e/surface-forms-approval.spec.ts --project=chromium.",
  "Step 3 - Draft link blocked from live use: confirm pytest cases show new links save as draft and resolve queries exclude pending links.",
  "Step 4 - Live resolve spot-check (staging or local when API available): add and approve a test local phrase and confirm resolve returns the approved concept.",
  "Step 5 - Duplicate link review: run duplicate link audit via admin tools or API and confirm conflicting links are flagged.",
  "Step 6 - Change history review: open change history for a sample link in the admin screen and confirm add, approval, and review events are listed.",
  "Step 7 - Clinical spot-check: a knowledge admin or clinical reviewer confirms 3 or more approved local phrases map to clinically appropriate concepts.",
  "Step 8 - Record evidence: call record_validation_run for this VAL with result pass or fail, environment local or staging, and attach evidence.",
] as const;

test.describe("VAL-D681EA88 local wording dictionary @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records automated admin UI and change-history evidence",
    {
      tag: ["@UN-72B60B2D", "@VAL-D681EA88"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-D681EA88 - Local wording dictionary supports safe coding",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: {
          atlas_un_id: UN_ID,
          automated_steps: ["1", "5"],
          vt_reference: "VT-8DE34E84",
        },
        protocol: PROTOCOL,
        body: async (ctx) => {
          const counters = await stubSurfaceFormRoutes(ctx.page);
          await gotoSurfaceFormsTab(ctx.page);
          await runSurfaceFormApprovalFlow(ctx.page);
          await expect.poll(counters.getApproveCalls).toBe(1);
          await expect.poll(counters.getDeactivateCalls).toBe(1);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes:
              "Approve and deactivate controls exercised on stubbed surface form alias.",
          });
          ctx.lastCompletedStep.value = 1;

          await ctx.page.route("**/api/terminology/surface-forms/grouped**", (route) =>
            fulfillJson(route, buildGroupedSurfaceFormsPayload("approved")),
          );
          await stubSurfaceFormAuditLog(ctx.page);
          await gotoSurfaceFormsTab(ctx.page);
          await ctx.page.getByTestId("toolbar-action-audit-log").click();
          await expect(
            ctx.page.getByRole("dialog", { name: "Change log" }),
          ).toBeVisible();
          await expect(
            ctx.page.getByText(`approve · ${SURFACE_FORM_NORMALIZED}`),
          ).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 5,
            screenshotTarget: ctx.page.getByRole("dialog", {
              name: "Change log",
            }),
            notes: "Change log lists approve and upsert audit entries.",
          });
          ctx.lastCompletedStep.value = 5;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Automated Playwright evidence recorded for protocol steps 2 and 6. Steps 1, 3-5, 7-8 remain manual or pytest-backed.",
          );
        },
      });
    },
  );
});
