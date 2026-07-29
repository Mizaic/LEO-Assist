/**
 * Fixtures and API stubs for NG12 1.5.5 rule-build walkthrough.
 */
import type { Page } from "@playwright/test";
import type { SearchHit } from "./ng12-walkthrough-actions";

export const REC_TEXT =
  "1.5.5 Carry out appropriate tests for ovarian cancer (see recommendations " +
  "1.5.6 to 1.5.9) in any woman, or trans man or non-binary person with " +
  "female reproductive organs who is aged 50 or over and who has " +
  "experienced symptoms within the last 12 months that suggest irritable " +
  "bowel syndrome (IBS), because IBS rarely presents for the first time " +
  "at this age. (See NICE's guideline on irritable bowel syndrome in " +
  "adults .) [2011]";

export const IBS_ROW =
  "symptoms within the last 12 months that suggest irritable bowel syndrome (IBS)";

export const SEARCH_HITS: Record<string, SearchHit[]> = {
  "irritable bowel": [
    {
      snomed_concept_id: "10743008",
      term: "Irritable bowel syndrome",
      semantic_tag: "disorder",
    },
  ],
  "irritable bowel syndrome": [
    {
      snomed_concept_id: "10743008",
      term: "Irritable bowel syndrome",
      semantic_tag: "disorder",
    },
  ],
  symptoms: [
    {
      snomed_concept_id: "10743008",
      term: "Irritable bowel syndrome",
      semantic_tag: "disorder",
    },
  ],
  "ovarian cancer": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
  "ovarian cancer screening": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
  "appropriate tests": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
};

export const RULE = {
  rule_id: "e2e-ng12-1-5-5-walkthrough",
  name: "NG12 1.5.5 -- ovarian tests / IBS symptoms (walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Offer ovarian cancer tests when IBS-like symptoms appear at age 50+.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: {
    node_id: "root",
    kind: "AND",
    children: [
      {
        node_id: "age",
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: "50",
        unit: "years",
      },
      {
        node_id: "sex",
        kind: "DEMOGRAPHIC",
        field: "sex",
        operator: "=",
        value: "female",
      },
    ],
  },
  action: {
    snomed_concept_id: "",
    preferred_term: "",
    semantic_tag: "procedure",
  },
  has_predecessor: false,
  updated_at: "2026-07-01T09:00:00Z",
};

export type DecisionBody = {
  action?: string;
  updates?: {
    priority?: string;
    due_days?: number | null;
    actions?: Array<{
      strength?: string;
      criterion?: { snomed_concept_id?: string };
    }>;
    logic_tree?: Record<string, unknown>;
  };
};

export async function installFixtures(
  page: Page,
  captured: { decision: DecisionBody | null },
) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([RULE]),
    }),
  );
  for (const status of ["active", "superseded", "rejected"]) {
    await page.route(`**/api/guidance/rules/review*status=${status}*`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      }),
    );
  }
  await page.route("**/api/guidance/rules/review/*/decision", async (route) => {
    const raw = route.request().postData();
    captured.decision = raw ? (JSON.parse(raw) as DecisionBody) : null;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rule_id: `${RULE.rule_id}:edited` }),
    });
  });
  await page.route("**/api/terminology/prior-resolutions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/terminology/descendants*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const hits =
      SEARCH_HITS[q] ??
      Object.entries(SEARCH_HITS).find(([k]) => q.includes(k) || k.includes(q))?.[1] ??
      [];
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(hits),
    });
  });
  await page.route("**/api/nice/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
}
