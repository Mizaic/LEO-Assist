/**
 * End-to-end walkthrough: build NG12 recommendation 1.7.6 (consider
 * 2WW for BCC-suspicious lesion when delay would matter) via Ask LEO.
 *
 * Peels to two AND rows (lesion suspicion + delay concern). Both are
 * vague; Ask LEO interprets them into SNOMED codes before Suggest.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-7-6-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-7-6");

const REC_TEXT =
  "1.7.6 Only consider a suspected cancer pathway referral for people " +
  "with a skin lesion that raises the suspicion of a basal cell " +
  "carcinoma if there is particular concern that a delay may have a " +
  "significant impact, because of factors such as lesion site or size. [2015]";

const BCC_ROW =
  "skin lesion that raises the suspicion of a basal cell carcinoma";
const DELAY_ROW =
  "particular concern that a delay may have a significant impact";

const BCC_TERMS = [
  "basal cell carcinoma of skin",
  "suspected basal cell carcinoma",
] as const;

const DELAY_TERMS = [
  "delay in treatment may be harmful",
  "clinically urgent",
] as const;

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "basal cell carcinoma of skin": [
    {
      snomed_concept_id: "254701007",
      term: "Basal cell carcinoma of skin",
      semantic_tag: "disorder",
    },
  ],
  "suspected basal cell carcinoma": [
    {
      snomed_concept_id: "274142008",
      term: "Basal cell carcinoma suspected",
      semantic_tag: "situation",
    },
  ],
  "delay in treatment may be harmful": [
    {
      snomed_concept_id: "161590003",
      term: "H/O: delayed treatment",
      semantic_tag: "situation",
    },
  ],
  "clinically urgent": [
    {
      snomed_concept_id: "103323008",
      term: "Urgent clinical concern",
      semantic_tag: "finding",
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
  rule_id: "e2e-ng12-1-7-6-walkthrough",
  name: "NG12 1.7.6 -- BCC delay concern (Ask LEO walkthrough)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Consider 2WW for BCC-suspicious lesions when delay would matter.",
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
    actions?: Array<{
      strength?: string;
      criterion?: { snomed_concept_id?: string };
    }>;
    logic_tree?: {
      kind?: string;
      children?: Array<{
        kind?: string;
        criterion?: { snomed_concept_id?: string };
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
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    if (
      q.includes("raises the suspicion") ||
      q.includes("particular concern that")
    ) {
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
    const raw = route.request().postData();
    const body = raw ? (JSON.parse(raw) as { phrase?: string }) : {};
    const phrase = (body.phrase ?? "").toLowerCase();
    const terms = phrase.includes("delay") || phrase.includes("concern")
      ? [...DELAY_TERMS]
      : [...BCC_TERMS];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        terms,
        reason: "stubbed for NG12 1.7.6 Ask LEO walkthrough",
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

async function askLeoForRow(
  page: Page,
  dialog: Locator,
  rowText: string,
  expectedTerms: readonly string[],
  shotPrefix: string,
) {
  const row = dialog
    .getByTestId(/^list-row-/)
    .filter({ hasText: rowText })
    .first();
  await expect(row).toBeVisible({ timeout: 10000 });
  await row.scrollIntoViewIfNeeded();
  await row.click();

  await expect(page.getByText(/No clinical terms match/i)).toBeVisible({
    timeout: 15000,
  });
  await shot(page, `${shotPrefix}-no-results`);
  await page.getByRole("button", { name: /Ask LEO for ideas/i }).click();

  const askDialog = page.getByRole("dialog", { name: /Ask LEO for ideas/i });
  await expect(askDialog).toBeVisible({ timeout: 10000 });
  for (const term of expectedTerms) {
    await expect(askDialog.getByText(term, { exact: true })).toBeVisible();
  }
  await shot(page, `${shotPrefix}-tick-terms`);
  await askDialog.getByRole("button", { name: /Look up ticked terms/i }).click();
  await expect(
    askDialog.getByRole("button", { name: /Add the matched clinical terms/i }),
  ).toBeEnabled({ timeout: 15000 });
  await shot(page, `${shotPrefix}-resolved`);
  await askDialog
    .getByRole("button", { name: /Add the matched clinical terms/i })
    .click();
  await expect(askDialog).toBeHidden({ timeout: 10000 });
  await expect(row).toHaveAttribute("data-resolved", "true", {
    timeout: 10000,
  });
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
  await expect(dialog.getByTestId("highlight-wizard")).toBeVisible({
    timeout: 10000,
  });
  return dialog;
}

test.describe("NG12 1.7.6 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.7.6 via Ask LEO on BCC + delay-concern rows", async ({
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
    await shot(page, "03-situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByTestId(/^list-row-/).filter({ hasText: BCC_ROW }),
    ).toBeVisible();
    await expect(
      dialog.getByTestId(/^list-row-/).filter({ hasText: DELAY_ROW }),
    ).toBeVisible();
    await shot(page, "04-two-and-rows");

    await askLeoForRow(page, dialog, BCC_ROW, BCC_TERMS, "05-bcc");
    await askLeoForRow(page, dialog, DELAY_ROW, DELAY_TERMS, "06-delay");
    await runAxeDialog(page);
    await shot(page, "07-both-rows-coded");
    await btnByLabel(dialog, /^confirm situation a$/i).click();

    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    await shot(page, "08-wizard-review");

    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await shot(page, "09-suggest-uncoded-action");

    await dialog
      .getByRole("button", {
        name: /no procedure picked yet\. click to pick/i,
      })
      .click();
    const search = dialog.getByLabel(/search clinical terms/i);
    await expect(search).toBeVisible({ timeout: 10000 });
    await search.fill("skin cancer");
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
      .getByRole("option", { name: /Think about this test or referral/i })
      .click();
    await shot(page, "10-suggest-consider-2ww");

    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await dialog
      .getByLabel(/why are you changing this rule/i)
      .fill(
        "Walkthrough: Ask LEO coded NG12 1.7.6 BCC suspicion + delay concern.",
      );
    await shot(page, "11-save-reason-filled");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    const ids = (captured.decision?.updates?.logic_tree?.children ?? [])
      .filter((c) => c.kind === "CONCEPT")
      .map((c) => c.criterion?.snomed_concept_id);
    expect(ids).toEqual(
      expect.arrayContaining([
        "254701007",
        "274142008",
        "161590003",
        "103323008",
      ]),
    );
    expect(ids).toHaveLength(4);
    expect(
      captured.decision?.updates?.actions?.[0]?.criterion?.snomed_concept_id,
    ).toBe("276281000000104");
    expect(captured.decision?.updates?.actions?.[0]?.strength).toBe("consider");
  });
});
