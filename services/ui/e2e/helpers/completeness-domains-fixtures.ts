/**
 * Shared Playwright fixtures for completeness domain configuration tests.
 */

import { type Page } from "@playwright/test";
import { fulfillJson } from "./surface-forms-fixtures";

export const DOMAIN_ID = "test_domain";
export const SUBDOMAIN = "breast";

export function domainDetailPayload() {
  return {
    id: DOMAIN_ID,
    name: "Test domain",
    description: "Completeness test domain",
    subdomain_count: 1,
    source: "tenant",
    episode_detector: false,
    use_cases: ["completeness"],
    subdomains: [
      {
        name: SUBDOMAIN,
        description: "Breast referral completeness",
        milestone_type: "diagnosis",
        time_window_months: null,
        semantic_tags: ["disorder"],
        assertion_filter: [],
        constructs: [],
        use_cases: ["completeness", "episode_detection"],
        completeness_schema: [
          {
            name: "Diagnosis present",
            required: true,
            concept_ids: [254837009, 363346000],
            semantic_categories: ["disorder"],
          },
        ],
        construct_count: 0,
        concept_count: 2,
        descendant_count: 0,
      },
    ],
  };
}

export function subdomainDetailPayload() {
  return {
    name: SUBDOMAIN,
    description: "Breast referral completeness",
    milestone_type: "diagnosis",
    time_window_months: null,
    semantic_tags: ["disorder"],
    assertion_filter: [],
    constructs: [],
    use_cases: ["completeness", "episode_detection"],
    completeness_schema: [
      {
        name: "Diagnosis present",
        required: true,
        concept_ids: [254837009, 363346000],
        semantic_categories: ["disorder"],
      },
    ],
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

export async function stubCompletenessDomainRoutes(page: Page) {
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

  await page.route("**/api/terminology/semantic-tags", (route) =>
    fulfillJson(route, ["disorder", "finding", "observable_entity"]),
  );

  await page.route("**/api/proxy/analytics/domains/use-cases", (route) =>
    fulfillJson(route, [
      { value: "extraction", label: "Targeted extraction" },
      { value: "completeness", label: "Minimum dataset" },
      { value: "analytics", label: "Population health analytics" },
      { value: "episode_detection", label: "Episode detection" },
    ]),
  );

  await page.route("**/api/proxy/analytics/benchmarks/keys", (route) =>
    fulfillJson(route, ["prevalence_hypertension", "prevalence_diabetes", "qof_indicator_dm006"]),
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
    `**/api/proxy/analytics/domains/${DOMAIN_ID}/subdomains/${SUBDOMAIN}/schema`,
    (route) => {
      if (route.request().method() === "PUT") {
        return fulfillJson(route, { groups: [] });
      }
      return route.continue();
    },
  );
}

export async function openSubdomainPanel(page: Page) {
  await page.goto(`/settings/domains/${DOMAIN_ID}`);
  await page.getByRole("button", { name: `Configure ${SUBDOMAIN}` }).click();
}
