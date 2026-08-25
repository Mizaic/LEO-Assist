/**
 * VAL-25DA430F -- Log repeated pipeline issues in Atlas.
 *
 * Atlas:
 *   UN: UN-656248A7
 *   DI: DI-C7DEF132
 *   DO: DO-67EE14A1
 *   VAL: VAL-25DA430F
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  DIGEST_TITLE,
  ESCALATE_TITLE,
  stubPhoneHomeValRoutes,
} from "./helpers/phone-home-val-fixtures";
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

const VAL_ID = "VAL-25DA430F";
const UN_ID = "UN-656248A7";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Validation Lab and choose Investigate a non-conformance.",
  "Confirm the list shows one open phone-home record per issue family.",
  "Confirm an escalate phone-home record is present at once.",
  "Confirm titles have no patient id, NHS number, or letter text.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-25DA430F phone-home quality records @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records phone-home quality record evidence",
    {
      tag: ["@UN-656248A7", "@VAL-25DA430F"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-25DA430F - Repeated pipeline issues - quality validation",
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
          await stubPhoneHomeValRoutes(ctx.page);
          await ctx.page.goto("/admin/knowledge?tab=validation-lab");
          await expect(
            ctx.page.getByTestId("validation-lab-page"),
          ).toBeVisible({ timeout: 15_000 });
          await ctx.page.getByTestId("validation-lab-mode-clinical").click();
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-panel"),
          ).toBeVisible({ timeout: 10_000 });

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Validation Lab investigate path is open.",
          });
          ctx.lastCompletedStep.value = 0;

          const list = ctx.page.getByTestId("validation-lab-ncr-list");
          await expect(list).toBeVisible();
          await expect(list.getByText(DIGEST_TITLE)).toHaveCount(1);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "One open coding-family phone-home record is shown.",
          });
          ctx.lastCompletedStep.value = 1;

          await expect(list.getByText(ESCALATE_TITLE)).toHaveCount(1);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Escalate phone-home record is present.",
          });
          ctx.lastCompletedStep.value = 2;

          const listText = (await list.innerText()).toLowerCase();
          expect(listText).not.toMatch(/\d{6,}/);
          expect(listText).not.toMatch(/\bnhs\b/);
          expect(listText).not.toMatch(/\bpatient\b/);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "List text has no patient identifiers.",
          });
          ctx.lastCompletedStep.value = 3;

          await list.getByText(DIGEST_TITLE).click();
          await expect(
            ctx.page.getByTestId("validation-lab-ncr-linked"),
          ).toContainText(DIGEST_TITLE);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes: "Linked phone-home quality record has a redacted title.",
          });
          ctx.lastCompletedStep.value = 4;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Phone-home quality records are one per family, escalate is present, and titles are redacted.",
          );
        },
      });
    },
  );
});
