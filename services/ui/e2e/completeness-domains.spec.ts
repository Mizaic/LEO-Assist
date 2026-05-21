/**
 * VT-734E8B96 / VT-A32E2016 -- completeness domain configuration UI.
 *
 * Verifies an administrator can add required completeness criteria, preview a
 * sample SNOMED fact set, and save the schema through the domains settings UI.
 * Backend calls are stubbed so the spec is deterministic.
 */

import { expect, test, type Page, type Route } from "@playwright/test";

const DOMAIN_ID = "test_domain";
const SUBDOMAIN = "breast";

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
      user: {
        email: "e2e@example.com",
        name: "E2E Platform Admin",
      },
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

test.describe("completeness domain configuration", () => {
  test("administrator previews and saves completeness criteria", async ({ page }) => {
    let saveCalls = 0;
    let lastSavedBody: unknown = null;

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

    await page.route(
      `**/api/proxy/analytics/domains/${DOMAIN_ID}`,
      (route) => fulfillJson(route, domainDetailPayload()),
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
        const missing = group.concept_ids.filter(
          (id) => !body.concept_ids.includes(id),
        );
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
        lastSavedBody = route.request().postDataJSON();
        return fulfillJson(route, lastSavedBody);
      },
    );

    await page.goto(`/settings/domains/${DOMAIN_ID}`);
    await expect(page.getByText("Breast referral completeness")).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("button", { name: `Configure ${SUBDOMAIN}` }).click();
    await expect(
      page.getByRole("dialog", { name: "Configure: breast" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Add criterion" }).click();
    await page.getByLabel("Criterion name").click();
    await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
    await page.keyboard.type("Diagnosis present");
    await expect(page.getByLabel("Criterion name")).toHaveValue("Diagnosis present");
    await page.getByLabel("Specific SNOMED concepts").fill("breast");
    await page.getByRole("option", { name: /Breast cancer/ }).click();
    await page.getByLabel("Specific SNOMED concepts").fill("malignant");
    await page
      .getByRole("option", { name: /Malignant neoplastic disease/ })
      .click();
    await page.getByLabel("Semantic categories").last().click();
    await page.getByRole("option", { name: "disorder" }).click();

    await page.getByLabel("Sample patient fact IDs").fill("254837009");
    await page.getByRole("button", { name: "Preview criteria" }).click();
    await expect(page.getByText("Sample is missing required criteria.")).toBeVisible();
    await expect(page.getByText("Missing: Diagnosis present")).toBeVisible();

    await page.getByLabel("Sample patient fact IDs").fill("254837009, 363346000");
    await page.getByRole("button", { name: "Preview criteria" }).click();
    await expect(page.getByText("Sample meets the completeness criteria.")).toBeVisible();
    await expect(page.getByText("Matched: Diagnosis present")).toBeVisible();

    await page.getByRole("button", { name: "Save criteria" }).click();
    await expect.poll(() => saveCalls).toBe(1);
    expect(lastSavedBody).toEqual({
      groups: [
        {
          name: "Diagnosis present",
          required: true,
          semantic_categories: ["disorder"],
          concept_ids: [254837009, 363346000],
        },
      ],
    });
  });
});
