/**
 * Fixtures and API stubs for NG12 1.3.1 rule-build walkthrough.
 */
import type { Page } from "@playwright/test";

interface FixtureItem {
  text: string;
  start: number;
  end: number;
  children?: FixtureItem[];
}

interface Fixture {
  text: string;
  leadText: string;
  items: FixtureItem[];
}

function buildNg131Fixture(): Fixture {
  const leadText =
    "Offer quantitative faecal immunochemical testing (FIT) using HM-JACKarc " +
    "or OC-Sensor to guide referral for suspected colorectal cancer in adults:";
  let text = `1.3.1 ${leadText} `;
  const take = (label: string, children?: FixtureItem[]): FixtureItem => {
    const start = text.length;
    text += label;
    const end = text.length;
    return children ? { text: label, start, end, children } : { text: label, start, end };
  };
  const items: FixtureItem[] = [];
  items.push(take("with an abdominal mass"));
  text += ", or ";
  items.push(take("with a change in bowel habit"));
  text += ", or ";
  items.push(take("with iron-deficiency anaemia"));
  text += ", or ";
  items.push(take("aged 40 and over with unexplained weight loss and abdominal pain"));
  text += ", or ";
  const eLead =
    "aged under 50 with rectal bleeding and either of the following unexplained symptoms:";
  const eStart = text.length;
  text += eLead;
  const eChildren: FixtureItem[] = [];
  for (const [i, s] of ["abdominal pain", "weight loss"].entries()) {
    if (i > 0) text += " ";
    const s0 = text.length;
    text += s;
    eChildren.push({ text: s, start: s0, end: text.length });
  }
  items.push({
    text: eLead,
    start: eStart,
    end: eStart + eLead.length,
    children: eChildren,
  });
  text += ", or ";
  const fLead = "aged 50 and over with any of the following unexplained symptoms:";
  const fStart = text.length;
  text += fLead;
  const fChildren: FixtureItem[] = [];
  for (const [i, s] of [
    "rectal bleeding",
    "abdominal pain",
    "weight loss",
  ].entries()) {
    if (i > 0) text += " ";
    const s0 = text.length;
    text += s;
    fChildren.push({ text: s, start: s0, end: text.length });
  }
  items.push({
    text: fLead,
    start: fStart,
    end: fStart + fLead.length,
    children: fChildren,
  });
  text += ", or ";
  items.push(
    take(
      "aged 60 and over with anaemia even in the absence of iron deficiency. " +
        "FIT should be offered even if the person has previously had a negative FIT result " +
        "through the NHS bowel cancer screening programme. People with a rectal mass, an " +
        "unexplained anal mass or unexplained anal ulceration do not need to be offered FIT " +
        "before referral is considered. [2023]",
    ),
  );
  return { text, leadText, items };
}

const FIXTURE = buildNg131Fixture();

export const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "abdominal mass": [
    {
      snomed_concept_id: "271860004",
      term: "Abdominal mass",
      semantic_tag: "finding",
    },
  ],
  "change in bowel habit": [
    {
      snomed_concept_id: "88111009",
      term: "Altered bowel function",
      semantic_tag: "finding",
    },
  ],
  "iron-deficiency anaemia": [
    {
      snomed_concept_id: "87522002",
      term: "Iron deficiency anemia",
      semantic_tag: "disorder",
    },
  ],
  "unexplained weight loss": [
    {
      snomed_concept_id: "262285001",
      term: "Weight loss",
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
  "rectal bleeding": [
    {
      snomed_concept_id: "12063002",
      term: "Rectal bleeding",
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
  "anaemia even in the absence of iron deficiency": [
    {
      snomed_concept_id: "271737000",
      term: "Anemia",
      semantic_tag: "disorder",
    },
  ],
  fit: [
    {
      snomed_concept_id: "1049361000000101",
      term: "Quantitative faecal immunochemical test",
      semantic_tag: "observable entity",
    },
  ],
  "faecal immunochemical": [
    {
      snomed_concept_id: "1049361000000101",
      term: "Quantitative faecal immunochemical test",
      semantic_tag: "observable entity",
    },
  ],
};

export const RULE = {
  rule_id: "e2e-ng12-1-3-1-walkthrough",
  name: "NG12 1.3.1 -- offer FIT (walkthrough)",
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
  plain_english: "Offer FIT to guide colorectal cancer referral in adults.",
  present_criteria: [],
  absent_criteria: [],
  // Seed age>=18 so the guided wizard opens (empty trees show the
  // blank "Add first..." state instead). "Adults" in the NICE text
  // is the clinical intent; pathway-specific ages are added in Step 3.
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
    due_days?: number | null;
    actions?: Array<{ strength?: string; criterion?: { snomed_concept_id?: string } }>;
    logic_tree?: Record<string, unknown>;
  };
};

export async function installFixtures(page: Page, captured: { decision: DecisionBody | null }) {
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
