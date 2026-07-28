/**
 * End-to-end walkthrough: build NG12 recommendation 1.7.2 (melanoma
 * referral when dermoscopy suggests melanoma) in the guided
 * EditRuleDialog.
 *
 * The clinical clause is too vague for a direct SNOMED hit. The
 * reviewer uses "Ask LEO for ideas" to interpret the phrase into
 * concrete terms, resolve them to codes, then suggests a 2WW skin
 * cancer referral.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-7-2-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-7-2");

const REC_TEXT =
  "1.7.2 Refer people using a suspected cancer pathway referral if " +
  "dermoscopy suggests melanoma of the skin. [2015]";

const CLINICAL_ROW = "dermoscopy suggests melanoma of the skin";

const ASK_LEO_TERMS = [
  "melanoma of skin",
  "suspected melanoma",
  "dermoscopy of skin",
] as const;

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "melanoma of skin": [
    {
      snomed_concept_id: "372244006",
      term: "Malignant melanoma of skin",
      semantic_tag: "disorder",
    },
  ],
  "suspected melanoma": [
    {
      snomed_concept_id: "313299006",
      term: "Suspected melanoma of skin",
      semantic_tag: "situation",
    },
  ],
  "dermoscopy of skin": [
    {
      snomed_concept_id: "241077003",
      term: "Dermatoscopy of skin",
      semantic_tag: "procedure",
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

const RULE = {
  rule_id: "e2e-ng12-1-7-2-walkthrough",
  name: "NG12 1.7.2 -- dermoscopy suggests melanoma (Ask LEO walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Refer on a suspected cancer pathway when dermoscopy suggests melanoma.",
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

type DecisionBody = {
  action?: string;
  updates?: {
    priority?: string;
    due_days?: number | null;
    actions?: Array<{
      strength?: string;
      criterion?: { snomed_concept_id?: string };
    }>;
    logic_tree?: {
      kind?: string;
      children?: Array<{
        kind?: string;
        criterion?: { snomed_concept_id?: string; preferred_term?: string };
      }>;
    };
  };
};

async function installFixtures(
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
  // Vague dermoscopy phrase must miss so Ask LEO appears; resolved
  // Ask LEO terms and the referral action still hit SEARCH_HITS.
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    if (q.includes("dermoscopy suggests")) {
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
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        terms: [...ASK_LEO_TERMS],
        reason: "stubbed for NG12 1.7.2 Ask LEO walkthrough",
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

test.describe("NG12 1.7.2 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.7.2 via Ask LEO interpretation of dermoscopy phrase", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page);

    await expect(dialog.getByText("Always true")).toBeVisible();
    await runAxeDialog(page);
    await shot(page, "02-who-always-true");
    await btnByLabel(dialog, /No, nothing else/i).click();

    await expect(
      dialog.getByText(/couldn't find more than one situation/i),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "03-situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    const row = dialog
      .getByTestId(/^list-row-/)
      .filter({ hasText: CLINICAL_ROW })
      .first();
    await expect(row).toBeVisible({ timeout: 10000 });
    await shot(page, "04-vague-dermoscopy-row");
    await row.click();

    await expect(page.getByText(/No clinical terms match/i)).toBeVisible({
      timeout: 15000,
    });
    const askLeo = page.getByRole("button", { name: /Ask LEO for ideas/i });
    await expect(askLeo).toBeVisible();
    await shot(page, "05-search-no-results-ask-leo");
    await askLeo.click();

    const askDialog = page.getByRole("dialog", { name: /Ask LEO for ideas/i });
    await expect(askDialog).toBeVisible({ timeout: 10000 });
    for (const term of ASK_LEO_TERMS) {
      await expect(askDialog.getByText(term, { exact: true })).toBeVisible();
    }
    await shot(page, "06-ask-leo-tick-terms");
    await askDialog.getByRole("button", { name: /Look up ticked terms/i }).click();

    await expect(
      askDialog.getByText(/Malignant melanoma of skin/i),
    ).toBeVisible({ timeout: 15000 });
    await expect(
      askDialog.getByText(/Suspected melanoma of skin/i),
    ).toBeVisible();
    await expect(askDialog.getByText(/Dermatoscopy of skin/i)).toBeVisible();
    await shot(page, "07-ask-leo-resolved-codes");
    await askDialog
      .getByRole("button", { name: /Add the matched clinical terms/i })
      .click();
    await expect(askDialog).toBeHidden({ timeout: 10000 });

    await expect(row).toHaveAttribute("data-resolved", "true", {
      timeout: 10000,
    });
    await runAxeDialog(page);
    await shot(page, "08-dermoscopy-row-coded");
    await btnByLabel(dialog, /^confirm situation a$/i).click();

    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    await runAxeDialog(page);
    await shot(page, "09-wizard-review-live-preview");

    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await shot(page, "10-suggest-uncoded-action");

    await dialog
      .getByRole("button", {
        name: /no procedure picked yet\. click to pick/i,
      })
      .click();
    const search = dialog.getByLabel(/search clinical terms/i);
    await expect(search).toBeVisible({ timeout: 10000 });
    await search.fill("melanoma");
    await page
      .getByRole("button", {
        name: /Use Fast track referral for suspected skin cancer/i,
      })
      .click({ timeout: 15000 });

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await page.getByRole("option", { name: /2 week wait/i }).click();
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await page
      .getByRole("option", { name: /offer this test or referral/i })
      .click();
    await shot(page, "11-suggest-skin-cancer-referral");

    await btnByLabel(dialog, /^Next/i).click();

    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "12-save-before-after-preview");

    await dialog
      .getByLabel(/why are you changing this rule/i)
      .fill(
        "Walkthrough: Ask LEO interpreted NG12 1.7.2 dermoscopy suggests melanoma into coded findings.",
      );
    await shot(page, "13-save-reason-filled");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    const children = captured.decision?.updates?.logic_tree?.children ?? [];
    const conceptIds = children
      .filter((c) => c.kind === "CONCEPT")
      .map((c) => c.criterion?.snomed_concept_id)
      .filter(Boolean);
    expect(conceptIds).toEqual(
      expect.arrayContaining([
        "372244006",
        "313299006",
        "241077003",
      ]),
    );
    expect(conceptIds).toHaveLength(3);
    expect(
      captured.decision?.updates?.actions?.[0]?.criterion?.snomed_concept_id,
    ).toBe("276281000000104");
    expect(captured.decision?.updates?.actions?.[0]?.strength).toBe("offer");
  });
});
