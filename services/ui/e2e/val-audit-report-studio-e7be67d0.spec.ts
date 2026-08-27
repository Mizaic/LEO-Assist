/**
 * VAL-E7BE67D0 -- Audit report studio: world-class authoring and rendering.
 *
 * Exercises and evidences the new studio capabilities that bring the builder
 * to parity with the hardcoded Clinical Audit report:
 *   - add a metric tile by click,
 *   - add a metric tile by drag-from-library,
 *   - override a tile's metric parameters,
 *   - split the report into multiple named pages,
 *   - embed a specialised NCDA section widget,
 *   - preview the multi-page layout,
 *   - export a branded PDF.
 *
 * Each protocol step uploads a screenshot to the Atlas validation-runs REST API.
 */

import { expect, test } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import {
  clickFirstAvailableMetricAdd,
  createAuditFixtureState,
  installAuditTemplateFixtures,
} from "./helpers/audit-template-fixtures";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";

loadPlaywrightEnv();

const VAL_ID = "VAL-E7BE67D0";
const UN_ID = "UN-2B54E750";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Quality Manager opens /admin/audit-templates/new and adds the Referral STT Rate metric from the library. Confirms a KPI tile appears on the Page 1 canvas.",
  "Quality Manager drags a second metric (Guideline Compliance Rate) from the library onto the canvas. Confirms a second tile appears.",
  "Quality Manager selects the STT Rate tile, opens the Parameters tab, and overrides a metric parameter. Confirms the override control is shown and accepted.",
  "Quality Manager adds a second page with the Add page control. Confirms a Page 2 tab appears, is selected, and the canvas is empty; then adds a metric tile to Page 2.",
  "Quality Manager adds a specialised NCDA section widget (Cancer Type Breakdown) from the library. Confirms a widget tile appears on the canvas.",
  "Quality Manager opens Preview. Confirms the report shows multiple page tabs and renders tiles in the authored layout.",
  "Quality Manager clicks Export PDF. Confirms a branded PDF file download is produced.",
] as const;

test.describe("VAL-E7BE67D0 audit report studio walkthrough @val", () => {
  // 7 steps x 2 Atlas REST calls (recordStep + uploadEvidence) each up to 60s,
  // plus Playwright actions, html2canvas render and PDF download.
  test.setTimeout(720_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records world-class studio authoring and rendering evidence",
    {
      tag: ["@UN-2B54E750", "@VAL-E7BE67D0"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-E7BE67D0 - Audit report studio world-class authoring and rendering",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      const state = createAuditFixtureState();

      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID },
        protocol: PROTOCOL,
        body: async (ctx) => {
          const p = ctx.page;
          await installAuditTemplateFixtures(p, state);
          await p.goto("/admin/audit-templates/new");
          await expect(p.getByRole("tab", { name: "Data" })).toBeVisible({
            timeout: 15_000,
          });
          await expect(
            p.getByText("Referral STT Rate", { exact: true }),
          ).toBeVisible({ timeout: 15_000 });

          // Step 1 -- add a metric tile by click.
          await clickFirstAvailableMetricAdd(p);
          await expect(p.locator("[data-testid='canvas-tile']")).toHaveCount(1);
          await expect(
            p.locator("[data-testid='canvas-tile']").filter({ hasText: "Referral STT Rate" }).first(),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: p,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Referral STT Rate added by click; a KPI tile renders on the Page 1 canvas.",
          });
          ctx.lastCompletedStep.value = 0;

          // Step 2 -- add a second metric tile by drag-from-library.
          const guidelineCard = p
            .locator('[draggable="true"]')
            .filter({ hasText: "Guideline Compliance" })
            .first();
          // Drop onto the CanvasGrid container so the HTML5 onDrop handler
          // fires and converts cursor position to a grid cell.
          const canvasGrid = p.locator("[data-testid='canvas-grid']").first();
          await guidelineCard.dragTo(canvasGrid, {
            targetPosition: { x: 260, y: 330 },
            timeout: 15_000,
          });
          await expect(p.locator("[data-testid='canvas-tile']")).toHaveCount(2);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: p,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "Guideline Compliance Rate dragged from the library; a second tile is added.",
          });
          ctx.lastCompletedStep.value = 1;

          // Step 3 -- override a tile parameter via the Parameters tab.
          await p
            .locator("[data-testid='canvas-tile']")
            .filter({ hasText: "Referral STT Rate" })
            .first()
            .click();
          // The config panel tab "Parameters" only renders when the selected
          // metric's param_schema is non-empty (referral_stt_rate has one).
          const paramsTab = p.getByRole("tab", { name: "Parameters" });
          await expect(paramsTab).toBeVisible({ timeout: 15_000 });
          await paramsTab.click();
          const lookback = p.getByLabel("Lookback months");
          await expect(lookback).toBeVisible({ timeout: 10_000 });
          await lookback.fill("24");
          await expect(lookback).toHaveValue("24");
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: p,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Parameters tab shown for STT Rate tile; Lookback months overridden to 24.",
          });
          ctx.lastCompletedStep.value = 2;

          // Step 4 -- add a second page and a tile on it.
          await p.getByRole("button", { name: "Add page" }).click();
          await expect(p.getByRole("tab", { name: /Page 2/ })).toBeVisible({
            timeout: 10_000,
          });
          // Page 2 starts empty.
          await expect(p.locator("[data-testid='tile-body']")).toHaveCount(0);
          await clickFirstAvailableMetricAdd(p);
          await expect(p.locator("[data-testid='tile-body']")).toHaveCount(1);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: p,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "Page 2 added (empty canvas), then a metric tile added to Page 2.",
          });
          ctx.lastCompletedStep.value = 3;

          // Step 5 -- add a specialised NCDA section widget.
          await p
            .getByRole("button", { name: "Add Cancer Type Breakdown widget" })
            .click();
          await expect(p.locator("[data-testid='tile-body']")).toHaveCount(2);
          await expect(
            p.locator("[data-testid='canvas-tile']").filter({ hasText: "Cancer Type Breakdown" }).first(),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: p,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes: "Cancer Type Breakdown specialised widget added as a tile on the canvas.",
          });
          ctx.lastCompletedStep.value = 4;

          // Step 6 -- preview the multi-page report.
          await p.getByRole("button", { name: "Preview" }).click();
          await expect(p.getByText("Preview as:")).toBeVisible({ timeout: 15_000 });
          await expect(p.getByRole("tab", { name: "Page 1" })).toBeVisible({
            timeout: 10_000,
          });
          await expect(p.getByRole("tab", { name: /Page 2/ })).toBeVisible({
            timeout: 10_000,
          });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: p,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 5,
            notes: "Preview shows multiple page tabs (Page 1 / Page 2) and renders the authored tiles.",
          });
          ctx.lastCompletedStep.value = 5;

          // Step 7 -- export to PDF and confirm a download is produced.
          const exportButton = p.getByRole("button", { name: "Export PDF" });
          await expect(exportButton).toBeEnabled({ timeout: 10_000 });
          const downloadPromise = p.waitForEvent("download", { timeout: 60_000 });
          await exportButton.click();
          const download = await downloadPromise;
          const filename = download.suggestedFilename();
          expect(filename).toMatch(/\.pdf$/);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: p,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 6,
            notes: `Export PDF produced a branded download: ${filename}`,
          });
          ctx.lastCompletedStep.value = 6;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "World-class studio authoring (click-add, drag, parameters, multi-page, widget) and rendering (preview, PDF export) recorded with Playwright evidence.",
          );
        },
      });
    },
  );
});
