/**
 * VAL-C73DD43E -- Customer pathway onboarding procedure (LEO-OP-001 v2.0).
 *
 * Walks through the five onboarding phases in the redesigned Knowledge hub
 * with stubbed backend routes and Playwright screenshot evidence.
 *
 * Procedure: compliance/policy/LEO-OP-001-customer-pathway-onboarding-procedure.md
 * Implements: DC-GOV-001 / DI-44D0E115
 */

import { expect, test, waitForPageSettled } from "./fixtures";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import {
  DOMAIN_ID,
  SUBDOMAIN,
  gotoKnowledgeTab,
  stubOnboardingRoutes,
} from "./helpers/onboarding-fixtures";
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

const VAL_ID = "VAL-C73DD43E";
const UN_ID = "UN-AF530E8E";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open /admin/knowledge. Confirm Knowledge sidebar shows NLP and AI, Clinical Knowledge, Data Setup, and Quality sections.",
  "Phase 1: Open Terminology tab. Confirm terminology packages are listed (platform readiness).",
  "Phase 2a: Open Surface Forms tab. Confirm grouped surface form list loads without error.",
  "Phase 2b: Open Clinical Guidelines tab. Confirm StatHero tiles and jump strip (1. Load / 2. Inspect / 3. Review / 4. Compile).",
  "Phase 3a: Open Domains tab. Confirm StatHero area counts and domain cards load.",
  "Phase 3b: Open domain detail. Click Configure on subdomain. Confirm split panel with Overview / Concepts / Rules tabs.",
  "Phase 3c: Rules tab shows completeness criteria groups for the subdomain.",
  "Phase 4: Open Validation Lab > Run baseline tests. Confirm saved gold cases load.",
] as const;

test.describe("VAL-C73DD43E customer pathway onboarding @val", () => {
  test.setTimeout(480_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records five-phase onboarding evidence in Knowledge hub",
    {
      tag: ["@UN-AF530E8E", "@UN-3B25A20E", "@VAL-C73DD43E", "@LEO-OP-001"],
      annotation: [
        {
          type: "Atlas VAL",
          description: "VAL-C73DD43E - Customer pathway onboarding procedure",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID, procedure: "LEO-OP-001" },
        protocol: PROTOCOL,
        body: async (ctx) => {
          await stubOnboardingRoutes(ctx.page);

          // Step 0: Knowledge hub shell
          await gotoKnowledgeTab(ctx.page, "terminology");
          const sidebar = ctx.page.getByTestId("knowledge-sidebar");
          await expect(sidebar.getByText("NLP & AI")).toBeVisible({ timeout: 10_000 });
          await expect(sidebar.getByText("Clinical Knowledge")).toBeVisible();
          await expect(sidebar.getByText("Data Setup")).toBeVisible();
          await expect(sidebar.getByText("Quality")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 0,
            notes: "Knowledge sidebar shows all four section groups.",
          });
          ctx.lastCompletedStep.value = 0;

          // Step 1: Phase 1 terminology
          await expect(ctx.page.getByText("Package status")).toBeVisible({ timeout: 10_000 });
          await expect(
            ctx.page.getByText(/SNOMED CT UK Edition/i),
          ).toBeVisible({ timeout: 10_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 1,
            notes: "Terminology packages visible -- platform readiness confirmed.",
          });
          ctx.lastCompletedStep.value = 1;

          // Step 2: Phase 2a surface forms
          await gotoKnowledgeTab(ctx.page, "surface-forms");
          await expect(ctx.page.getByTestId("phrase-mappings-chrome")).toBeVisible({
            timeout: 15_000,
          });
          await ctx.page.getByTestId("segmented-tab-live").click();
          await expect(
            ctx.page.getByText("T2DM", { exact: true }),
          ).toBeVisible({ timeout: 10_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 2,
            notes: "Surface forms tab loaded with approved alias group.",
          });
          ctx.lastCompletedStep.value = 2;

          // Step 3: Phase 2b clinical guidelines
          await gotoKnowledgeTab(ctx.page, "clinical-guidelines");
          await ctx.page
            .getByRole("button", {
              name: /skip the guideline builder intro animation/i,
            })
            .click({ timeout: 3_000 })
            .catch(() => undefined);
          await expect(ctx.page.getByTestId("metric-tile-loaded")).toBeVisible({
            timeout: 10_000,
          });
          await expect(ctx.page.getByText("1. Load")).toBeVisible();
          await expect(ctx.page.getByText("2. Inspect")).toBeVisible();
          await expect(ctx.page.getByText("3. Review")).toBeVisible();
          await expect(ctx.page.getByText("4. Compile")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 3,
            notes: "Clinical Guidelines StatHero and jump strip visible.",
          });
          ctx.lastCompletedStep.value = 3;

          // Step 4: Phase 3a domains list
          await gotoKnowledgeTab(ctx.page, "domains");
          await expect(ctx.page.getByText("Areas", { exact: true })).toBeVisible({
            timeout: 10_000,
          });
          await expect(ctx.page.getByTestId("domains-grid")).toBeVisible();
          await expect(ctx.page.getByText("Cancer referrals")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 4,
            notes: "Domains StatHero and domain card visible.",
          });
          ctx.lastCompletedStep.value = 4;

          // Step 5: Phase 3b subdomain split panel
          await ctx.page.goto(`/settings/domains/${DOMAIN_ID}`);
          await waitForPageSettled(ctx.page);
          await expect(ctx.page.getByTestId("domain-hero")).toBeVisible({ timeout: 10_000 });
          await ctx.page.getByRole("button", { name: `Configure ${SUBDOMAIN}` }).click();
          await expect(ctx.page.getByRole("tab", { name: "Overview" })).toBeVisible({
            timeout: 10_000,
          });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 5,
            notes: "Subdomain split panel opened with Overview tab.",
          });
          ctx.lastCompletedStep.value = 5;

          // Step 6: Phase 3c rules tab
          await ctx.page.getByRole("tab", { name: "Rules" }).click();
          await expect(
            ctx.page.getByRole("textbox", { name: "Rule 1 name" }),
          ).toHaveValue("Diagnosis present", { timeout: 5_000 });
          await expect(ctx.page.getByText("Required")).toBeVisible();

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 6,
            notes: "Rules tab shows completeness criteria group 'Diagnosis present'.",
          });
          ctx.lastCompletedStep.value = 6;

          // Step 7: Phase 4 Validation Lab saved gold cases
          await gotoKnowledgeTab(ctx.page, "validation-lab");
          await expect(ctx.page.getByTestId("validation-lab-page")).toBeVisible({
            timeout: 15_000,
          });
          await ctx.page.getByTestId("validation-lab-mode-saved").click();
          await expect(ctx.page.getByTestId("validation-lab-rolodex")).toBeVisible({
            timeout: 15_000,
          });
          await expect(
            ctx.page.getByText("Onboarding baseline case", { exact: true }),
          ).toBeVisible({ timeout: 10_000 });

          await recordProtocolStep({
            request: ctx.request, runId: ctx.runId, valId: ctx.valId,
            page: ctx.page, testInfo: ctx.testInfo, protocol: ctx.protocol, stepIndex: 7,
            notes: "Validation Lab saved gold cases list loads with completed baseline case.",
          });
          ctx.lastCompletedStep.value = 7;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Eight-phase onboarding walkthrough recorded with Playwright evidence (LEO-OP-001 v2.0).",
          );
        },
      });
    },
  );
});
