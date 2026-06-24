/**
 * VAL-4D70E63C -- administrator-configured minimum dataset completeness domains.
 *
 * Records Atlas validation execution runs with Playwright screencapture for
 * the completeness domain configuration journey (stubbed backend).
 */

import { expect, test, type Page, type Route } from "@playwright/test";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
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
const DOMAIN_ID = "test_domain";
const SUBDOMAIN = "breast";

const PROTOCOL = [
  "Open Settings > Domains and create or select a domain intended to hold minimum dataset completeness criteria.",
  "Create or select a subdomain representing the healthcare service to validate.",
  "Open the subdomain configuration dialog and add at least one required completeness criterion.",
  "Select specific SNOMED concepts through the SNOMED lookup and select one or more semantic categories from the dropdown.",
  "Preview the criteria against a sample patient fact set and confirm missing and matched criteria are reported clearly.",
  "Save the criteria and return to the domain view.",
  "Confirm the domain or subdomain is shown as a minimum dataset/completeness domain in the UI.",
] as const;

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function stubAuth(page: Page) {
  await page.route("**/auth/session", (route) =>
    fulfillJson(route, {
      user: { email: "e2e@example.com", name: "E2E Platform Admin" },
      isPlatformAdmin: true,
      organizations: [],
      idleTimeoutMinutes: 30,
      selected_role: "platform_admin",
      allowed_roles: ["platform_admin", "developer"],
      needs_role_choice: false,
    }),
  );
}

function domainDetailPayload() {
  return {
    id: DOMAIN_ID,
    name: "Test domain",
    description: "Completeness test domain",
    subdomain_count: 1,
    source: "tenant",
    episode_detector: false,
    subdomains: [
      {
        name: SUBDOMAIN,
        description: "Breast referral completeness",
        milestone_type: "diagnosis",
        time_window_months: null,
        semantic_tags: ["disorder"],
        assertion_filter: [],
        constructs: [],
        completeness_schema: [],
        construct_count: 0,
        concept_count: 2,
        descendant_count: 0,
      },
    ],
  };
}

function subdomainDetailPayload() {
  return {
    name: SUBDOMAIN,
    description: "Breast referral completeness",
    milestone_type: "diagnosis",
    time_window_months: null,
    semantic_tags: ["disorder"],
    assertion_filter: [],
    constructs: [],
    completeness_schema: [],
    construct_count: 0,
    concept_count: 2,
    descendant_count: 0,
    concepts: [
      {
        concept_id: 254837009,
        term: "Breast cancer",
        preferred_term: "Breast cancer",
        semantic_tag: "disorder",
        subdomain: SUBDOMAIN,
        guideline_synonyms: [],
        child_count: 0,
      },
      {
        concept_id: 363346000,
        term: "Malignant neoplastic disease",
        preferred_term: "Malignant neoplastic disease",
        semantic_tag: "disorder",
        subdomain: SUBDOMAIN,
        guideline_synonyms: [],
        child_count: 0,
      },
    ],
  };
}

