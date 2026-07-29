/**
 * Fixtures and API stubs for NG12 1.1.2 rule-build walkthrough.
 */
import type { Page } from "@playwright/test";

export interface FixtureItem {
  text: string;
  start: number;
  end: number;
}

interface Fixture {
  text: string;
  leadText: string;
  items: FixtureItem[];
  trailingText: string;
}

/** Same NG12 1.1.2 shape as pathwayTextSplit.test.ts. */
function buildNg112Fixture(): Fixture {
  let text = "";
  const append = (s: string) => {
    text += s;
  };
  const takeFlatItem = (label: string): FixtureItem => {
    const start = text.length;
    append(label);
    return { text: label, start, end: text.length };
  };

  const leadText =
    "Offer an urgent, direct access chest X-ray to assess for lung cancer " +
    "in people aged 40 and over if they have 2 or more of the following " +
    "unexplained symptoms, or if they have ever smoked and have 1 or " +
    "more of the following unexplained symptoms: ";
  append(leadText);

  const items: FixtureItem[] = [];
  for (const [i, symptom] of [
    "cough",
    "fatigue",
    "shortness of breath",
    "chest pain",
    "weight loss",
    "appetite loss",
  ].entries()) {
    if (i > 0) append(", ");
    items.push(takeFlatItem(symptom));
  }
  const trailingText = ". [2015]";
  append(trailingText);

  return { text, leadText, items, trailingText };
}

const FIXTURE = buildNg112Fixture();

export const SYMPTOMS = [
  "cough",
  "fatigue",
  "shortness of breath",
  "chest pain",
  "weight loss",
  "appetite loss",
] as const;

export const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  cough: [
    {
      snomed_concept_id: "49727002",
      term: "Cough",
      semantic_tag: "finding",
    },
    {
      snomed_concept_id: "11833005",
      term: "Dry cough",
      semantic_tag: "finding",
    },
  ],
  fatigue: [
    {
      snomed_concept_id: "84229001",
      term: "Fatigue",
      semantic_tag: "finding",
    },
  ],
  "shortness of breath": [
    {
      snomed_concept_id: "267036007",
      term: "Shortness of breath",
      semantic_tag: "finding",
    },
  ],
  "chest pain": [
    {
      snomed_concept_id: "29857009",
      term: "Chest pain",
      semantic_tag: "finding",
    },
  ],
  "weight loss": [
    {
      snomed_concept_id: "262285001",
      term: "Weight loss",
      semantic_tag: "finding",
    },
  ],
  "appetite loss": [
    {
      snomed_concept_id: "79890006",
      term: "Loss of appetite",
      semantic_tag: "finding",
    },
  ],
  "chest x-ray": [
    {
      snomed_concept_id: "399208008",
      term: "Plain chest X-ray",
      semantic_tag: "procedure",
    },
  ],
  "chest x ray": [
    {
      snomed_concept_id: "399208008",
      term: "Plain chest X-ray",
      semantic_tag: "procedure",
    },
  ],
  "ever smoked": [
    {
      snomed_concept_id: "77176002",
      term: "Smoker",
      semantic_tag: "finding",
    },
    {
      snomed_concept_id: "8517006",
      term: "Ex-smoker",
      semantic_tag: "finding",
    },
  ],
};

export const RULE = {
  rule_id: "e2e-ng12-1-1-2-walkthrough",
  name: "NG12 1.1.2 -- urgent chest X-ray (walkthrough)",
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
    trailing_text: FIXTURE.trailingText,
  },
  plain_english: "Urgent chest X-ray criteria for suspected lung cancer.",
  present_criteria: [],
  absent_criteria: [],
  // Age only -- situations and clinical codes are built live in the wizard.
  logic_tree: {
    node_id: "root",
    kind: "AND",
    children: [
      {
        node_id: "age",
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: "40",
      },
    ],
  },
  // Blank action so Suggest-step coding is real.
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
  reason?: string;
  updates?: {
    priority?: string;
    due_days?: number | null;
    actions?: Array<{
      strength?: string;
      criterion?: { snomed_concept_id?: string };
    }>;
    logic_tree?: Record<string, unknown>;
    name?: string;
  };
};

export function rowTestId(item: FixtureItem): string {
  return `list-row-${item.start}-${item.end}`;
}

export function symptomItem(label: string): FixtureItem {
  const item = FIXTURE.items.find((i) => i.text === label);
  if (!item) throw new Error(`Missing fixture item: ${label}`);
  return item;
}

export function hit(searchKey: string, hitIndex = 0) {
  const hits = SEARCH_HITS[searchKey];
  if (!hits?.[hitIndex]) {
    throw new Error(`No SEARCH_HITS[${searchKey}][${hitIndex}]`);
  }
  return hits[hitIndex]!;
}

export async function installFixtures(
  page: Page,
  captured: { decision: DecisionBody | null },
) {
  await page.route(
    "**/api/guidance/rules/review*status=pending_review*",
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([RULE]),
      }),
  );
  for (const status of ["active", "superseded", "rejected"]) {
    await page.route(
      `**/api/guidance/rules/review*status=${status}*`,
      (route) =>
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
    const hits = SEARCH_HITS[q] ?? [];
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
