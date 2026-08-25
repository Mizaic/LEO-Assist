/**
 * VAL-CF997D18 -- Link Validation Lab to product NCRs.
 *
 * Atlas:
 *   UN: UN-CCCD8D77
 *   DI: DI-287FFFD0, DI-ED5A9AC3
 *   DO: DO-4961CF34, DO-25990FB5
 *   VAL: VAL-CF997D18
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  NEW_NCR_TITLE,
  NHS_NUMBER,
  OPEN_NCR_TITLE,
  PATIENT_NAME,
  UBRN,
  createdBodies,
  eventBodies,
  stubValidationLabNcrValRoutes,
} from "./helpers/validation-lab-ncr-val-fixtures";
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

const VAL_ID = "VAL-CF997D18";
const UN_ID = "UN-CCCD8D77";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Validation Lab and search product non-conformances.",
  "Open a new non-conformance with a title, what went wrong, and how serious it is.",
  "Confirm the product is set for me and I cannot pick another.",
  "Link a case after the ticket is linked. Confirm the NHS number stays in Validation Lab.",
  "Confirm notes to the quality system do not include the NHS number or referral number.",
] as const;

test.describe("VAL-CF997D18 Validation Lab product records @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records Validation Lab product non-conformance evidence",
    {
      tag: ["@UN-CCCD8D77", "@VAL-CF997D18"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-CF997D18 - Validation Lab product records - quality validation",
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
          await stubValidationLabNcrValRoutes(ctx.page);
          await ctx.page.goto("/admin/knowledge?tab=validation-lab");
          await expect(
            ctx.page.getByTestId("validation-lab-page"),
          ).toBeVisible({ timeout: 15_000 });
          await expect(
            ctx.page.getByTestId("validation-lab-mode-clinical"),
          ).toBeVisible({ timeout: 10_000 });
          await ctx.page.getByTestId("validation-lab-mode-clinical").click();
          await expect(
            ctx.page.getByTestId("validation-lab-clinical-door"),
          ).toBeVisible({ timeout: 10_000 });
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-panel"),
          ).toBeVisible({ timeout: 10_000 });
          await expect(
            ctx.page.getByTestId("validation-lab-clinical-lookup"),
          ).toHaveCount(0);
          await ctx.page.getByLabel("Search product NCRs").fill("Missed");
          await ctx.page.getByTestId("validation-lab-ncr-search").click();
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-list"),
          ).toContainText(OPEN_NCR_TITLE);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Search finds an open product non-conformance.",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page.getByTestId("validation-lab-ncr-open-new").click();
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-form"),
          ).toBeVisible();
          await ctx.page.getByLabel("NCR title").fill(NEW_NCR_TITLE);
          await ctx.page
            .getByLabel("What went wrong")
            .fill("LEO missed a finding. Check the letter again.");
          await ctx.page.getByLabel("How serious").click();
          await ctx.page.getByRole("option", { name: "minor" }).click();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "New non-conformance form has title, what went wrong, and severity.",
          });
          ctx.lastCompletedStep.value = 1;

          const form = ctx.page.getByTestId("validation-lab-ncr-form");
          await expect(form).toContainText("Product is locked");
          await expect(form).not.toContainText("Pick a product");
          await expect(ctx.page.getByLabel("Product")).toHaveCount(0);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Product is locked. The form cannot pick another product.",
          });
          ctx.lastCompletedStep.value = 2;

          await ctx.page.getByTestId("validation-lab-ncr-save").click();
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-linked"),
          ).toContainText(NEW_NCR_TITLE);
          await expect(
            ctx.page.getByTestId("validation-lab-clinical-lookup"),
          ).toBeVisible();
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-cases-empty"),
          ).toContainText("stay in this investigation");
          await ctx.page
            .getByTestId("validation-lab-clinical-all-patients")
            .getByText(PATIENT_NAME)
            .click();
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-cases"),
          ).toContainText(PATIENT_NAME);
          await expect(
            ctx.page.getByTestId("validation-lab-clinical-all-patients"),
          ).toContainText(`NHS ${NHS_NUMBER}`);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "A local case is linked. The NHS number stays in Validation Lab.",
          });
          ctx.lastCompletedStep.value = 3;

          await expect.poll(() => eventBodies.length).toBeGreaterThan(0);
          const create = createdBodies[0] || {};
          const noteText = JSON.stringify(eventBodies);
          expect(create.product_id).toBeUndefined();
          expect(JSON.stringify(create)).not.toContain(NHS_NUMBER);
          expect(JSON.stringify(create)).not.toContain(UBRN);
          expect(noteText).not.toContain(NHS_NUMBER);
          expect(noteText).not.toContain(UBRN);
          expect(noteText).toMatch(/Local run/i);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes: "Create and journal notes do not include NHS number or referral number.",
          });
          ctx.lastCompletedStep.value = 4;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Validation Lab can search and open a product non-conformance, lock the product, link local cases, and redact Atlas notes.",
          );
        },
      });
    },
  );
});
