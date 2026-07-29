/**
 * Fixtures and API stubs for NG12 1.7.1 rule-build walkthrough.
 */
import type { Page } from "@playwright/test";
import type { SearchHit } from "./ng12-walkthrough-actions";

export const REC_TEXT =
  "1.7.1 Refer people using a suspected cancer pathway referral for melanoma " +
  "if they have a suspicious pigmented skin lesion with a weighted 7-point " +
  "checklist score of 3 or more. [2015]";

export const COMPANION_PANELS = [
  {
    title: "Weighted 7-point checklist",
    kind: "weighted_checklist",
    threshold: 3,
    groups: [
      {
        label: "Major features of the lesions (scoring 2 points each)",
        points: 2,
        items: [
          { text: "change in size" },
          { text: "irregular shape" },
          { text: "irregular colour" },
        ],
      },
      {
        label: "Minor features of the lesions (scoring 1 point each)",
        points: 1,
        items: [
          { text: "largest diameter 7 mm or more" },
          { text: "inflammation" },
          { text: "oozing" },
          { text: "change in sensation" },
        ],
      },
    ],
  },
];

export const FEATURES = [
  "suspicious pigmented skin lesion",
  "change in size",
  "irregular shape",
  "irregular colour",
  "largest diameter 7 mm or more",
  "inflammation",
  "oozing",
  "change in sensation",
] as const;

export const SEARCH_HITS: Record<string, SearchHit[]> = {
  "suspicious pigmented skin lesion": [
    {
      snomed_concept_id: "734936000",
      term: "Malignant pigmented skin lesion suspected",
      semantic_tag: "situation",
    },
  ],
  "change in size": [
    {
      snomed_concept_id: "112630007",
      term: "Change in size of mole",
      semantic_tag: "finding",
    },
  ],
  "irregular shape": [
    {
      snomed_concept_id: "403532002",
      term: "Irregular outline of mole",
      semantic_tag: "finding",
    },
  ],
  "irregular colour": [
    {
      snomed_concept_id: "403533007",
      term: "Variegated color of mole",
      semantic_tag: "finding",
    },
  ],
  "largest diameter 7 mm or more": [
    {
      snomed_concept_id: "403534001",
      term: "Large mole",
      semantic_tag: "finding",
    },
  ],
  inflammation: [
    {
      snomed_concept_id: "128477000",
      term: "Abscess",
      semantic_tag: "disorder",
    },
  ],
  oozing: [
    {
      snomed_concept_id: "315257008",
      term: "Oozing of pigmented skin lesion",
      semantic_tag: "disorder",
    },
  ],
  "change in sensation": [
    {
      snomed_concept_id: "271793003",
      term: "Disorder of skin sensation",
      semantic_tag: "disorder",
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
};

export const RULE = {
  rule_id: "e2e-ng12-1-7-1-walkthrough",
  name: "NG12 1.7.1 -- melanoma 7-point checklist (walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  companion_panels: COMPANION_PANELS,
  plain_english: "Refer for melanoma when 7-point checklist score is 3 or more.",
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
        value: "18",
        unit: "years",
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
    actions?: Array<{
      strength?: string;
      criterion?: { snomed_concept_id?: string };
    }>;
    logic_tree?: {
      kind?: string;
      children?: Array<{
        kind?: string;
        min?: number;
        children?: Array<{ kind?: string; min?: number; children?: unknown[] }>;
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

export function findOrNode(node: DecisionBody["updates"]): {
  kind?: string;
  children?: Array<{ kind?: string; min?: number; children?: unknown[] }>;
} | null {
  const tree = node?.logic_tree;
  if (!tree?.children) return null;
  for (const child of tree.children) {
    if (child.kind === "OR") return child;
  }
  return null;
}
