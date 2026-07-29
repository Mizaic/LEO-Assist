/**
 * Fixtures and API stubs for NG12 1.7.2 Ask LEO walkthrough.
 */
import type { Page } from "@playwright/test";
import type { SearchHit } from "./ng12-walkthrough-actions";

export const REC_TEXT =
  "1.7.2 Refer people using a suspected cancer pathway referral if " +
  "dermoscopy suggests melanoma of the skin. [2015]";

export const CLINICAL_ROW = "dermoscopy suggests melanoma of the skin";

export const ASK_LEO_TERMS = [
  "melanoma of skin",
  "suspected melanoma",
  "dermoscopy of skin",
] as const;

export const SEARCH_HITS: Record<string, SearchHit[]> = {
  "melanoma of skin": [
    {
      snomed_concept_id: "372244006",
      term: "Malignant melanoma of skin",
      semantic_tag: "disorder",
    },
  ],
  "suspected melanoma": [
    {
      snomed_concept_id: "313299006",
      term: "Suspected melanoma of skin",
      semantic_tag: "situation",
    },
  ],
  "dermoscopy of skin": [
    {
      snomed_concept_id: "241077003",
      term: "Dermatoscopy of skin",
      semantic_tag: "procedure",
    },
  ],
  melanoma: [
    {
      snomed_concept_id: "276281000000104",
      term: "Fast track referral for suspected skin cancer",
      semantic_tag: "procedure",
    },
  ],
  "skin cancer": [
    {
      snomed_concept_id: "276281000000104",
      term: "Fast track referral for suspected skin cancer",
      semantic_tag: "procedure",
    },
  ],
  "fast track referral": [
    {
      snomed_concept_id: "276281000000104",
      term: "Fast track referral for suspected skin cancer",
      semantic_tag: "procedure",
    },
  ],
};

export const RULE = {
  rule_id: "e2e-ng12-1-7-2-walkthrough",
  name: "NG12 1.7.2 -- dermoscopy suggests melanoma (Ask LEO walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Refer on a suspected cancer pathway when dermoscopy suggests melanoma.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: {
    node_id: "root",
    kind: "AND",
    children: [],
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
    logic_tree?: {
      kind?: string;
      children?: Array<{
        kind?: string;
        criterion?: { snomed_concept_id?: string; preferred_term?: string };
      }>;
    };
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
  // Vague dermoscopy phrase must miss so Ask LEO appears; resolved
  // Ask LEO terms and the referral action still hit SEARCH_HITS.
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    if (q.includes("dermoscopy suggests")) {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
      return;
    }
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
  await page.route("**/api/guidance/concepts/expand-topic", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        terms: [...ASK_LEO_TERMS],
        reason: "stubbed for NG12 1.7.2 Ask LEO walkthrough",
      }),
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
