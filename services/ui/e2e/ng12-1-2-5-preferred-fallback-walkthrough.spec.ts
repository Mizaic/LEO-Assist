/**
 * End-to-end walkthrough: NG12 1.2.5 preferred-then-fallback actions.
 *
 * NICE: urgent direct-access CT, or urgent ultrasound if CT is not
 * available (pancreatic cancer assessment).
 *
 * Jumps to Suggest (Who tree is pre-seeded) and builds the CT -> US
 * chain with "If not available, add...".
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8672AC7E
 *
 * Run from services/ui:
 *   PLAYWRIGHT_BASE_URL=http://localhost:3017 PLAYWRIGHT_REUSE_SERVER=false \
 *     npx playwright test ng12-1-2-5-preferred-fallback-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-2-5");

const REC_TEXT =
  "1.2.5 Consider an urgent, direct access CT scan, or an urgent, " +
  "direct access ultrasound scan if CT is not available, to assess " +
  "for pancreatic cancer in people aged 60 and over with weight loss " +
  "and any of the following: diarrhoea, back pain, abdominal pain, " +
  "nausea, vomiting, constipation, new-onset diabetes. [2015]";

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "ct abdomen": [
    {
      snomed_concept_id: "419394006",
      term: "CT of abdomen and pelvis",
      semantic_tag: "procedure",
    },
  ],
  "ct of abdomen": [
    {
      snomed_concept_id: "419394006",
      term: "CT of abdomen and pelvis",
      semantic_tag: "procedure",
    },
  ],
  ultrasound: [
    {
      snomed_concept_id: "418394000",
      term: "Ultrasound scan of abdomen",
      semantic_tag: "procedure",
    },
  ],
  "ultrasound scan": [
    {
      snomed_concept_id: "418394000",
      term: "Ultrasound scan of abdomen",
      semantic_tag: "procedure",
    },
  ],
};

const RULE = {
  rule_id: "e2e-ng12-1-2-5-walkthrough",
  name: "NG12 1.2.5 -- CT or ultrasound if CT unavailable",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  plain_english:
    "Urgent CT for pancreatic cancer assessment; ultrasound if CT unavailable.",
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
        value: "60",
        unit: "years",
      },
      {
        node_id: "weight-loss",
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "89362005",
          preferred_term: "Weight loss",
          semantic_tag: "finding",
        },
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

type DecisionAction = {
  strength?: string;
  group_id?: string;
  group_mode?: string;
  group_rank?: number;
  criterion?: { snomed_concept_id?: string; preferred_term?: string };
};

type DecisionBody = {
  action?: string;
  updates?: {
    priority?: string;
    actions?: DecisionAction[];
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

async function pickProcedure(
  page: Page,
  dialog: Locator,
  query: string,
  useLabel: RegExp,
) {
  const search = dialog.getByLabel(/search clinical terms/i);
  await expect(search).toBeVisible({ timeout: 10000 });
  await search.fill(query);
  await page.getByRole("button", { name: useLabel }).click({ timeout: 15000 });
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
  return dialog;
}

test.describe("NG12 1.2.5 preferred-fallback walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("builds CT then ultrasound if CT not available", async ({ page }) => {
    test.setTimeout(240_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page);
    await shot(page, "02-who-seeded");

    await dialog
      .getByRole("button", {
        name: /step 2 of 3: what should the system suggest/i,
      })
      .click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await shot(page, "03-suggest-uncoded");

    await dialog
      .getByRole("button", {
        name: /no procedure picked yet\. click to pick/i,
      })
      .click();
    await pickProcedure(
      page,
      dialog,
      "ct abdomen",
      /Use CT of abdomen and pelvis/i,
    );
    await expect(
      dialog.getByRole("button", { name: /ct of abdomen and pelvis/i }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "04-ct-coded");

    await dialog
      .getByRole("button", {
        name: /If not available, add another procedure after row 1/i,
      })
      .click();
    await expect(
      dialog.getByText(/Prefer the first\. If it is not available/i),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "05-fallback-row-added");

    await pickProcedure(
      page,
      dialog,
      "ultrasound",
      /Use Ultrasound scan of abdomen/i,
    );
    await expect(
      dialog.getByRole("button", { name: /ultrasound scan of abdomen/i }),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "06-both-coded");

    const strength0 = dialog.locator("#edit-rule-action-strength-0");
    await strength0.scrollIntoViewIfNeeded();
    await strength0.click();
    await page
      .getByRole("option", { name: /Think about this test or referral/i })
      .click();
    const strength1 = dialog.locator("#edit-rule-action-strength-1");
    await strength1.scrollIntoViewIfNeeded();
    await strength1.click();
    await page
      .getByRole("option", { name: /Think about this test or referral/i })
      .click();

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await page.getByRole("option", { name: /^Urgent\b/i }).click();

    await expect(
      dialog.getByText(/If that is not available:/i),
    ).toBeVisible({ timeout: 10000 });
    await shot(page, "07-live-preview-fallback");

    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await dialog
      .getByLabel(/why are you changing this rule/i)
      .fill(
        "Walkthrough: NG12 1.2.5 CT preferred, ultrasound if CT not available.",
      );
    await shot(page, "08-save-reason");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision?.action).toBe("edit");
    const actions = captured.decision?.updates?.actions ?? [];
    expect(actions).toHaveLength(2);
    expect(actions[0].criterion?.snomed_concept_id).toBe("419394006");
    expect(actions[1].criterion?.snomed_concept_id).toBe("418394000");
    expect(actions[0].group_mode).toBe("preferred_fallback");
    expect(actions[1].group_mode).toBe("preferred_fallback");
    expect(actions[0].group_id).toBeTruthy();
    expect(actions[0].group_id).toBe(actions[1].group_id);
    expect(actions[0].group_rank).toBe(0);
    expect(actions[1].group_rank).toBe(1);
    expect(actions[0].strength).toBe("consider");
    expect(actions[1].strength).toBe("consider");
  });
});
