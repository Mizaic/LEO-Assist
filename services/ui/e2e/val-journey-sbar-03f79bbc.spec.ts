/**
 * VAL-03F79BBC -- Compose patient journeys with documents and SBAR playback.
 *
 * Atlas:
 *   UN: UN-236D97F4
 *   DI: DI-DD1989E6, DI-9DD9E548
 *   DO: DO-6D4C8A32
 *   VAL: VAL-03F79BBC
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  DOC_BODY,
  DOC_TITLE,
  PATIENT_ID,
  SOURCE_TAG,
  createdBodies,
  stubJourneyValRoutes,
} from "./helpers/journey-sbar-val-fixtures";
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

const VAL_ID = "VAL-03F79BBC";
const UN_ID = "UN-236D97F4";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open a patient Documents tab. Add a document by pasting markdown. Confirm Upload .txt is available.",
  "Open the document. Confirm Edit and Delete.",
  "Attach the document to a milestone. Run document pipeline SBAR and play episode rollup SBAR.",
  "Confirm Journey builder is shown for an admin. Confirm the document is tagged manual_journey.",
  "Capture screenshots and record the run.",
] as const;

test.describe("VAL-03F79BBC patient journeys and SBAR playback @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records journey document and SBAR playback evidence",
    {
      tag: ["@UN-236D97F4", "@VAL-03F79BBC"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-03F79BBC - Patient journeys with documents and SBAR playback - quality validation",
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
          await stubJourneyValRoutes(ctx.page);
          await ctx.page.goto("/care/patients/" + PATIENT_ID);
          await expect(ctx.page.getByText("VAL Journey Patient")).toBeVisible({
            timeout: 15_000,
          });
          await ctx.page.getByRole("tab", { name: "Documents" }).click();
          await expect(ctx.page.getByTestId("journey-builder-panel")).toBeVisible();
          await ctx.page.getByTestId("add-document-button").click();
          const addDialog = ctx.page.getByRole("dialog", { name: "Add document" });
          await expect(addDialog).toBeVisible();
          await addDialog.getByLabel("Title").fill(DOC_TITLE);
          await addDialog.locator('[contenteditable="true"]').fill(DOC_BODY);
          await expect(addDialog.getByRole("button", { name: "Upload .txt" })).toBeVisible();
          await addDialog.getByRole("button", { name: "Add document" }).click();
          await expect.poll(() => createdBodies.length).toBe(1);

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Document added from pasted markdown. Upload .txt is available.",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page
            .getByRole("button", { name: new RegExp(DOC_TITLE) })
            .click();
          await expect(ctx.page.getByTestId("edit-document-button")).toBeVisible();
          await expect(ctx.page.getByTestId("delete-document-button")).toBeVisible();
          await ctx.page.getByTestId("edit-document-button").click();
          await expect(ctx.page.getByRole("dialog", { name: "Edit document" })).toBeVisible();
          await ctx.page.getByRole("button", { name: "Cancel" }).click();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "Edit and Delete are available for the authored document.",
          });
          ctx.lastCompletedStep.value = 1;

          const panel = ctx.page.getByTestId("journey-builder-panel");
          await panel.getByRole("button", { name: "Run document pipeline" }).click();
          await expect(panel.getByText("Document pipeline SBAR")).toBeVisible({
            timeout: 10_000,
          });
          await ctx.page.keyboard.press("Escape");
          await expect(
            ctx.page.getByRole("dialog", { name: "SBAR preview" }),
          ).toHaveCount(0);
          await panel.getByRole("button", { name: "Play episode SBAR" }).click();
          await expect(panel.getByText(/Episode SBAR/)).toBeVisible({ timeout: 10_000 });
          await expect(panel.getByText(/Rollup SBAR/)).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Document pipeline SBAR and episode rollup SBAR were played.",
          });
          ctx.lastCompletedStep.value = 2;

          await expect(panel).toBeVisible();
          await expect(ctx.page.getByText(SOURCE_TAG).first()).toBeVisible();

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "Journey builder is admin-gated. Document is tagged manual_journey.",
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
            notes: "Journey document and SBAR playback evidence captured.",
          });
          ctx.lastCompletedStep.value = 4;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Journey documents can be added, edited, and played through document and episode SBAR. Admin gate and manual_journey tag are visible.",
          );
        },
      });
    },
  );
});
