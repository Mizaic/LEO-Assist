/**
 * VAL-4EAC0FF0 -- AI and cloud costs per patient case.
 *
 * Atlas:
 *   UN: UN-9828175D
 *   DI: DI-CDF1C4D4, DI-21FD1EC2
 *   DO: DO-4D2BEA1D, DO-FD338D48
 *   VAL: VAL-4EAC0FF0
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  DISCOUNT_COPY,
  LIST_AT_75,
  LIST_AT_80,
  ORG_NAME,
  PATIENT_COST,
  PATIENT_ID,
  PLATFORM_TYPE,
  RAW_COST,
  postDiscountBodies,
  putMarginBodies,
  stubCostTrackingValRoutes,
} from "./helpers/cost-tracking-val-fixtures";
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

const VAL_ID = "VAL-4EAC0FF0";
const UN_ID = "UN-9828175D";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Care Overview. Confirm AI model spend for a patient case, with cost shown.",
  "Open Platform Billing. Confirm raw cost, list price, and billable amount for a customer organisation.",
  "Set the target profit margin and save. Confirm the organisation list price includes the margin.",
  "Add a time-limited discount for that organisation. Confirm the underlying raw cost does not change.",
  "Confirm platform operating costs, such as testing, are shown separately and not billed to tenants.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-4EAC0FF0 AI and cloud costs per patient case @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records AI and cloud cost tracking evidence",
    {
      tag: ["@UN-9828175D", "@VAL-4EAC0FF0"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-4EAC0FF0 - AI and cloud costs per patient case - quality validation",
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
          await stubCostTrackingValRoutes(ctx.page);
          await ctx.page.goto("/care/dashboard");
          const spendHeading = ctx.page.getByRole("heading", {
            name: "AI model spend",
          });
          await expect(spendHeading).toBeVisible({ timeout: 15_000 });
          await expect(ctx.page.getByText(PATIENT_ID)).toBeVisible();
          await expect(ctx.page.getByText(PATIENT_COST).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 0,
            screenshotTarget: spendHeading,
            notes: "Care Overview shows AI model spend for a patient case.",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page.goto("/admin/platform?tab=billing");
          await expect(
            ctx.page.getByText("Billing & pricing"),
          ).toBeVisible({ timeout: 15_000 });
          await expect(ctx.page.getByText(ORG_NAME)).toBeVisible();
          await expect(ctx.page.getByText(RAW_COST).first()).toBeVisible();
          await expect(ctx.page.getByText(LIST_AT_75).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 1,
            notes:
              "Organisation raw cost, list price, and billable amount are shown.",
          });
          ctx.lastCompletedStep.value = 1;

          await ctx.page.getByText("80%", { exact: true }).click();
          await ctx.page.getByRole("button", { name: "Save margin" }).click();
          await expect(
            ctx.page.getByText("Margin updated to 80.0%."),
          ).toBeVisible();
          expect(putMarginBodies[0]?.targetMargin).toBe(0.8);
          await expect(ctx.page.getByText(LIST_AT_80).first()).toBeVisible();
          await expect(ctx.page.getByText(RAW_COST).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 2,
            notes:
              "Target margin saved at 80 percent. List price includes the margin.",
          });
          ctx.lastCompletedStep.value = 2;

          await ctx.page.getByText(ORG_NAME).click();
          await ctx.page.getByRole("button", { name: "Add discount" }).click();
          const dialog = ctx.page.getByRole("dialog");
          await expect(dialog).toBeVisible();
          await dialog.getByLabel("Description *").fill(DISCOUNT_COPY);
          await dialog.getByLabel("Valid to").fill("2026-12-31");
          await dialog.getByRole("button", { name: "Add discount" }).click();
          await expect(dialog).toHaveCount(0);
          expect(postDiscountBodies[0]?.rate).toBe(0.1);
          expect(postDiscountBodies[0]?.type).toBe("promo");
          expect(postDiscountBodies[0]?.validTo).toBeTruthy();
          await expect(ctx.page.getByText(RAW_COST).first()).toBeVisible();
          await expect(ctx.page.getByText(/10\.0%/).first()).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 3,
            notes:
              "Time-limited discount added. Underlying raw cost is unchanged.",
          });
          ctx.lastCompletedStep.value = 3;

          const platformCard = ctx.page.getByText("Platform operating costs");
          await expect(platformCard).toBeVisible();
          await expect(ctx.page.getByText("not billed to tenants")).toBeVisible();
          await expect(ctx.page.getByText(PLATFORM_TYPE)).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 4,
            screenshotTarget: platformCard,
            notes:
              "Platform operating costs shown separately and not billed to tenants.",
          });
          ctx.lastCompletedStep.value = 4;

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: PROTOCOL,
            stepIndex: 5,
            notes: "Screenshots captured for each protocol step.",
          });
          ctx.lastCompletedStep.value = 5;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "VAL-4EAC0FF0 cost tracking evidence recorded. Not a human pass.",
          );
        },
      });
    },
  );
});
