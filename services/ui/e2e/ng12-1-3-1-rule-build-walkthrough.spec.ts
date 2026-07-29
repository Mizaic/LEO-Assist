/**
 * End-to-end walkthrough: build NG12 recommendation 1.3.1 (offer FIT
 * for suspected colorectal cancer) in the guided EditRuleDialog.
 *
 * Seven structure-sourced situations (A-G). Exercises age-stripped
 * clinical rows, "either of the following" AT_LEAST(1) with a rectal
 * bleeding lead, "any of the following" on situation F, FIT action
 * coding, priority / SLA / strength, and save / sign-off.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-3-1-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-3-1");

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

const SEARCH_HITS: Record<
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

const RULE = {
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

async function pickRowByName(
  page: Page,
  dialog: Locator,
  rowName: string | RegExp,
  searchKey: string,
) {
  const hits = SEARCH_HITS[searchKey];
  if (!hits?.[0]) throw new Error(`No SEARCH_HITS[${searchKey}]`);
  const hit = hits[0]!;
  // Prefer list-row test ids -- after coding, accessible name may
  // include "matched to: ..." and no longer equal the bare finding.
  const row = dialog
    .getByTestId(/^list-row-/)
    .filter({ hasText: rowName })
    .first();
  await expect(row).toBeVisible({ timeout: 10000 });
  const testId = await row.getAttribute("data-testid");
  if (!testId) throw new Error("list-row missing data-testid");
  await row.scrollIntoViewIfNeeded();
  await row.click();
  const checkbox = page.getByRole("checkbox", { name: `Select ${hit.term}` });
  await expect(checkbox).toBeVisible({ timeout: 15000 });
  await checkbox.check();
  await page.getByRole("button", { name: "Add 1 code" }).click();
  await expect(page.getByRole("button", { name: "Add 1 code" })).toBeHidden({
    timeout: 10000,
  });
  await expect(dialog.getByTestId(testId)).toHaveAttribute(
    "data-resolved",
    "true",
    { timeout: 10000 },
  );
}

async function chooseOnlyOneGrouping(dialog: Locator) {
  const btn = btnByLabel(dialog, /only one needs to match/i);
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(
    dialog.getByText(/only one of these needs to match/i),
  ).toBeVisible();
}

async function setPathwayAge(
  dialog: Locator,
  operatorOption: RegExp,
  value: string,
) {
  const panel = dialog.getByTestId("pathway-demographics-panel");
  const addAge = dialog.getByRole("button", {
    name: /add an age check for this situation only/i,
  });
  // Copy-across can already bring an age leaf -- only add when needed.
  if (await addAge.isEnabled()) {
    await addAge.click();
  }
  await panel.getByLabel(/how to compare age/i).click();
  await dialog.page().getByRole("option", { name: operatorOption }).click();
  await panel.getByLabel(/lower bound/i).fill(value);
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

async function confirmSituation(dialog: Locator, letter: string, next?: string) {
  const label = next
    ? new RegExp(`confirm situation ${letter}, next -> ${next}`, "i")
    : new RegExp(`^confirm situation ${letter}$`, "i");
  await btnByLabel(dialog, label).click();
}

test.describe("NG12 1.3.1 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.3.1 end-to-end with seven situations, FIT action, and sign-off", async ({
    page,
  }) => {
    test.setTimeout(360_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page);

    // -- Step 1: Always true (seeded adults age>=18) ------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "02-who-always-true");
    await btnByLabel(dialog, /No, nothing else/i).click();

    // -- Step 2: seven situations from structure ----------------------
    await expect(
      dialog.getByText(/the guideline lists 7 situations/i),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "03-situations-split-confirm");
    await btnByLabel(dialog, /Looks right, continue/i).click();

    // -- A: abdominal mass --------------------------------------------
    await expect(dialog.getByText(/situation a \(1 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await pickRowByName(page, dialog, /^abdominal mass$/i, "abdominal mass");
    await shot(page, "04-situation-a-mass");
    await confirmSituation(dialog, "a", "b");

    // -- B: change in bowel habit -------------------------------------
    await expect(dialog.getByText(/situation b \(2 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await pickRowByName(
      page,
      dialog,
      /^change in bowel habit$/i,
      "change in bowel habit",
    );
    await confirmSituation(dialog, "b", "c");

    // -- C: iron-deficiency anaemia -----------------------------------
    await expect(dialog.getByText(/situation c \(3 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await pickRowByName(
      page,
      dialog,
      /^iron-deficiency anaemia$/i,
      "iron-deficiency anaemia",
    );
    await confirmSituation(dialog, "c", "d");

    // -- D: age >=40 + weight loss + abdominal pain -------------------
    await expect(dialog.getByText(/situation d \(4 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await setPathwayAge(dialog, /is at least/i, "40");
    await pickRowByName(
      page,
      dialog,
      /^unexplained weight loss$/i,
      "unexplained weight loss",
    );
    await pickRowByName(page, dialog, /^abdominal pain$/i, "abdominal pain");
    await shot(page, "05-situation-d-age-weight-pain");
    await confirmSituation(dialog, "d", "e");

    // -- E: age <50 + rectal bleeding + either-of AT_LEAST(1) ---------
    await expect(dialog.getByText(/situation e \(5 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByRole("button", { name: /^rectal bleeding$/i }),
    ).toBeVisible();
    await setPathwayAge(dialog, /is less than/i, "50");
    await chooseOnlyOneGrouping(dialog);
    await pickRowByName(page, dialog, /^rectal bleeding$/i, "rectal bleeding");
    await pickRowByName(page, dialog, /^abdominal pain$/i, "abdominal pain");
    await pickRowByName(page, dialog, /^weight loss$/i, "weight loss");
    await shot(page, "06-situation-e-either-of");
    await confirmSituation(dialog, "e", "f");

    // -- F: age >=50 + any of three (copy-across when offered) --------
    await expect(dialog.getByText(/situation f \(6 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await setPathwayAge(dialog, /is at least/i, "50");
    const copyBtn = btnByLabel(dialog, /copy them across/i);
    if (await copyBtn.isVisible().catch(() => false)) {
      await shot(page, "07-situation-f-copy-across");
      await copyBtn.click();
    } else {
      await chooseOnlyOneGrouping(dialog);
      await pickRowByName(page, dialog, /^rectal bleeding$/i, "rectal bleeding");
      await pickRowByName(page, dialog, /^abdominal pain$/i, "abdominal pain");
      await pickRowByName(page, dialog, /^weight loss$/i, "weight loss");
    }
    const onlyOneAlready = dialog.getByText(
      /only one of these needs to match/i,
    );
    if (!(await onlyOneAlready.isVisible().catch(() => false))) {
      await chooseOnlyOneGrouping(dialog);
    }
    await shot(page, "08-situation-f-any-of");
    await confirmSituation(dialog, "f", "g");

    // -- G: age >=60 + anaemia (caveats stripped from row) ------------
    await expect(dialog.getByText(/situation g \(7 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    const anaemiaRow = dialog
      .getByTestId(/^list-row-/)
      .filter({ hasText: /anaemia even in the absence of iron deficiency/i })
      .first();
    await expect(anaemiaRow).toBeVisible();
    // Caveats stay in the quote pane; the Step 3 row must be clean.
    await expect(anaemiaRow).not.toContainText(/FIT should be offered/i);
    await setPathwayAge(dialog, /is at least/i, "60");
    await pickRowByName(
      page,
      dialog,
      /^anaemia even in the absence of iron deficiency$/i,
      "anaemia even in the absence of iron deficiency",
    );
    await shot(page, "09-situation-g-anaemia");
    await confirmSituation(dialog, "g");

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/abdominal mass/i).first()).toBeVisible();
    await expect(preview.getByText(/rectal bleeding/i).first()).toBeVisible();
    await expect(preview.getByText(/has at least 1 of:/i).first()).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "10-wizard-review-live-preview");

    // -- Suggest: FIT + 2WW + Offer -----------------------------------
    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "11-suggest-uncoded-action");

    await dialog
      .getByRole("button", {
        name: /no procedure picked yet\. click to pick/i,
      })
      .click();
    const search = dialog.getByLabel(/search clinical terms/i);
    await expect(search).toBeVisible({ timeout: 10000 });
    await search.fill("fit");
    await page
      .getByRole("button", {
        name: /Use Quantitative faecal immunochemical test/i,
      })
      .click({ timeout: 15000 });
    await expect(
      dialog.getByRole("button", {
        name: /quantitative faecal immunochemical test/i,
      }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "12-suggest-action-coded");

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await page.getByRole("option", { name: /2 week wait/i }).click();
    const dueDays = dialog.locator("#edit-rule-due-days");
    await dueDays.scrollIntoViewIfNeeded();
    await dueDays.fill("14");
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await page
      .getByRole("option", { name: /offer this test or referral/i })
      .click();
    await shot(page, "13-suggest-priority-sla-strength");

    await btnByLabel(dialog, /^Next/i).click();

    // -- Save / sign-off ----------------------------------------------
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(/saved, but not live yet/i)).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "14-save-before-after-preview");

    await dialog
      .getByLabel(/why are you changing this rule/i)
      .fill(
        "Walkthrough: coded NG12 1.3.1 FIT situations A-G, set 2WW / 14 days.",
      );
    await shot(page, "15-save-reason-filled");

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
    expect(actions?.[0]?.criterion?.snomed_concept_id).toBe("1049361000000101");

    await shot(page, "16-review-pool-after-save");
  });
});
