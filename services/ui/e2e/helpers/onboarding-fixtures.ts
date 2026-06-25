/**
 * Shared Playwright fixtures for LEO-OP-001 customer pathway onboarding VAL.
 */

import { type Page } from "@playwright/test";
import {
  buildGroupedSurfaceFormsPayload,
  fulfillJson,
  stubKnowledgeAdminAuth,
} from "./surface-forms-fixtures";

export const DOMAIN_ID = "onboard_domain";
export const SUBDOMAIN = "lower_gi";
export const SCENARIO_RUN_ID = "run-onboard-001";

export function domainListPayload() {
  return [
    {
      id: DOMAIN_ID,
      name: "Cancer referrals",
      description: "Customer pathway onboarding test domain",
      subdomain_count: 1,
      source: "tenant",
      episode_detector: false,
    },
  ];
}

export function domainDetailPayload() {
  return {
    id: DOMAIN_ID,
    name: "Cancer referrals",
    description: "Customer pathway onboarding test domain",
    subdomain_count: 1,
    source: "tenant",
    episode_detector: false,
    subdomains: [
      {
        name: SUBDOMAIN,
        description: "Lower GI referral completeness",
        milestone_type: "referral",
        time_window_months: 12,
        semantic_tags: ["disorder"],
        assertion_filter: [],
        constructs: [],
        completeness_schema: [
          {
            name: "Diagnosis present",
            required: true,
            concept_ids: [254837009],
            semantic_categories: ["disorder"],
          },
        ],
        construct_count: 0,
        concept_count: 1,
        descendant_count: 0,
      },
    ],
  };
}

export function subdomainDetailPayload() {
  return {
    name: SUBDOMAIN,
    description: "Lower GI referral completeness",
    milestone_type: "referral",
    time_window_months: 12,
    semantic_tags: ["disorder"],
    assertion_filter: [],
    constructs: [],
    completeness_schema: [
      {
        name: "Diagnosis present",
        required: true,
        concept_ids: [254837009],
        semantic_categories: ["disorder"],
      },
    ],
    construct_count: 0,
    concept_count: 1,
    descendant_count: 0,
    concepts: [
      {
        concept_id: 254837009,
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

export async function stubOnboardingRoutes(page: Page) {
  await stubKnowledgeAdminAuth(page);

  await page.route("**/api/admin/terminology/status", (route) =>
    fulfillJson(route, {
      packages: {
        snomed: {
          label: "SNOMED CT UK Edition",
          local_version: "20260301",
          trud_version: "20260301",
          trud_date: "2026-03-01",
          trud_size_mb: 1200,
          up_to_date: true,
        },
        dmd: {
          label: "dm+d",
          local_version: "20260301",
          trud_version: "20260301",
          trud_date: "2026-03-01",
          trud_size_mb: 400,
          up_to_date: true,
        },
        icd10: {
          label: "ICD-10",
          local_version: "2026",
          trud_version: "2026",
          trud_date: "2026-01-01",
          trud_size_mb: 80,
          up_to_date: true,
        },
        opcs4: {
          label: "OPCS-4",
          local_version: "2026",
          trud_version: "2026",
          trud_date: "2026-01-01",
          trud_size_mb: 40,
          up_to_date: true,
        },
      },
      neo4j: {
        active_concepts: 350000,
        terms: 900000,
        is_a_rels: 1200000,
        icd10_codes: 50000,
        icd10_maps: 40000,
        opcs4_codes: 10000,
        opcs4_maps: 8000,
        read_maps: 200000,
      },
    }),
  );

  await page.route("**/api/nice/loaded", (route) =>
    fulfillJson(route, [
      {
        code: "NG12",
        title: "Suspected cancer: recognition and referral",
        guidance_type: "NG",
        publication_date: "2023-07-01",
        chapter_count: 4,
        recommendation_count: 14,
        rules_pending: 0,
        rules_approved: 12,
        rules_rejected: 0,
      },
    ]),
  );

  await page.route("**/api/terminology/guidelines/bitmap/status*", (route) =>
    fulfillJson(route, {
      active_version: "v20260625-120000",
      rule_count: 12,
      compile_timestamp: "2026-06-25T12:00:00Z",
    }),
  );

  await page.route("**/api/terminology/surface-forms/grouped*", (route) =>
    fulfillJson(route, buildGroupedSurfaceFormsPayload("approved")),
  );

  await page.route("**/api/proxy/analytics/domains", (route) => {
    if (route.request().method() === "GET") {
      return fulfillJson(route, domainListPayload());
    }
    return route.continue();
  });

  await page.route(`**/api/proxy/analytics/domains/${DOMAIN_ID}`, (route) =>
    fulfillJson(route, domainDetailPayload()),
  );

  await page.route(
    `**/api/proxy/analytics/domains/${DOMAIN_ID}/subdomains/${SUBDOMAIN}`,
    (route) => fulfillJson(route, subdomainDetailPayload()),
  );

  await page.route("**/api/terminology/semantic-tags", (route) =>
    fulfillJson(route, ["disorder", "finding", "observable_entity"]),
  );

  await page.route("**/api/sbar/scenario-runs/scenarios*", (route) =>
    fulfillJson(route, { cases: [], total: 0 }),
  );

  await page.route("**/api/sbar/scenario-runs", (route) => {
    if (route.request().method() === "GET") {
      return fulfillJson(route, {
        runs: [
          {
            run_id: SCENARIO_RUN_ID,
            status: "completed",
            case_ids: ["case-onboard-1"],
            child_runs: {},
            guideline_id: "NG12",
            completeness_domain: DOMAIN_ID,
            completeness_subdomain: SUBDOMAIN,
            completed_count: 1,
            failed_count: 0,
            running_count: 0,
            case_count: 1,
            triggered_at: "2026-06-25T14:00:00Z",
            completed_at: "2026-06-25T14:00:00Z",
          },
        ],
      });
    }
    return route.continue();
  });
}

export async function gotoKnowledgeTab(page: Page, tab: string) {
  await page.goto(`/admin/knowledge?tab=${tab}`);
  await page.waitForLoadState("networkidle");
}
