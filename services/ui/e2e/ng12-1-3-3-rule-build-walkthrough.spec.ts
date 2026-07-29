/**
 * End-to-end walkthrough: build NG12 recommendation 1.3.3 (safety
 * netting when FIT sample not returned or FIT below 10) in the guided
 * EditRuleDialog.
 *
 * Lead prose splits two situations ("not returned a faecal sample" OR
 * "FIT result below 10") even though the structure list after the colon
 * is an AND-joined ACTION list (safety netting + referral).
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-3-3-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-3-3");

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

function buildNg133Fixture(): Fixture {
  const leadText =
    "For people who have not returned a faecal sample or who have a FIT " +
    "result below 10 micrograms of haemoglobin per gram of faeces:";
  const actionA = "safety netting processes should be in place";
  const actionB =
    "referral to an appropriate secondary care pathway should not be delayed " +
    "if there is strong clinical concern of cancer because of ongoing " +
    "unexplained symptoms (for example, abdominal mass). [2023]";
  const text = `1.3.3 ${leadText} ${actionA} ${actionB}`;
  const items: FixtureItem[] = [
    {
      text: actionA,
      start: text.indexOf(actionA),
      end: text.indexOf(actionA) + actionA.length,
    },
    {
      text: actionB,
      start: text.indexOf(actionB),
      end: text.indexOf(actionB) + actionB.length,
    },
  ];
  return { text, leadText, items };
}

const FIXTURE = buildNg133Fixture();

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "not returned a faecal sample": [
    {
      snomed_concept_id: "149441000000102",
      term: "Provision of faecal immunochemical test kit declined",
      semantic_tag: "situation",
    },
  ],
  "faecal sample": [
    {
      snomed_concept_id: "149441000000102",
      term: "Provision of faecal immunochemical test kit declined",
      semantic_tag: "situation",
    },
  ],
  "FIT result below 10 micrograms of haemoglobin per gram of faeces": [
    {
      snomed_concept_id: "1049361000000101",
      term: "Quantitative faecal immunochemical test",
      semantic_tag: "observable entity",
    },
  ],
  "fit result": [
    {
      snomed_concept_id: "1049361000000101",
      term: "Quantitative faecal immunochemical test",
      semantic_tag: "observable entity",
    },
  ],
  "safety netting": [
    {
      snomed_concept_id: "185389006",
      term: "Follow-up arranged",
      semantic_tag: "procedure",
    },
  ],
  referral: [
    {
      snomed_concept_id: "276401000000108",
      term: "Fast track referral for suspected colorectal cancer",
      semantic_tag: "procedure",
    },
  ],
};

const RULE = {
  rule_id: "e2e-ng12-1-3-3-walkthrough",
  name: "NG12 1.3.3 -- FIT safety netting (walkthrough)",
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
  plain_english: "Safety net when FIT sample missing or FIT below 10.",
  present_criteria: [],
  absent_criteria: [],
  // Seed a leaf so the guided wizard opens (empty trees show Add-first).
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

test.describe("NG12 1.3.3 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.3.3 end-to-end with lead-or situations, action coding, and sign-off", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page);

    // -- Step 1: Always true ------------------------------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "02-who-always-true");
    await btnByLabel(dialog, /No, nothing else/i).click();

    // -- Step 2: two situations from lead "or who have" ---------------
    await expect(
      dialog.getByText(/we think we found 2 possible situations/i),
    ).toBeVisible({ timeout: 15000 });
    // Situation cards (A)/(B) -- quote pane also repeats the same words.
    await expect(dialog.getByText(/\(A\).*faecal sample/i)).toBeVisible();
    await expect(dialog.getByText(/\(B\).*FIT result below 10/i)).toBeVisible();
    // Action list must not become Situation C.
    await expect(dialog.getByText(/\(C\)/i)).toHaveCount(0);
    await runAxeDialog(page);
    await shot(page, "03-situations-lead-or-split");
    await btnByLabel(dialog, /Looks right, continue/i).click();

    // -- Situation A: faecal sample not returned ----------------------
    await expect(dialog.getByText(/situation a \(1 of 2\)/i)).toBeVisible({
      timeout: 15000,
    });
    await pickRowByName(
      page,
      dialog,
      /not returned a faecal sample/i,
      "not returned a faecal sample",
    );
    await shot(page, "04-situation-a-sample-not-returned");
    await btnByLabel(dialog, /confirm situation a, next -> b/i).click();

    // -- Situation B: FIT below 10 ------------------------------------
    await expect(dialog.getByText(/situation b \(2 of 2\)/i)).toBeVisible({
      timeout: 15000,
    });
    await pickRowByName(
      page,
      dialog,
      /FIT result below 10/i,
      "FIT result below 10 micrograms of haemoglobin per gram of faeces",
    );
    await shot(page, "05-situation-b-fit-below-10");
    await btnByLabel(dialog, /^confirm situation b$/i).click();

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/faecal immunochemical/i).first()).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "06-wizard-review-live-preview");

    // -- Suggest: safety-netting style follow-up ----------------------
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
    await search.fill("safety netting");
    await page
      .getByRole("button", { name: /Use Follow-up arranged/i })
      .click({ timeout: 15000 });
    await expect(
      dialog.getByRole("button", { name: /follow-up arranged/i }),
    ).toBeVisible({ timeout: 10000 });

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await page.getByRole("option", { name: /routine/i }).click();
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await page.getByRole("option", { name: /watch and check back/i }).click();
    await shot(page, "08-suggest-safety-net");

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
        "Walkthrough: coded NG12 1.3.3 sample-not-returned / FIT<10 situations.",
      );
    await shot(page, "10-save-reason-filled");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    expect(captured.decision?.updates?.logic_tree).toBeTruthy();
    const actions = captured.decision?.updates?.actions;
    expect(Array.isArray(actions) && actions.length > 0).toBe(true);
    expect(actions?.[0]?.strength).toBe("safety_net");
    expect(actions?.[0]?.criterion?.snomed_concept_id).toBe("185389006");

    await shot(page, "11-review-pool-after-save");
  });
});
