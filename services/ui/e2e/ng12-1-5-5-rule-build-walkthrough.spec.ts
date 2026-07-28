/**
 * End-to-end walkthrough: build NG12 recommendation 1.5.5 (ovarian
 * cancer tests when IBS-suggestive symptoms present at age 50+) in the
 * guided EditRuleDialog.
 *
 * Inclusive sex phrasing ("any woman, or trans man or non-binary...")
 * must NOT become Situation A/B. Empty recommendation_structure falls
 * back to the text heuristic, which correctly reports no split.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-5-5-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-5-5");

const REC_TEXT =
  "1.5.5 Carry out appropriate tests for ovarian cancer (see recommendations " +
  "1.5.6 to 1.5.9) in any woman, or trans man or non-binary person with " +
  "female reproductive organs who is aged 50 or over and who has " +
  "experienced symptoms within the last 12 months that suggest irritable " +
  "bowel syndrome (IBS), because IBS rarely presents for the first time " +
  "at this age. (See NICE's guideline on irritable bowel syndrome in " +
  "adults .) [2011]";

const IBS_ROW =
  "symptoms within the last 12 months that suggest irritable bowel syndrome (IBS)";

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "irritable bowel": [
    {
      snomed_concept_id: "10743008",
      term: "Irritable bowel syndrome",
      semantic_tag: "disorder",
    },
  ],
  "irritable bowel syndrome": [
    {
      snomed_concept_id: "10743008",
      term: "Irritable bowel syndrome",
      semantic_tag: "disorder",
    },
  ],
  symptoms: [
    {
      snomed_concept_id: "10743008",
      term: "Irritable bowel syndrome",
      semantic_tag: "disorder",
    },
  ],
  "ovarian cancer": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
  "ovarian cancer screening": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
  "appropriate tests": [
    {
      snomed_concept_id: "268544008",
      term: "Ovarian cancer screening",
      semantic_tag: "procedure",
    },
  ],
};

const RULE = {
  rule_id: "e2e-ng12-1-5-5-walkthrough",
  name: "NG12 1.5.5 -- ovarian tests / IBS symptoms (walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Offer ovarian cancer tests when IBS-like symptoms appear at age 50+.",
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
        value: "50",
        unit: "years",
      },
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

async function pickIbsSymptomsRow(page: Page, dialog: Locator) {
  const row = dialog
    .getByTestId(/^list-row-/)
    .filter({ hasText: /irritable bowel syndrome/i })
    .first();
  await expect(row).toBeVisible({ timeout: 10000 });
  const testId = await row.getAttribute("data-testid");
  if (!testId) throw new Error("IBS list-row missing data-testid");
  await row.scrollIntoViewIfNeeded();
  await row.click();

  const search = page.getByLabel(/search clinical terms/i);
  await expect(search).toBeVisible({ timeout: 15000 });
  await search.fill("irritable bowel");
  const checkbox = page.getByRole("checkbox", {
    name: "Select Irritable bowel syndrome",
  });
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

test.describe("NG12 1.5.5 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.5.5 end-to-end with no fake sex-phrase situations", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page);

    // -- Step 1: Always true (age + sex) ------------------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toHaveAttribute(
      "data-has-anchor",
      "true",
    );
    await expect(dialog.getByTestId("prerequisite-row-sex")).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "02-who-always-true-age-sex");
    await btnByLabel(dialog, /No, nothing else/i).click();

    // -- Step 2: inclusive sex ", or " must NOT invent Situation A/B --
    await expect(
      dialog.getByText(/couldn't find more than one situation/i),
    ).toBeVisible({ timeout: 15000 });
    await expect(dialog.getByText(/\(A\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(B\)/i)).toHaveCount(0);
    await runAxeDialog(page);
    await shot(page, "03-situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    // -- Step 3: single situation -- IBS-suggestive symptoms ----------
    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByTestId(/^list-row-/).filter({ hasText: IBS_ROW }),
    ).toBeVisible();
    await pickIbsSymptomsRow(page, dialog);
    await runAxeDialog(page);
    await shot(page, "04-situation-ibs-symptoms-coded");
    await btnByLabel(dialog, /^confirm situation a$/i).click();

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/irritable bowel/i).first()).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "05-wizard-review-live-preview");

    // -- Suggest: ovarian cancer tests --------------------------------
    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "06-suggest-uncoded-action");

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
    await shot(page, "07-suggest-ovarian-tests");

    await btnByLabel(dialog, /^Next/i).click();

    // -- Save / sign-off ----------------------------------------------
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(/saved, but not live yet/i)).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "08-save-before-after-preview");

    await dialog
      .getByLabel(/why are you changing this rule/i)
      .fill(
        "Walkthrough: coded NG12 1.5.5 age/sex + IBS-suggestive symptoms, no sex-phrase split.",
      );
    await shot(page, "09-save-reason-filled");

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
