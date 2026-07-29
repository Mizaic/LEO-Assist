/**
 * End-to-end walkthrough: build NG12 recommendation 1.5.2 (primary-care
 * ovarian tests for persistent/frequent symptoms) in the guided
 * EditRuleDialog.
 *
 * The guideline's 4-item symptom `<ul>` under a verbose "any of the
 * following symptoms on a persistent or frequent basis..." lead must
 * stay ONE situation with AT_LEAST(1), not Situation A-D. Inclusive
 * sex phrasing in the lead must not invent a split either.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-5-2-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-5-2");

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

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
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

const RULE = {
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

type DecisionBody = {
  action?: string;
  updates?: {
    priority?: string;
    due_days?: number | null;
    actions?: Array<{ strength?: string; criterion?: { snomed_concept_id?: string } }>;
    logic_tree?: Record<string, unknown>;
  };
};

async function installFixtures(page: Page, captured: { decision: DecisionBody | null }) {
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

async function dismissSplash(page: Page) {
  await page
    .getByRole("button", { name: /skip the guideline builder intro animation/i })
    .click({ timeout: 3000 })
    .catch(() => {});
}

async function shot(page: Page, name: string) {
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: false,
  });
}

async function runAxeDialog(page: Page) {
  const results = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags([...WCAG_TAGS])
    .analyze();
  const blockers = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(
    blockers,
    JSON.stringify(
      blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help })),
      null,
      2,
    ),
  ).toEqual([]);
}

function btnByLabel(root: Locator, label: string | RegExp): Locator {
  return root.getByRole("button").filter({ hasText: label });
}

function rowTestId(item: FixtureItem): string {
  return `list-row-${item.start}-${item.end}`;
}

async function pickConceptForRow(
  page: Page,
  dialog: Locator,
  item: FixtureItem,
  searchKey: string,
) {
  const hits = SEARCH_HITS[searchKey] ?? SEARCH_HITS[item.text];
  if (!hits?.[0]) throw new Error(`No SEARCH_HITS for ${searchKey}`);
  const hit = hits[0]!;
  const row = dialog.getByTestId(rowTestId(item));
  await expect(row).toBeVisible({ timeout: 10000 });
  await row.scrollIntoViewIfNeeded();
  await row.click();
  const checkbox = page.getByRole("checkbox", { name: `Select ${hit.term}` });
  await expect(checkbox).toBeVisible({ timeout: 15000 });
  await checkbox.check();
  await page.getByRole("button", { name: "Add 1 code" }).click();
  await expect(page.getByRole("button", { name: "Add 1 code" })).toBeHidden({
    timeout: 10000,
  });
  await expect(row).toHaveAttribute("data-resolved", "true", { timeout: 10000 });
}

async function openEditDialog(page: Page): Promise<Locator> {
  await page.goto("/admin/knowledge?tab=clinical-guidelines");
  await page.waitForLoadState("load");
  await dismissSplash(page);

  const reviewTab = page.getByTestId("segmented-tab-review");
  if (await reviewTab.isVisible().catch(() => false)) {
    await reviewTab.click();
  }
  await expect(page.locator("#rule-review-body")).toBeVisible({
    timeout: 15000,
  });

  const pendingPool = page.getByTestId("rule-pool-pending");
  const pendingToggle = pendingPool.locator("button[aria-expanded]").first();
  if ((await pendingToggle.getAttribute("aria-expanded")) !== "true") {
    await pendingToggle.click();
  }

  await expect(
    page.getByRole("button", { name: `Toggle rule from ${RULE.guideline_id}` }),
  ).toBeVisible({ timeout: 15000 });
  await page
    .getByRole("button", { name: `Toggle rule from ${RULE.guideline_id}` })
    .click();
  await expect(
    page.getByRole("button", { name: `Edit rule ${RULE.rule_id}` }),
  ).toBeVisible();
  await shot(page, "01-review-pool-card");
  await page.getByRole("button", { name: `Edit rule ${RULE.rule_id}` }).click();

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("highlight-wizard")).toBeVisible();
  return dialog;
}

test.describe("NG12 1.5.2 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.5.2 end-to-end as one AT_LEAST situation, not four", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page);

    // -- Step 1: Always true (sex; age is soft "especially if") -------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-sex")).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "02-who-always-true-sex");
    await btnByLabel(dialog, /No, nothing else/i).click();

    // -- Step 2: must NOT invent Situation A-D from the symptom list --
    await expect(
      dialog.getByText(/couldn't find more than one situation/i),
    ).toBeVisible({ timeout: 15000 });
    await expect(dialog.getByText(/\(A\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(B\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(C\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(D\)/i)).toHaveCount(0);
    await runAxeDialog(page);
    await shot(page, "03-situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    // -- Step 3: one situation, AT_LEAST(1) over 4 symptom bullets ----
    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByRole("group", { name: /any of the following/i }),
    ).toBeVisible();
    await btnByLabel(dialog, /only one needs to match/i).click();
    await expect(
      dialog.getByText(/only one of these needs to match/i),
    ).toBeVisible();
    await shot(page, "04-situation-at-least-1-grouping");

    const searchKeys = [
      "persistent abdominal distension (often referred to as 'bloating')",
      "feeling full (early satiety) and/or loss of appetite",
      "pelvic or abdominal pain",
      "increased urinary urgency and/or frequency",
    ] as const;
    for (const [i, item] of FIXTURE.items.entries()) {
      await pickConceptForRow(page, dialog, item, searchKeys[i]!);
    }
    await runAxeDialog(page);
    await shot(page, "05-situation-all-symptoms-coded");
    await btnByLabel(dialog, /^confirm situation a$/i).click();

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/abdominal bloating/i).first()).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "06-wizard-review-live-preview");

    // -- Suggest: primary-care ovarian tests --------------------------
    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "07-suggest-uncoded-action");

    await dialog
      .getByRole("button", {
        name: /no procedure picked yet\. click to pick/i,
      })
      .click();
    const search = dialog.getByLabel(/search clinical terms/i);
    await expect(search).toBeVisible({ timeout: 10000 });
    await search.fill("ovarian cancer");
    await page
      .getByRole("button", { name: /Use Ovarian cancer screening/i })
      .click({ timeout: 15000 });
    await expect(
      dialog.getByRole("button", { name: /ovarian cancer screening/i }),
    ).toBeVisible({ timeout: 10000 });

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await page.getByRole("option", { name: /routine/i }).click();
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await page
      .getByRole("option", { name: /offer this test or referral/i })
      .click();
    await shot(page, "08-suggest-ovarian-tests");

    await btnByLabel(dialog, /^Next/i).click();

    // -- Save / sign-off ----------------------------------------------
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(/saved, but not live yet/i)).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "09-save-before-after-preview");

    await dialog
      .getByLabel(/why are you changing this rule/i)
      .fill(
        "Walkthrough: coded NG12 1.5.2 as one AT_LEAST(1) symptom cluster, not four situations.",
      );
    await shot(page, "10-save-reason-filled");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    expect(captured.decision?.updates?.logic_tree).toBeTruthy();
    const actions = captured.decision?.updates?.actions;
    expect(Array.isArray(actions) && actions.length > 0).toBe(true);
    expect(actions?.[0]?.strength).toBe("offer");
    expect(actions?.[0]?.criterion?.snomed_concept_id).toBe("268544008");
  });
});
