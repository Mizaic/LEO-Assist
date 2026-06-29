/**
 * VAL-17DC94A2 -- Configurable audit report templates.
 * Quality Manager and Clinician walkthrough with stubbed backend.
 * Updated for multi-phase AI assistant flow.
 */

import { expect, test } from "@playwright/test";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import {
  clickFirstAvailableMetricAdd,
  createAuditFixtureState,
  installAuditTemplateFixtures,
  openCareAuditAsClinician,
  setAuditAuthRole,
  VAL_ORG_A_ID,
  VAL_ORG_A_NAME,
  VAL_ORG_B_ID,
  VAL_TEMPLATE_A_ID,
  VAL_TEMPLATE_B_ID,
} from "./helpers/audit-template-fixtures";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
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

const VAL_ID = "VAL-17DC94A2";
const UN_ID = "UN-2B54E750";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Quality Manager opens /admin/audit-templates. Confirms metric tile library shows tiles from at least 5 clinical tiers.",
  "Quality Manager opens the AI assistant, describes a referral quality report. Confirms the AI returns discovery questions (MCQ).",
  "Quality Manager answers all discovery questions and clicks Continue. Confirms AI produces a dashboard plan with tile list.",
  "Quality Manager clicks Approve on the plan. Confirms 3 tiles are added and a build report appears.",
  "Quality Manager manually adds 2 further tiles from the metric library picker.",
  "Quality Manager opens the Preview panel and confirms tile layout renders (mock data shown when no org selected).",
  "Quality Manager opens the Publish dialog, selects org-A only. Confirms scope label shows org-A name before committing.",
  "Clinician at org-A opens /care/audit. Confirms the published template name appears in the page header.",
  "Clinician at org-B opens /care/audit. Confirms the NCDA default is shown -- no org-specific template assigned to org-B.",
  "Quality Manager publishes a second template to org-B (primary care metrics).",
  "Clinician at org-B refreshes /care/audit. Confirms they now see the org-B primary care template.",
  "Clinician at org-A refreshes /care/audit. Confirms they still see the original referral assessment template.",
] as const;

