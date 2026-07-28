/**
 * End-to-end walkthrough: build NG12 recommendation 1.1.2 (urgent
 * chest X-ray for lung cancer) in the guided EditRuleDialog.
 *
 * Covers every live step a Knowledge Base Author uses -- Review pool,
 * Who/Situations/Conditions/Review wizard phases, clinical coding,
 * back-and-forth, Suggest (priority / strength / SLA), Save / sign-off
 * -- with assertions, axe checks, and a numbered screenshot pack.
 *
 * Situation A uses "At least 2 need to match" (guideline "2 or more").
 * Situation B codes "ever smoked" plus AT_LEAST(1) of the shared
 * 6-symptom list (via Copy across when offered).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-1-2-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-1-2");

interface FixtureItem {
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

const SYMPTOMS = [
  "cough",
  "fatigue",
  "shortness of breath",
  "chest pain",
  "weight loss",
  "appetite loss",
] as const;

const SEARCH_HITS: Record<
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

const RULE = {
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

type DecisionBody = {
  action?: string;
  reason?: string;
  updates?: {
    priority?: string;
    due_days?: number | null;
    actions?: Array<{ strength?: string; criterion?: { snomed_concept_id?: string } }>;
    logic_tree?: Record<string, unknown>;
    name?: string;
  };
};

function rowTestId(item: FixtureItem): string {
  return `list-row-${item.start}-${item.end}`;
}

function symptomItem(label: string): FixtureItem {
  const item = FIXTURE.items.find((i) => i.text === label);
  if (!item) throw new Error(`Missing fixture item: ${label}`);
  return item;
}

async function installFixtures(page: Page, captured: { decision: DecisionBody | null }) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([RULE]),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=active*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=superseded*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=rejected*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
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
      blockers.map((v) => ({
        id: v.id,
        impact: v.impact,
        help: v.help,
      })),
      null,
      2,
    ),
  ).toEqual([]);
}

/** Wizard row coding uses MultiConceptPicker (multiPick=true). */
async function pickConceptForRow(
  page: Page,
  dialog: Locator,
  item: FixtureItem,
  termLabel: string,
  hitIndex = 0,
) {
  const hits = SEARCH_HITS[item.text];
  if (!hits?.[hitIndex]) {
    throw new Error(`No SEARCH_HITS[${item.text}][${hitIndex}]`);
  }
  const hit = hits[hitIndex]!;
  const row = dialog.getByTestId(rowTestId(item));
  await row.scrollIntoViewIfNeeded();
  await row.click();
  const checkbox = page.getByRole("checkbox", {
    name: `Select ${hit.term}`,
  });
  await expect(checkbox).toBeVisible({ timeout: 15000 });
  await checkbox.check();
  await page.getByRole("button", { name: "Add 1 code" }).click();
  await expect(page.getByRole("button", { name: "Add 1 code" })).toBeHidden({
    timeout: 10000,
  });
  await expect(row).toHaveAttribute("data-resolved", "true", {
    timeout: 10000,
  });
  void termLabel;
}

async function codeAllSymptoms(page: Page, dialog: Locator) {
  for (const label of SYMPTOMS) {
    await pickConceptForRow(page, dialog, symptomItem(label), label);
  }
}

/** Tooltip titles often become the accessible name; match visible label. */
function btnByLabel(root: Locator, label: string | RegExp): Locator {
  return root.getByRole("button").filter({ hasText: label });
}

async function chooseAtLeastNGrouping(dialog: Locator, n: number) {
  const btn = btnByLabel(dialog, new RegExp(`at least ${n} need to match`, "i"));
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(
    dialog.getByText(new RegExp(`at least ${n} of these need to match`, "i")),
  ).toBeVisible();
}

async function chooseOnlyOneGrouping(dialog: Locator) {
  const btn = btnByLabel(dialog, /only one needs to match/i);
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(
    dialog.getByText(/only one of these needs to match/i),
  ).toBeVisible();
}

