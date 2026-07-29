/**
 * Fixtures and API stubs for NG12 1.5.2 rule-build walkthrough.
 */
import type { Page } from "@playwright/test";
import type { SearchHit } from "./ng12-walkthrough-actions";

interface FixtureItem {
  text: string;
  start: number;
  end: number;
}

interface Fixture {
  text: string;
  leadText: string;
  items: FixtureItem[];
}

function buildNg152Fixture(): Fixture {
  const leadText =
    "Carry out tests in primary care (see recommendations 1.5.6 to 1.5.9) if a woman, " +
    "or a trans man or non-binary person with female reproductive organs " +
    "(especially if they are aged 50 or over) reports having any of the following " +
    "symptoms on a persistent or frequent basis - particularly more than 12 times " +
    "per month:";
  let text = `1.5.2 ${leadText} `;
  const findings = [
    "persistent abdominal distension (often referred to as 'bloating')",
    "feeling full (early satiety) and/or loss of appetite",
    "pelvic or abdominal pain",
    "increased urinary urgency and/or frequency",
  ];
  const items: FixtureItem[] = [];
  for (const [i, finding] of findings.entries()) {
    if (i > 0) text += " ";
    const start = text.length;
    text += finding;
    items.push({ text: finding, start, end: text.length });
  }
  text += ". [2011]";
  return { text, leadText, items };
}

const FIXTURE = buildNg152Fixture();

export const FIXTURE_ITEMS = FIXTURE.items;

export const SEARCH_HITS: Record<string, SearchHit[]> = {
  "persistent abdominal distension (often referred to as 'bloating')": [
    {
      snomed_concept_id: "116289008",
      term: "Abdominal bloating",
      semantic_tag: "finding",
    },
  ],
  bloating: [
    {
      snomed_concept_id: "116289008",
      term: "Abdominal bloating",
      semantic_tag: "finding",
    },
  ],
  "feeling full (early satiety) and/or loss of appetite": [
    {
      snomed_concept_id: "442076002",
      term: "Early satiety",
      semantic_tag: "finding",
    },
  ],
  "early satiety": [
    {
      snomed_concept_id: "442076002",
      term: "Early satiety",
      semantic_tag: "finding",
    },
  ],
  "pelvic or abdominal pain": [
    {
      snomed_concept_id: "21522001",
      term: "Abdominal pain",
      semantic_tag: "finding",
    },
  ],
  "abdominal pain": [
    {
      snomed_concept_id: "21522001",
      term: "Abdominal pain",
      semantic_tag: "finding",
    },
  ],
  "increased urinary urgency and/or frequency": [
    {
      snomed_concept_id: "75088002",
      term: "Urgent desire to urinate",
      semantic_tag: "finding",
    },
  ],
  "urinary urgency": [
    {
      snomed_concept_id: "75088002",
      term: "Urgent desire to urinate",
      semantic_tag: "finding",
    },
  ],
  "ovarian cancer": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
  "primary care": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
};

export const RULE = {
  rule_id: "e2e-ng12-1-5-2-walkthrough",
  name: "NG12 1.5.2 -- primary care ovarian tests (walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: FIXTURE.text,
  recommendation_structure: {
    lead_text: FIXTURE.leadText,
    items: FIXTURE.items,
  },
  plain_english:
    "Primary-care ovarian tests for persistent or frequent red-flag symptoms.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: {
    node_id: "root",
    kind: "AND",
    children: [
      {
        node_id: "sex",
        kind: "DEMOGRAPHIC",
        field: "sex",
        operator: "==",
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