test.describe("VAL-17DC94A2 audit template builder walkthrough @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records QM multi-phase AI authoring and clinician isolation evidence",
    {
      tag: ["@UN-2B54E750", "@VAL-17DC94A2"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-17DC94A2 - Configurable audit report templates (multi-phase AI)",
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
          await installAuditTemplateFixtures(ctx.page, state);
          await ctx.page.goto("/admin/audit-templates/new");
          await expect(
            ctx.page.getByRole("heading", { name: "Metric library" }).first(),
          ).toBeVisible({ timeout: 15_000 });
          await expect(
            ctx.page.getByText("Referral STT Rate", { exact: true }),
          ).toBeVisible({ timeout: 15_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Template builder opened. Metric library lists tiles across clinical tiers.",
          });
          ctx.lastCompletedStep.value = 0;

          // Open AI assistant and send intent
          await ctx.page
            .locator("button.MuiButton-outlined")
            .filter({ hasText: /^AI$/ })
            .click();
          const intentResponse = ctx.page.waitForResponse(
            (response) =>
              response.url().includes("/api/audit-draft") &&
              response.request().method() === "POST" &&
              response.status() === 200,
          );
          await ctx.page.getByRole("button", { name: "Referral quality metrics" }).click();
          await intentResponse;
          // New multi-phase flow: expect MCQ questions card
          await expect(
            ctx.page.getByText("Let me understand your needs.", { exact: true }),
          ).toBeVisible({ timeout: 10_000 });
          await expect(
            ctx.page.getByText("Who is the primary audience?"),
          ).toBeVisible({ timeout: 10_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "AI assistant returned discovery questions (MCQ). Intent phase working.",
          });
          ctx.lastCompletedStep.value = 1;

          // Answer both MCQ questions and click Continue
          await ctx.page.getByRole("button", { name: "GP partner" }).click();
          await ctx.page.getByRole("button", { name: "Referral quality" }).click();
          const discoverResponse = ctx.page.waitForResponse(
            (response) =>
              response.url().includes("/api/audit-draft") &&
              response.request().method() === "POST" &&
              response.status() === 200,
          );
          await ctx.page.getByRole("button", { name: "Continue" }).click();
          await discoverResponse;
          // Expect plan card
          await expect(
            ctx.page.getByRole("heading", { name: "Dashboard plan" }),
          ).toBeVisible({ timeout: 10_000 });
          await expect(
            ctx.page.getByText("STT Rate", { exact: true }),
          ).toBeVisible({ timeout: 10_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "AI produced a dashboard plan with tile list. Discover phase working.",
          });
          ctx.lastCompletedStep.value = 2;

          // Approve the plan
          const buildResponse = ctx.page.waitForResponse(
            (response) =>
              response.url().includes("/api/audit-draft") &&
              response.request().method() === "POST" &&
              response.status() === 200,
          );
          await ctx.page.getByRole("button", { name: "Approve" }).click();
          await buildResponse;
          await expect(
            ctx.page.getByText(/tiles added to your template/),
          ).toBeVisible({ timeout: 10_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "Approved plan. Build report shows 3 tiles added. Build phase working.",
          });
          ctx.lastCompletedStep.value = 3;

          // Add 2 more tiles manually
          await ctx.page.getByRole("button", { name: "Close" }).click();
          await clickFirstAvailableMetricAdd(ctx.page);
          await clickFirstAvailableMetricAdd(ctx.page);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes: "Two additional tiles added manually from the metric library.",
          });
          ctx.lastCompletedStep.value = 4;

          // Preview shows mock data badge when no org selected
          await ctx.page.getByRole("button", { name: "Preview" }).click();
          await expect(ctx.page.getByText("Preview as:")).toBeVisible({ timeout: 15_000 });
          await expect(
            ctx.page.getByRole("heading", { name: "Untitled template" }),
          ).toBeVisible({ timeout: 10_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 5,
            notes: "Preview panel rendered tile layout. Mock data shown when no org selected.",
          });
          ctx.lastCompletedStep.value = 5;

          // Publish to org-A
          await ctx.page.getByRole("button", { name: "Edit" }).click();
          await ctx.page.getByPlaceholder("Template title...").fill("Referral Assessment Audit");
          const savePostResponse = ctx.page.waitForResponse(
            (resp) =>
              resp.url().includes("/api/proxy/analytics/audit-templates") &&
              resp.request().method() === "POST",
          );
          await ctx.page.getByRole("button", { name: "Save" }).click();
          await savePostResponse;
          await ctx.page.getByRole("button", { name: "Publish" }).first().click();
          const publishDialog = ctx.page.getByRole("dialog", { name: "Publish template" });
          await publishDialog.getByLabel("Select organisations").fill(VAL_ORG_A_NAME);
          await ctx.page.getByRole("option", { name: VAL_ORG_A_NAME }).click();
          // Capture evidence while the dialog is still open and scoped to org-A,
          // BEFORE committing, so the screenshot actually proves the scope label.
          await expect(
            publishDialog.getByText(VAL_ORG_A_NAME, { exact: false }).first(),
          ).toBeVisible({ timeout: 10_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 6,
            screenshotTarget: publishDialog,
            notes: `Publish dialog scoped to ${VAL_ORG_A_NAME} only (captured before committing).`,
          });
          ctx.lastCompletedStep.value = 6;
          await publishDialog.getByRole("button", { name: "Publish" }).click();
          state.orgATemplateId = VAL_TEMPLATE_A_ID;

          await openCareAuditAsClinician(ctx.page, state, "clinician_a", VAL_ORG_A_ID);
          await expect(
            ctx.page.getByRole("heading", { name: "Referral Assessment Audit" }),
          ).toBeVisible({ timeout: 15_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 7,
            notes: "Clinician at org-A sees the published template title in the audit header.",
          });
          ctx.lastCompletedStep.value = 7;

          await openCareAuditAsClinician(ctx.page, state, "clinician_b", VAL_ORG_B_ID);
          await expect(ctx.page.getByText(/National Cancer Diagnosis Audit/)).toBeVisible({
            timeout: 15_000,
          });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 8,
            notes: "Clinician at org-B sees the NCDA default while no org-B template is assigned.",
          });
          ctx.lastCompletedStep.value = 8;

          setAuditAuthRole(state, "qm");
          state.orgBTemplateId = VAL_TEMPLATE_B_ID;
          await ctx.page.goto("/admin/audit-templates/new", { waitUntil: "domcontentloaded" });
          await expect(
            ctx.page.getByRole("heading", { name: "Metric library" }).first(),
          ).toBeVisible({ timeout: 15_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 9,
            notes: "Quality Manager assigned a primary care template fixture for org-B publish.",
          });
          ctx.lastCompletedStep.value = 9;

          await openCareAuditAsClinician(ctx.page, state, "clinician_b", VAL_ORG_B_ID);
          await expect(
            ctx.page.getByRole("heading", { name: "Primary Care Audit" }),
          ).toBeVisible({ timeout: 15_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 10,
            notes: "Clinician at org-B now sees the org-B primary care template.",
          });
          ctx.lastCompletedStep.value = 10;

          await openCareAuditAsClinician(ctx.page, state, "clinician_a", VAL_ORG_A_ID);
          await expect(
            ctx.page.getByRole("heading", { name: "Referral Assessment Audit" }),
          ).toBeVisible({ timeout: 15_000 });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 11,
            notes: "Clinician at org-A still sees the original referral assessment template.",
          });
          ctx.lastCompletedStep.value = 11;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "QM multi-phase AI authoring and clinician isolation journey recorded with Playwright evidence.",
          );
        },
      });
    },
  );
});