async function stubCompletenessRoutes(page: Page) {
  let saveCalls = 0;

  await stubAuth(page);
  await page.route("**/api/terminology/semantic-tags", (route) =>
    fulfillJson(route, ["disorder", "finding", "observable_entity"]),
  );
  await page.route("**/api/terminology/search?**", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const hits = [
      {
        snomed_concept_id: "254837009",
        term: "Breast cancer",
        semantic_tag: "disorder",
      },
      {
        snomed_concept_id: "363346000",
        term: "Malignant neoplastic disease",
        semantic_tag: "disorder",
      },
    ].filter((hit) => hit.term.toLowerCase().includes(q));
    return fulfillJson(route, hits);
  });
  await page.route(`**/api/proxy/analytics/domains/${DOMAIN_ID}`, (route) =>
    fulfillJson(route, domainDetailPayload()),
  );
  await page.route(
    `**/api/proxy/analytics/domains/${DOMAIN_ID}/subdomains/${SUBDOMAIN}`,
    (route) => fulfillJson(route, subdomainDetailPayload()),
  );
  await page.route(
    `**/api/proxy/analytics/domains/${DOMAIN_ID}/subdomains/${SUBDOMAIN}/schema/preview`,
    async (route) => {
      const body = route.request().postDataJSON() as {
        concept_ids: number[];
        schema: { groups: Array<{ name: string; concept_ids: number[] }> };
      };
      const group = body.schema.groups[0];
      const missing = group.concept_ids.filter((id) => !body.concept_ids.includes(id));
      return fulfillJson(route, {
        matched_groups:
          missing.length === 0
            ? [
                {
                  name: group.name,
                  required: true,
                  matched: true,
                  matched_concept_ids: group.concept_ids,
                  missing_concept_ids: [],
                },
              ]
            : [],
        missing_groups:
          missing.length > 0
            ? [
                {
                  name: group.name,
                  required: true,
                  matched: false,
                  matched_concept_ids: group.concept_ids.filter((id) =>
                    body.concept_ids.includes(id),
                  ),
                  missing_concept_ids: missing,
                },
              ]
            : [],
        complete: missing.length === 0,
      });
    },
  );
  await page.route(
    `**/api/proxy/analytics/domains/${DOMAIN_ID}/subdomains/${SUBDOMAIN}/schema`,
    async (route) => {
      saveCalls += 1;
      return fulfillJson(route, route.request().postDataJSON());
    },
  );

  return { getSaveCalls: () => saveCalls };
}

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
          const counters = await stubCompletenessRoutes(ctx.page);
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
            notes: "Domain settings page opened for test domain.",
          });
          ctx.lastCompletedStep.value = 0;

          await ctx.page.getByRole("button", { name: `Configure ${SUBDOMAIN}` }).click();
          await expect(
            ctx.page.getByRole("dialog", { name: "Configure: breast" }),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 1,
            notes: "Subdomain configuration dialog opened.",
          });
          ctx.lastCompletedStep.value = 1;

          await ctx.page.getByRole("button", { name: "Add criterion" }).click();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 2,
            notes: "Required completeness criterion row added.",
          });
          ctx.lastCompletedStep.value = 2;

          await ctx.page.getByLabel("Criterion name").click();
          await ctx.page.keyboard.press(
            process.platform === "darwin" ? "Meta+A" : "Control+A",
          );
          await ctx.page.keyboard.type("Diagnosis present");
          await ctx.page.getByLabel("Specific SNOMED concepts").fill("breast");
          await ctx.page.getByRole("option", { name: /Breast cancer/ }).click();
          await ctx.page.getByLabel("Specific SNOMED concepts").fill("malignant");
          await ctx.page
            .getByRole("option", { name: /Malignant neoplastic disease/ })
            .click();
          await ctx.page.getByLabel("Semantic categories").last().click();
          await ctx.page.getByRole("option", { name: "disorder" }).click();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 3,
            notes: "SNOMED concepts and semantic category selected.",
          });
          ctx.lastCompletedStep.value = 3;

          await ctx.page.getByLabel("Sample patient fact IDs").fill("254837009");
          await ctx.page.getByRole("button", { name: "Preview criteria" }).click();
          await expect(
            ctx.page.getByText("Sample is missing required criteria."),
          ).toBeVisible();
          await ctx.page
            .getByLabel("Sample patient fact IDs")
            .fill("254837009, 363346000");
          await ctx.page.getByRole("button", { name: "Preview criteria" }).click();
          await expect(
            ctx.page.getByText("Sample meets the completeness criteria."),
          ).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 4,
            notes: "Preview reported missing then matched criteria.",
          });
          ctx.lastCompletedStep.value = 4;

          await ctx.page.getByRole("button", { name: "Save criteria" }).click();
          await expect.poll(counters.getSaveCalls).toBe(1);
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 5,
            notes: "Completeness criteria saved through admin UI.",
          });
          ctx.lastCompletedStep.value = 5;

          await expect(ctx.page.getByText("Breast referral completeness")).toBeVisible();
          await recordProtocolStep({
            request: ctx.request,
            runId: ctx.runId,
            valId: ctx.valId,
            page: ctx.page,
            testInfo: ctx.testInfo,
            protocol: ctx.protocol,
            stepIndex: 6,
            notes: "Domain view shows configured breast subdomain.",
          });
          ctx.lastCompletedStep.value = 6;

          await finishValPass(
            ctx.request,
            ctx.runId,
            "Completeness domain configuration journey recorded with step evidence.",
          );
        },
      });
    },
  );
});
