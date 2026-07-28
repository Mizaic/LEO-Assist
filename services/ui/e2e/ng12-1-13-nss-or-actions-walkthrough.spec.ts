/**
 * End-to-end walkthroughs: NG12 1.13.2 / 1.13.3 / 1.13.4
 * non-site-specific symptoms -- three-way either/or actions.
 *
 * NICE offers (or for 1.13.4, consider):
 *   urgent investigation, OR
 *   a suspected cancer pathway referral, OR
 *   a non-specific symptoms pathway referral.
 *
 * Exercises "Or instead, add..." on Suggest (Who trees are pre-seeded).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Run from services/ui:
 *   PLAYWRIGHT_BASE_URL=http://localhost:3017 PLAYWRIGHT_REUSE_SERVER=false \
 *     npx playwright test ng12-1-13-nss-or-actions-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_ROOT = path.join(__dirname, "screenshots");

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  "urgent investigation": [
    {
      snomed_concept_id: "183654001",
      term: "Urgent investigation",
      semantic_tag: "procedure",
    },
  ],
  urgent: [
    {
      snomed_concept_id: "183654001",
      term: "Urgent investigation",
      semantic_tag: "procedure",
    },
  ],
  "suspected cancer": [
    {
      snomed_concept_id: "276581000000102",
      term: "Fast track referral for suspected cancer",
      semantic_tag: "procedure",
    },
  ],
  "fast track": [
    {
      snomed_concept_id: "276581000000102",
      term: "Fast track referral for suspected cancer",
      semantic_tag: "procedure",
    },
  ],
  "non-specific": [
    {
      snomed_concept_id: "183519002",
      term: "Referral for non-specific symptoms assessment",
      semantic_tag: "procedure",
    },
  ],
  nss: [
    {
      snomed_concept_id: "183519002",
      term: "Referral for non-specific symptoms assessment",
      semantic_tag: "procedure",
    },
  ],
};

type DecisionAction = {
  strength?: string;
  group_id?: string;
  group_mode?: string;
  group_rank?: number;
  criterion?: { snomed_concept_id?: string };
};

type DecisionBody = {
  action?: string;
  updates?: { priority?: string; actions?: DecisionAction[] };
};

type Scenario = {
  recId: string;
  shotDir: string;
  ruleId: string;
  name: string;
  recommendationText: string;
  plainEnglish: string;
  logicTree: Record<string, unknown>;
  strengthLabel: RegExp;
  strengthValue: string;
  reason: string;
};

const SCENARIOS: Scenario[] = [
  {
    recId: "1.13.2",
    shotDir: "ng12-1-13-2",
    ruleId: "e2e-ng12-1-13-2-walkthrough",
    name: "NG12 1.13.2 -- unexplained weight loss NSS triad",
    recommendationText:
      "1.13.2 For people aged 60 and over with unexplained weight loss " +
      "(greater than 5% mean weight loss within a 6-month period), which " +
      "is a symptom of several cancers including colorectal, " +
      "gastro-oesophageal, lung, prostate, pancreatic and urological " +
      "cancer: carry out an assessment for additional symptoms, signs " +
      "or findings that may help to clarify which cancer is most likely, " +
      "and offer urgent investigation, or a suspected cancer pathway " +
      "referral, or a non-specific symptoms pathway referral. [2026]",
    plainEnglish:
      "Age 60+ with unexplained weight loss: offer urgent investigation, " +
      "2WW, or NSS pathway.",
    logicTree: {
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
    strengthLabel: /Offer this test or referral/i,
    strengthValue: "offer",
    reason:
      "Walkthrough: NG12 1.13.2 either/or urgent investigation, 2WW, or NSS.",
  },
  {
    recId: "1.13.3",
    shotDir: "ng12-1-13-3",
    ruleId: "e2e-ng12-1-13-3-walkthrough",
    name: "NG12 1.13.3 -- unexplained appetite loss NSS triad",
    recommendationText:
      "1.13.3 For people with unexplained appetite loss, which is a " +
      "symptom of several cancers including lung, oesophageal, stomach, " +
      "colorectal, pancreatic, bladder and renal cancer: carry out an " +
      "assessment for additional symptoms, signs or findings that may " +
      "help to clarify which cancer is most likely, and offer urgent " +
      "investigation, or a suspected cancer pathway referral, or a " +
      "non-specific symptoms pathway referral. [2015, amended 2026]",
    plainEnglish:
      "Unexplained appetite loss: offer urgent investigation, 2WW, or NSS.",
    logicTree: {
      node_id: "root",
      kind: "AND",
      children: [
        {
          node_id: "appetite",
          kind: "CONCEPT",
          criterion: {
            snomed_concept_id: "79890006",
            preferred_term: "Loss of appetite",
            semantic_tag: "finding",
          },
        },
      ],
    },
    strengthLabel: /Offer this test or referral/i,
    strengthValue: "offer",
    reason:
      "Walkthrough: NG12 1.13.3 either/or urgent investigation, 2WW, or NSS.",
  },
  {
    recId: "1.13.4",
    shotDir: "ng12-1-13-4",
    ruleId: "e2e-ng12-1-13-4-walkthrough",
    name: "NG12 1.13.4 -- DVT NSS triad (consider)",
    recommendationText:
      "1.13.4 For people with deep vein thrombosis, which is associated " +
      "with several cancers including urogenital, breast, colorectal and " +
      "lung cancer: carry out an assessment for additional symptoms, " +
      "signs or findings that may help to clarify which cancer is most " +
      "likely, and consider urgent investigation, or a suspected cancer " +
      "pathway referral, or a non-specific symptoms pathway referral. " +
      "[2015, amended 2026]",
    plainEnglish:
      "DVT: consider urgent investigation, 2WW, or NSS pathway.",
    logicTree: {
      node_id: "root",
      kind: "AND",
      children: [
        {
          node_id: "dvt",
          kind: "CONCEPT",
          criterion: {
            snomed_concept_id: "128053003",
            preferred_term: "Deep venous thrombosis",
            semantic_tag: "disorder",
          },
        },
      ],
    },
    strengthLabel: /Think about this test or referral/i,
    strengthValue: "consider",
    reason:
      "Walkthrough: NG12 1.13.4 either/or consider urgent investigation, 2WW, or NSS.",
  },
];

function buildRule(scenario: Scenario) {
  return {
    rule_id: scenario.ruleId,
    name: scenario.name,
    status: "pending_review",
    strength: "unspecified",
    schema_version: 2,
    guideline_id: "NG12",
    guideline_version: 1,
    chapter_title: "Chapter 1",
    recommendation_text: scenario.recommendationText,
    recommendation_structure: null,
    plain_english: scenario.plainEnglish,
    present_criteria: [],
    absent_criteria: [],
    logic_tree: scenario.logicTree,
    action: {
      snomed_concept_id: "",
      preferred_term: "",
      semantic_tag: "procedure",
    },
    has_predecessor: false,
    updated_at: "2026-07-01T09:00:00Z",
  };
}

async function installFixtures(
  page: Page,
  rule: ReturnType<typeof buildRule>,
  captured: { decision: DecisionBody | null },
) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([rule]),
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
      body: JSON.stringify({ rule_id: `${rule.rule_id}:edited` }),
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

async function shot(dir: string, page: Page, name: string) {
  await page.screenshot({
    path: path.join(dir, `${name}.png`),
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

async function openEditDialog(
  page: Page,
  rule: ReturnType<typeof buildRule>,
  dir: string,
): Promise<Locator> {
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
    .getByRole("button", { name: `Toggle rule from ${rule.guideline_id}` })
    .click();
  await shot(dir, page, "01-review-pool-card");
  await page.getByRole("button", { name: `Edit rule ${rule.rule_id}` }).click();

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function setStrength(
  page: Page,
  dialog: Locator,
  index: number,
  label: RegExp,
) {
  const select = dialog.locator(`#edit-rule-action-strength-${index}`);
  await select.scrollIntoViewIfNeeded();
  await select.click();
  await page.getByRole("option", { name: label }).click();
}

async function buildNssEitherOr(
  page: Page,
  dialog: Locator,
  dir: string,
  scenario: Scenario,
) {
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
  await shot(dir, page, "02-suggest-uncoded");

  await dialog
    .getByRole("button", {
      name: /no procedure picked yet\. click to pick/i,
    })
    .click();
  await pickProcedure(
    page,
    dialog,
    "urgent investigation",
    /Use Urgent investigation/i,
  );
  await expect(
    dialog.getByRole("button", { name: /urgent investigation/i }),
  ).toBeVisible({ timeout: 10000 });
  await shot(dir, page, "03-urgent-investigation");

  await dialog
    .getByRole("button", {
      name: /Or instead, add another procedure after row 1/i,
    })
    .click();
  await expect(
    dialog.getByText(/Suggest either of these/i),
  ).toBeVisible({ timeout: 10000 });
  await pickProcedure(
    page,
    dialog,
    "suspected cancer",
    /Use Fast track referral for suspected cancer/i,
  );
  await expect(
    dialog.getByRole("button", {
      name: /fast track referral for suspected cancer/i,
    }),
  ).toBeVisible({ timeout: 10000 });
  await shot(dir, page, "04-two-alternatives");

  await dialog
    .getByRole("button", {
      name: /Or instead, add another procedure after row 2/i,
    })
    .click();
  await pickProcedure(
    page,
    dialog,
    "non-specific",
    /Use Referral for non-specific symptoms assessment/i,
  );
  await expect(
    dialog.getByRole("button", {
      name: /referral for non-specific symptoms assessment/i,
    }),
  ).toBeVisible({ timeout: 10000 });
  await shot(dir, page, "05-three-alternatives");

  for (let i = 0; i < 3; i++) {
    await setStrength(page, dialog, i, scenario.strengthLabel);
  }

  await expect(dialog.getByText(/, or /i).first()).toBeVisible({
    timeout: 10000,
  });
  await shot(dir, page, "06-live-preview-either-or");

  await btnByLabel(dialog, /^Next/i).click();
  await expect(
    dialog.getByRole("heading", { name: /save your change/i }),
  ).toBeVisible({ timeout: 10000 });
  await dialog
    .getByLabel(/why are you changing this rule/i)
    .fill(scenario.reason);
  await shot(dir, page, "07-save-reason");
  await btnByLabel(dialog, /approve and save/i).click();
  await expect(dialog).toBeHidden({ timeout: 15000 });
}

test.describe("NG12 1.13 NSS either/or action walkthroughs (DI-42246DA7)", () => {
  for (const scenario of SCENARIOS) {
    test(`builds ${scenario.recId} three-way either/or actions`, async ({
      page,
    }) => {
      test.setTimeout(240_000);
      const dir = path.join(SCREENSHOT_ROOT, scenario.shotDir);
      fs.mkdirSync(dir, { recursive: true });
      const rule = buildRule(scenario);
      const captured: { decision: DecisionBody | null } = { decision: null };
      await installFixtures(page, rule, captured);

      const dialog = await openEditDialog(page, rule, dir);
      await shot(dir, page, "01b-who-seeded");
      await buildNssEitherOr(page, dialog, dir, scenario);

      expect(captured.decision?.action).toBe("edit");
      const actions = captured.decision?.updates?.actions ?? [];
      expect(actions).toHaveLength(3);
      expect(actions.map((a) => a.criterion?.snomed_concept_id)).toEqual([
        "183654001",
        "276581000000102",
        "183519002",
      ]);
      expect(actions.every((a) => a.group_mode === "any")).toBe(true);
      expect(actions[0].group_id).toBeTruthy();
      expect(actions.every((a) => a.group_id === actions[0].group_id)).toBe(
        true,
      );
      expect(actions.map((a) => a.group_rank)).toEqual([0, 1, 2]);
      expect(actions.every((a) => a.strength === scenario.strengthValue)).toBe(
        true,
      );
    });
  }
});