async function pickEverSmoked(page: Page, dialog: Locator) {
  // Role name (not getByText /^...$/) -- row markup can include siblings.
  const row = dialog.getByRole("button", { name: /^ever smoked$/i });
  await expect(row).toBeVisible({ timeout: 10000 });
  const testId = await row.getAttribute("data-testid");
  if (!testId) throw new Error("ever smoked row missing data-testid");
  const m = /^list-row-(\d+)-(\d+)$/.exec(testId);
  if (!m) throw new Error(`Unexpected row test id: ${testId}`);
  const item: FixtureItem = {
    text: "ever smoked",
    start: Number(m[1]),
    end: Number(m[2]),
  };
  await pickConceptForRow(page, dialog, item, "ever smoked", 0);
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

test.describe("NG12 1.1.2 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.1.2 end-to-end with coding, navigation, priority/SLA, and sign-off", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page);

    // -- Step 1: Always true (age) ------------------------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toHaveAttribute(
      "data-has-anchor",
      "true",
    );
    await runAxeDialog(page);
    await shot(page, "02-who-always-true-age");
    await btnByLabel(dialog, /No, nothing else/i).click();

    // -- Step 2: two situations (heuristic split for 1.1.2) -----------
    await expect(
      dialog.getByText(/we think we found 2 possible situations/i),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "03-situations-split-confirm");
    await btnByLabel(dialog, /Looks right, continue/i).click();

    // -- Situation A: AT_LEAST(2) from "2 or more of the following" ---
    await expect(dialog.getByText(/situation a \(1 of 2\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByRole("group", { name: /2 or more of the following/i }),
    ).toBeVisible();
    await chooseAtLeastNGrouping(dialog, 2);
    await shot(page, "04-situation-a-cluster-at-least-2");
    await codeAllSymptoms(page, dialog);
    await runAxeDialog(page);
    await shot(page, "05-situation-a-all-symptoms-coded");
    await btnByLabel(dialog, /confirm situation a, next -> b/i).click();

    // -- Situation B: ever smoked + copy-across AT_LEAST(1) -----------
    await expect(dialog.getByText(/situation b \(2 of 2\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByRole("button", { name: /^ever smoked$/i }),
    ).toBeVisible();
    const copyBtn = btnByLabel(dialog, /copy them across/i);
    if (await copyBtn.isVisible().catch(() => false)) {
      await shot(page, "06-situation-b-copy-across-offer");
      await copyBtn.click();
    } else {
      await chooseOnlyOneGrouping(dialog);
      await codeAllSymptoms(page, dialog);
    }
    const onlyOneAlready = dialog.getByText(
      /only one of these needs to match/i,
    );
    if (!(await onlyOneAlready.isVisible().catch(() => false))) {
      await chooseOnlyOneGrouping(dialog);
    }
    await pickEverSmoked(page, dialog);
    await runAxeDialog(page);
    await shot(page, "07-situation-b-coded");
    await btnByLabel(dialog, /^confirm situation b$/i).click();

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.getByRole("region", {
      name: /live preview of this rule/i,
    });
    await expect(preview).toBeVisible();
    // A = AT_LEAST(2) from "2 or more"; B = ever smoked + AT_LEAST(1).
    await expect(preview.getByText(/cough/i).first()).toBeVisible();
    await expect(preview.getByText(/has at least 2 of:/i)).toHaveCount(1);
    await expect(preview.getByText(/has at least 1 of:/i)).toHaveCount(1);
    await expect(preview.getByText(/smoker/i).first()).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "08-wizard-review-live-preview");

    // -- Back-and-forth: re-open B, swap cough via synonym editor ------
    // WizardHeader's Back (not the outer dialog footer Back) -- label
    // is plain "Back"; Tooltip may also expose the longer aria-name.
    await dialog
      .getByTestId("highlight-wizard")
      .getByRole("button", { name: /^(Back|Go back to the previous wizard)/i })
      .click();
    await expect(dialog.getByText(/situation b \(2 of 2\)/i)).toBeVisible({
      timeout: 10000,
    });
    await dialog.getByTestId(rowTestId(symptomItem("cough"))).click();
    // Nested synonym editor -- do not match the outer "Change this rule"
    // dialog (its DOM id also contains "edit-rule").
    const synonym = page.locator('[aria-labelledby^="synonym-editor-title-"]');
    await expect(synonym).toBeVisible({ timeout: 10000 });
    await shot(page, "09-synonym-editor-cough");
    await synonym.getByRole("button", { name: /remove this match/i }).click();
    await expect(synonym).toBeHidden({ timeout: 10000 });
    // Re-code cough with the alternate Dry cough hit.
    await pickConceptForRow(page, dialog, symptomItem("cough"), "cough", 1);
    await shot(page, "10-situation-b-cough-swapped");
    await btnByLabel(dialog, /^confirm situation b$/i).click();
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 10000,
    });
    await shot(page, "11-wizard-review-after-swap");

    // -- Outer Suggest step -------------------------------------------
    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "12-suggest-uncoded-action");

    // Code the chest X-ray procedure (single-pick ConceptSearchPanel).
    await dialog
      .getByRole("button", {
        name: /no procedure picked yet\. click to pick/i,
      })
      .click();
    const search = dialog.getByLabel(/search clinical terms/i);
    await expect(search).toBeVisible({ timeout: 10000 });
    await search.fill("chest x-ray");
    await page
      .getByRole("button", { name: /Use Plain chest X-ray/i })
      .click({ timeout: 15000 });
    await expect(
      dialog.getByRole("button", { name: /plain chest x-ray/i }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "13-suggest-action-coded");

    // Priority = 2WW, SLA = 14 days, strength = Offer.
    // PriorityPanel sits above the action chips; coding the action can
    // leave it scrolled out of the dialog body -- bring it back first.
    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await page.getByRole("option", { name: /2 week wait/i }).click();
    await shot(page, "14-suggest-priority-2ww");
    const dueDays = dialog.locator("#edit-rule-due-days");
    await dueDays.scrollIntoViewIfNeeded();
    await dueDays.fill("14");
    await shot(page, "15-suggest-sla-14-days");
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await page
      .getByRole("option", { name: /offer this test or referral/i })
      .click();
    await shot(page, "16-suggest-strength-offer");

    // Outer stepper back-and-forth: Suggest <-> Save (Who remounts wizard).
    await dialog
      .getByRole("button", {
        name: /step 3 of 3: save your change/i,
      })
      .click();
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "17-stepper-jump-save");
    await dialog
      .getByRole("button", {
        name: /step 2 of 3: what should the system suggest/i,
      })
      .click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "18-stepper-jump-back-suggest");
    await btnByLabel(dialog, /^Next/i).click();

    // -- Save / verify / sign-off -------------------------------------
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await expect(
      dialog.getByText(/saved, but not live yet/i),
    ).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "19-save-before-after-preview");

    const reason = dialog.getByLabel(/why are you changing this rule/i);
    await reason.fill(
      "Walkthrough: coded NG12 1.1.2 symptoms, set 2WW / 14 days, offer chest X-ray.",
    );
    await shot(page, "20-save-reason-filled");
    await shot(page, "21-not-live-yet-banner");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    expect(captured.decision?.updates?.priority).toBe("2ww");
    expect(captured.decision?.updates?.due_days).toBe(14);
    expect(captured.decision?.updates?.logic_tree).toBeTruthy();
    const actions = captured.decision?.updates?.actions;
    expect(Array.isArray(actions) && actions.length > 0).toBe(true);
    expect(actions?.[0]?.strength).toBe("offer");
    expect(actions?.[0]?.criterion?.snomed_concept_id).toBe("399208008");

    await shot(page, "22-review-pool-after-save");
  });
});
