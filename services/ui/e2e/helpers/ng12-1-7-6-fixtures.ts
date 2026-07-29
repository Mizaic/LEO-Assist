/**
 * Fixtures and API stubs for NG12 1.7.6 Ask LEO walkthrough.
 */
import type { Page } from "@playwright/test";
import type { SearchHit } from "./ng12-walkthrough-actions";

export const REC_TEXT =
  "1.7.6 Only consider a suspected cancer pathway referral for people " +
  "with a skin lesion that raises the suspicion of a basal cell " +
  "carcinoma if there is particular concern that a delay may have a " +
  "significant impact, because of factors such as lesion site or size. [2015]";

export const BCC_ROW =
  "skin lesion that raises the suspicion of a basal cell carcinoma";
export const DELAY_ROW =
  "particular concern that a delay may have a significant impact";

export const BCC_TERMS = [
  "basal cell carcinoma of skin",
  "suspected basal cell carcinoma",
] as const;

export const DELAY_TERMS = [
  "delay in treatment may be harmful",
  "clinically urgent",
] as const;

export const SEARCH_HITS: Record<string, SearchHit[]> = {
  "basal cell carcinoma of skin": [
    {
      snomed_concept_id: "254701007",
      term: "Basal cell carcinoma of skin",
      semantic_tag: "disorder",
    },
  ],
  "suspected basal cell carcinoma": [
    {
      snomed_concept_id: "274142008",
      term: "Basal cell carcinoma suspected",
      semantic_tag: "situation",
    },
  ],
  "delay in treatment may be harmful": [
    {
      snomed_concept_id: "161590003",
      term: "H/O: delayed treatment",
      semantic_tag: "situation",
    },
  ],
  "clinically urgent": [
    {
      snomed_concept_id: "103323008",
      term: "Urgent clinical concern",
      semantic_tag: "finding",
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
  rule_id: "e2e-ng12-1-7-6-walkthrough",
  name: "NG12 1.7.6 -- BCC delay concern (Ask LEO walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Consider 2WW for BCC-suspicious lesions when delay would matter.",
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
    actions?: Array<{
      strength?: string;
      criterion?: { snomed_concept_id?: string };
    }>;
    logic_tree?: {
      kind?: string;
      children?: Array<{
        kind?: string;
        criterion?: { snomed_concept_id?: string };
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
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    if (
      q.includes("raises the suspicion") ||
      q.includes("particular concern that")
    ) {
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
    const raw = route.request().postData();
    const body = raw ? (JSON.parse(raw) as { phrase?: string }) : {};
    const phrase = (body.phrase ?? "").toLowerCase();
    const terms =
      phrase.includes("delay") || phrase.includes("concern")
        ? [...DELAY_TERMS]
        : [...BCC_TERMS];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        terms,
        reason: "stubbed for NG12 1.7.6 Ask LEO walkthrough",
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
