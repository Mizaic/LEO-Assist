/**
 * Fixtures and UI helpers for VAL-8672AC7E action-group validation.
 */
import { expect, type Locator, type Page } from "@playwright/test";

export const SEARCH_HITS: Record<
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
  "computed tomography": [
    {
      snomed_concept_id: "419394006",
      term: "Computed tomography of abdomen and pelvis",
      semantic_tag: "procedure",
    },
  ],
  "fast track referral": [
    {
      snomed_concept_id: "38661000000100",
      term: "Fast track referral",
      semantic_tag: "procedure",
    },
  ],
  "non-specific": [
    {
      snomed_concept_id: "1556551000000104",
      term: "Fast track referral for suspected cancer due to non-site-specific symptoms",
      semantic_tag: "procedure",
    },
  ],
};

export type DecisionAction = {
  strength?: string;
  group_id?: string;
  group_mode?: string;
  group_rank?: number;
  criterion?: { snomed_concept_id?: string; preferred_term?: string };
};

export type DecisionBody = {
  action?: string;
  updates?: { priority?: string; actions?: DecisionAction[] };
};

export type RuleFixture = {
  rule_id: string;
  name: string;
  status: string;
  strength: string;
  schema_version: number;
  guideline_id: string;
  guideline_version: number;
  chapter_title: string;
  recommendation_text: string;
  plain_english: string;
  present_criteria: unknown[];
  absent_criteria: unknown[];
  logic_tree: Record<string, unknown>;
  action: {
    snomed_concept_id: string;
    preferred_term: string;
    semantic_tag: string;
  };
  has_predecessor: boolean;
  updated_at: string;
};

export const FALLBACK_RULE: RuleFixture = {
  rule_id: "val-ng12-1-2-5-action-groups",
  name: "NG12 1.2.5 -- CT or ultrasound if CT unavailable",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text:
    "1.2.5 Consider an urgent, direct access CT scan, or an urgent, " +
    "direct access ultrasound scan if CT is not available, to assess " +
    "for pancreatic cancer in people aged 60 and over with weight loss.",
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

export const EITHER_OR_RULE: RuleFixture = {
  rule_id: "val-ng12-1-13-2-action-groups",
  name: "NG12 1.13.2 -- unexplained weight loss NSS triad",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text:
    "1.13.2 For people aged 60 and over with unexplained weight loss: " +
    "offer urgent investigation, or a suspected cancer pathway referral, " +
    "or a non-specific symptoms pathway referral.",
  plain_english:
    "Age 60+ with unexplained weight loss: offer urgent investigation, 2WW, or NSS.",
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

export async function installFixtures(
  page: Page,
  rule: RuleFixture,
  captured: { decision: DecisionBody | null },
) {
  await page.unrouteAll({ behavior: "ignoreErrors" });
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

export function btnByLabel(root: Locator, label: string | RegExp): Locator {
  return root.getByRole("button").filter({ hasText: label });
}

export async function pickProcedure(
  page: Page,
  _dialog: Locator,
  query: string,
  useLabel: RegExp,
) {
  // ChipSearchPopover renders in a portal outside the dialog subtree.
  const search = page.getByLabel(/search clinical terms/i);
  await expect(search).toBeVisible({ timeout: 10000 });

  const searchResponse = page.waitForResponse(
    (resp) =>
      resp.url().includes("/api/terminology/search") &&
      resp.request().method() === "GET" &&
      resp.ok(),
  );
  await search.fill(query);
  await searchResponse;

  const useBtn = page.getByRole("button", { name: useLabel });
  await expect(useBtn).toBeVisible({ timeout: 15000 });
  await useBtn.click();
}

export async function openProcedurePicker(dialog: Locator) {
  await dialog.getByLabel(/no procedure picked yet\. click to pick/i).click();
}

export async function openEditDialog(
  page: Page,
  rule: RuleFixture,
): Promise<Locator> {
  await page.goto("/admin/knowledge?tab=clinical-guidelines");
  await page.waitForLoadState("load");
  await dismissSplash(page);

  const reviewTab = page.getByTestId("segmented-tab-review");
  if (await reviewTab.isVisible().catch(() => false)) {
    await reviewTab.click();
  }
  await expect(page.getByTestId("rule-pool-pending")).toBeVisible({
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
  await page.getByRole("button", { name: `Edit rule ${rule.rule_id}` }).click({
    timeout: 5000,
  }).catch(async () => {
    await page.getByRole("button", { name: /^Edit$/ }).click();
  });

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  return dialog;
}

export async function goToSuggest(dialog: Locator) {
  const suggestStep = dialog.getByRole("button", {
    name: /step (?:2 of 3|3 of 4): what should the system suggest/i,
  });
  await suggestStep.click();
  await expect(
    dialog.getByRole("heading", { name: /what should the system suggest/i }),
  ).toBeVisible({ timeout: 15000 });
}

export async function setStrength(
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
