/**
 * End-to-end walkthrough: build NG12 recommendation 1.7.1 (melanoma
 * referral when weighted 7-point checklist score >= 3) in the guided
 * EditRuleDialog.
 *
 * Expands the companion weighted checklist into major/minor feature
 * rows, codes them, and confirms the tree reifies to
 * OR(AT_LEAST 2 majors | AND(1 maj, 1 min) | AT_LEAST 3 minors).
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-7-1-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-7-1");

const REC_TEXT =
  "1.7.1 Refer people using a suspected cancer pathway referral for melanoma " +
  "if they have a suspicious pigmented skin lesion with a weighted 7-point " +
  "checklist score of 3 or more. [2015]";

const COMPANION_PANELS = [
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

const FEATURES = [
  "suspicious pigmented skin lesion",
  "change in size",
  "irregular shape",
  "irregular colour",
  "largest diameter 7 mm or more",
  "inflammation",
  "oozing",
  "change in sensation",
] as const;

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
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

const RULE = {
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

type DecisionBody = {
  action?: string;
  updates?: {
    priority?: string;
    actions?: Array<{ strength?: string; criterion?: { snomed_concept_id?: string } }>;
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

async function pickFeatureRow(page: Page, dialog: Locator, feature: string) {
  const hits = SEARCH_HITS[feature];
  if (!hits?.[0]) throw new Error(`No SEARCH_HITS for ${feature}`);
  const hit = hits[0]!;
  const row = dialog
    .getByTestId(/^list-row-/)
    .filter({ hasText: feature })
    .first();
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

function findOrNode(node: DecisionBody["updates"]): {
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

test.describe("NG12 1.7.1 rule-build walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds 1.7.1 with expanded weighted checklist OR tree", async ({ page }) => {
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
    await expect(dialog.getByTestId("weighted-checklist-expand")).toBeVisible();
    await expect(
      dialog.getByRole("button", {
        name: /expand weighted checklist \(score at least 3\)/i,
      }),
    ).toBeVisible();
    await shot(page, "04-weighted-checklist-expand-offer");
    await dialog
      .getByRole("button", {
        name: /expand weighted checklist \(score at least 3\)/i,
      })
      .click();

    await expect(
      dialog.getByText(/major features \(3\) and minor features \(4\)/i),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "05-features-expanded");

    for (const feature of FEATURES) {
      await pickFeatureRow(page, dialog, feature);
    }
    await runAxeDialog(page);
    await shot(page, "06-all-features-coded");
    await btnByLabel(dialog, /^confirm situation a$/i).click();

    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    await runAxeDialog(page);
    await shot(page, "07-wizard-review-live-preview");

    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await shot(page, "08-suggest-uncoded-action");

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
    await shot(page, "09-suggest-skin-cancer-referral");

    await btnByLabel(dialog, /^Next/i).click();

    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "10-save-before-after-preview");

    await dialog
      .getByLabel(/why are you changing this rule/i)
      .fill(
        "Walkthrough: expanded NG12 1.7.1 weighted 7-point checklist into OR of AT_LEAST groups.",
      );
    await shot(page, "11-save-reason-filled");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    const scoreOr = findOrNode(captured.decision?.updates);
    expect(scoreOr).toBeTruthy();
    expect(scoreOr!.children).toHaveLength(3);
    expect(scoreOr!.children?.[0]?.kind).toBe("AT_LEAST");
    expect(scoreOr!.children?.[0]?.min).toBe(2);
    expect(scoreOr!.children?.[1]?.kind).toBe("AND");
    expect(scoreOr!.children?.[2]?.kind).toBe("AT_LEAST");
    expect(scoreOr!.children?.[2]?.min).toBe(3);
    expect(captured.decision?.updates?.actions?.[0]?.criterion?.snomed_concept_id).toBe(
      "276281000000104",
    );
    expect(captured.decision?.updates?.actions?.[0]?.strength).toBe("offer");
  });
});
