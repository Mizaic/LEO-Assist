/**
 * VAL-4D70E63C -- administrator-configured minimum dataset completeness domains.
 *
 * Validates the split-panel subdomain UI (Overview / Concepts / Rules).
 * Backend calls are stubbed so the spec is deterministic.
 */

import { expect, test } from "@playwright/test";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import {
  DOMAIN_ID,
  SUBDOMAIN,
  openSubdomainPanel,
  stubCompletenessDomainRoutes,
} from "./helpers/completeness-domains-fixtures";
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

const VAL_ID = "VAL-4D70E63C";
const UN_ID = "UN-3B25A20E";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const PROTOCOL = [
  "Open Settings > Domains and select a domain intended to hold minimum dataset completeness criteria.",
  "Open the subdomain configuration split panel via Configure.",
  "Overview tab: confirm subdomain description and milestone settings are visible.",
  "Concepts tab: confirm configured SNOMED concepts are listed.",
  "Rules tab: confirm completeness criteria groups show required labels and SNOMED concept IDs.",
  "Close the split panel and confirm the subdomain card remains on the domain view.",
  "Confirm the domain detail hero shows the selected clinical area.",
] as const;

test.describe("VAL-4D70E63C completeness domains @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
  });

  test(
    "records completeness configuration evidence",
    {
      tag: ["@UN-3B25A20E", "@VAL-4D70E63C"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-4D70E63C - Administrator-configured minimum dataset completeness domains",
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
          await stubCompletenessDomainRoutes(ctx.page);
          await ctx.page.goto(`/settings/domains/${DOMAIN_ID}`);
          await expect(ctx.page.getByText("Breast referral completeness")).toBeVisible({
            timeout: 15_000,
          });

          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 0,
            notes: "Domain detail page opened for test domain with breast subdomain.",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page.getByRole("button", { name: `Configure ${SUBDOMAIN}` }).click();
          await expect(ctx.page.getByRole("tab", { name: "Overview" })).toBeVisible({
            timeout: 10_000,
          });
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "Subdomain split panel opened from Configure control.",
          });
          ctx.lastCompletedStep.value = 1;

          await expect(ctx.page.getByLabel("Description")).toHaveValue(
            "Breast referral completeness",
          );
          await expect(ctx.page.getByLabel("Milestone type")).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Overview tab shows subdomain description and milestone controls.",
          });
          ctx.lastCompletedStep.value = 2;

          await ctx.page.getByRole("tab", { name: "Concepts" }).click();
          await expect(ctx.page.getByText("Breast cancer")).toBeVisible({ timeout: 5_000 });
          await expect(ctx.page.getByText("Malignant neoplastic disease")).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "Concepts tab lists configured SNOMED concepts for the subdomain.",
          });
          ctx.lastCompletedStep.value = 3;

          await ctx.page.getByRole("tab", { name: "Rules" }).click();
          await expect(ctx.page.getByText("Diagnosis present")).toBeVisible({ timeout: 5_000 });
          await expect(ctx.page.getByText("Required")).toBeVisible();
          await expect(ctx.page.getByText("254837009, 363346000")).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes: "Rules tab shows required completeness group with SNOMED concept IDs.",
          });
          ctx.lastCompletedStep.value = 4;

          await ctx.page.getByRole("button", { name: "Close panel" }).click();
          await expect(ctx.page.getByText("Breast referral completeness")).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 5,
            notes: "Split panel closed; subdomain card remains on domain view.",
          });
          ctx.lastCompletedStep.value = 5;

          await expect(ctx.page.getByTestId("domain-hero")).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 6,
            notes: "Domain detail hero confirms clinical area context.",
          });
          ctx.lastCompletedStep.value = 6;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Completeness domain split-panel journey recorded with step evidence.",
          );
        },
      });
    },
  );
});
