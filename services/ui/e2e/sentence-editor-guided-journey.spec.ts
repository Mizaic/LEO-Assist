import { test, expect, type Page } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";

/**
 * Empty-rule + Guided journey for the Edit-rule dialog.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Advanced tree mode is removed. Empty rules start from the empty
 * state; once a first criterion is added the highlight wizard takes
 * over. Runs axe WCAG 2.1 AA on the empty state.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;

const EMPTY_RULE = {
  rule_id: "e2e-guided-empty-01",
  name: "E2E -- Guided empty rule journey",
  status: "pending_review",
  strength: "SHOULD",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text:
    "Consider referral for people with upper abdominal pain, with nausea, and no clear cause found.",
  plain_english: "This rule does not check anything yet.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: null,
  action: {
    snomed_concept_id: "168537006",
    preferred_term: "Referral for further investigation",
    semantic_tag: "procedure",
  },
  has_predecessor: false,
  updated_at: "2026-07-01T09:00:00Z",
};

const SEARCH_HITS: Record<string, Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>> = {
  abdo: [{ snomed_concept_id: "43364001", term: "Upper abdominal pain", semantic_tag: "finding" }],
};

async function installEditDialogFixtures(page: Page) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([EMPTY_RULE]),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=active*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }),
  );
  await page.route("**/api/guidance/rules/review*status=superseded*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }),
  );
  await page.route("**/api/guidance/rules/review/*/decision", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rule_id: EMPTY_RULE.rule_id }),
    }),
  );
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const key = Object.keys(SEARCH_HITS).find((prefix) => q.startsWith(prefix));
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(key ? SEARCH_HITS[key] : []),
    });
  });
}

async function openEditDialog(page: Page) {
  await installEditDialogFixtures(page);
  await page.goto("/admin/knowledge?tab=clinical-guidelines");
  await page.waitForLoadState("load");

  await page
    .getByRole("button", { name: /skip the guideline builder intro animation/i })
    .click({ timeout: 3000 })
    .catch(() => {});

  await page.locator("#rule-review").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: `Toggle rule from ${EMPTY_RULE.guideline_id}` }).click();
  await page.getByRole("button", { name: `Edit rule ${EMPTY_RULE.rule_id}` }).click();

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("heading", { name: "Who is this rule about?" })).toBeVisible();
  return dialog;
}

async function runAxeAndAssertClean(page: Page) {
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
      blockers.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.map((n) => n.target).flat() })),
      null,
      2,
    ),
  ).toEqual([]);
}

test.describe("Guided empty-rule journey (DI-42246DA7)", () => {
  test("empty rule opens with a plain-English empty state and zero axe blockers", async ({
    page,
  }) => {
    const dialog = await openEditDialog(page);

    await expect(dialog.getByRole("status", { name: "This rule is empty" })).toBeVisible();
    await expect(dialog.getByText("What does this rule apply to?")).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Add the first symptom, sign, procedure, or situation to this rule" }),
    ).toBeVisible();

    await runAxeAndAssertClean(page);
  });

  test("adding the first symptom opens the highlight wizard", async ({ page }) => {
    const dialog = await openEditDialog(page);

    await dialog
      .getByRole("button", { name: "Add the first symptom, sign, procedure, or situation to this rule" })
      .click();
    const searchInput = page.getByLabel("Search clinical terms");
    await expect(searchInput).toBeVisible();
    await searchInput.fill("abdo");
    await page.getByRole("button", { name: "Use Upper abdominal pain" }).click();

    await expect(dialog.getByTestId("highlight-wizard")).toBeVisible();
    await expect(dialog.getByText(/what must always be true/i)).toBeVisible();
    await expect(dialog.getByText(/upper abdominal pain/i)).toBeVisible();
    await expect(dialog.getByTestId("logic-tree-editor")).toHaveCount(0);
    await expect(dialog.getByTestId("segmented-tabs")).toHaveCount(0);
  });
});
