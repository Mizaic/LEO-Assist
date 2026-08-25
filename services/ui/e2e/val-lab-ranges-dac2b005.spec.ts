/**
 * VAL-DAC2B005 -- Default and organisation lab ranges.
 *
 * Atlas:
 *   UN: UN-15EEDC06
 *   DI: DI-6EFB48AB
 *   DO: DO-669C4B13
 *   VAL: VAL-DAC2B005
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  CONCEPT_ID,
  DISPLAY_NAME,
  ORG_FALLBACK_NAME,
  ORG_OVERLAY_NAME,
  PLATFORM_OWNER,
  stubLabRangeValRoutes,
} from "./helpers/lab-range-val-fixtures";
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

const VAL_ID = "VAL-DAC2B005";
const UN_ID = "UN-15EEDC06";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Results and Labs. Open a lab test. Open Reference ranges. Confirm a Platform default range is listed.",
  "Review an organisation overlay. Confirm it applies only to that organisation. Confirm other organisations keep their own ranges.",
  "Confirm an organisation with no overlay is not listed. That organisation uses the platform default.",
  "Confirm the add-range form has no service-level owner.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-DAC2B005 default and organisation lab ranges @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records default and organisation lab range evidence",
    {
      tag: ["@UN-15EEDC06", "@VAL-DAC2B005"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-DAC2B005 - Default and organisation lab ranges - quality validation",
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
          await stubLabRangeValRoutes(ctx.page);
          await ctx.page.goto("/admin/knowledge?tab=results-labs");
          await expect(ctx.page).toHaveURL(/tab=results-labs/);
          await expect(
            ctx.page.getByText("Lab metadata store"),
          ).toBeVisible({ timeout: 15_000 });
          await ctx.page.getByTestId("data-grid-row-" + CONCEPT_ID).click();
          await expect(ctx.page.getByRole("heading", { name: DISPLAY_NAME })).toBeVisible();
          await ctx.page.getByTestId("segmented-tab-ranges").click();
          await expect(ctx.page.getByTestId("add-range-form")).toBeVisible();

          const table = ctx.page.locator("table").filter({ hasText: "Owner" });
          await expect(table.getByText(PLATFORM_OWNER)).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Platform default range is listed for the lab test.",
          });
          ctx.lastCompletedStep.value = 0;

          await expect(table.getByText(ORG_OVERLAY_NAME)).toBeVisible();
          const owner = ctx.page.getByTestId("add-range-form").getByLabel("Owner");
          await owner.click();
          await owner.fill("oa");
          await ctx.page.getByRole("option", { name: /Oak GP/ }).click();
          await ctx.page.getByTestId("toolbar-action-add-range").click();
          const dialog = ctx.page.getByRole("dialog");
          await expect(dialog).toContainText(
            "This overlay applies only to the chosen organisation.",
          );
          await expect(dialog).toContainText(
            "Other organisations keep their own ranges.",
          );
          await expect(ctx.page.getByTestId("lab-add-confirm")).toContainText(
            ORG_OVERLAY_NAME,
          );
          await dialog.getByRole("button", { name: "Cancel" }).click();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "Organisation overlay confirm copy isolates the chosen organisation.",
          });
          ctx.lastCompletedStep.value = 1;

          await expect(table.getByText(ORG_FALLBACK_NAME)).toHaveCount(0);
          await expect(table.getByText(PLATFORM_OWNER)).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Organisation with no overlay is not listed and uses the default.",
          });
          ctx.lastCompletedStep.value = 2;

          const form = ctx.page.getByTestId("add-range-form");
          await expect(form.getByLabel("Service")).toHaveCount(0);
          await expect(form).not.toContainText(/service-level/i);
          await owner.click();
          await owner.fill("service");
          await expect(
            ctx.page.getByRole("option", { name: PLATFORM_OWNER }),
          ).toBeVisible();
          await expect(
            ctx.page.getByRole("option", { name: /service/i }),
          ).toHaveCount(0);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "Add-range form has no service-level owner.",
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
            notes: "Default, overlay, fallback, and no service owner are visible.",
          });
          ctx.lastCompletedStep.value = 4;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Platform default and organisation overlay are listed. Fallback org is not listed. Service-level owner is not offered.",
          );
        },
      });
    },
  );
});
