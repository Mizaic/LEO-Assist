import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Guided Step 3 per-pathway age/sex -- women vs men situations.
 * Atlas: DI-42246DA7 / DO-F8C56339
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;

const LEAD =
  "Consider referral for people with: ";
const ITEM_A = "women with unexplained weight loss";
const ITEM_B = "men with unexplained weight loss";
const TEXT = `${LEAD}${ITEM_A} or ${ITEM_B}.`;

const STRUCTURE = {
  items: [
    {
      text: ITEM_A,
      start: LEAD.length,
      end: LEAD.length + ITEM_A.length,
    },
    {
      text: ITEM_B,
      start: LEAD.length + ITEM_A.length + " or ".length,
      end: LEAD.length + ITEM_A.length + " or ".length + ITEM_B.length,
    },
  ],
};

const RULE = {
  rule_id: "e2e-per-pathway-demo-01",
  name: "E2E -- per-pathway sex gates",
  status: "pending_review",
  strength: "SHOULD",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: TEXT,
  recommendation_structure: STRUCTURE,
  plain_english: "Two situations with different sex gates.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "OR",
        children: [
          { kind: "AND", pathway_key: "pw_a", children: [] },
          { kind: "AND", pathway_key: "pw_b", children: [] },
        ],
      },
    ],
  },
  action: {
    snomed_concept_id: "168537006",
    preferred_term: "Referral for further investigation",
    semantic_tag: "procedure",
  },
  has_predecessor: false,
  updated_at: "2026-07-01T09:00:00Z",
};

const SEARCH_HITS: Record<
  string,
  Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>
> = {
  weight: [
    { snomed_concept_id: "89362005", term: "Weight loss", semantic_tag: "finding" },
  ],
};

async function installFixtures(page: Page) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([RULE]),
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
      body: JSON.stringify({ rule_id: RULE.rule_id }),
    }),
  );
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const key = Object.keys(SEARCH_HITS).find((prefix) => q.includes(prefix));
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(key ? SEARCH_HITS[key] : []),
    });
  });
}

async function openEditDialog(page: Page) {
  await installFixtures(page);
  await page.goto("/admin/knowledge?tab=clinical-guidelines");
  await page.waitForLoadState("load");
  await page
    .getByRole("button", { name: /skip the guideline builder intro animation/i })
    .click({ timeout: 3000 })
    .catch(() => {});
  await page.locator("#rule-review").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: `Toggle rule from ${RULE.guideline_id}` }).click();
  await page.getByRole("button", { name: `Edit rule ${RULE.rule_id}` }).click();
  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
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
  expect(blockers, JSON.stringify(blockers.map((v) => v.id))).toEqual([]);
}

async function pickWeightLoss(page: Page, dialog: ReturnType<Page["getByRole"]>) {
  await dialog.getByRole("button", { name: /unexplained weight loss/i }).click();
  const search = page.getByLabel("Search clinical terms");
  await expect(search).toBeVisible();
  await search.fill("weight");
  await page.getByRole("button", { name: /Use Weight loss/i }).click();
}

test.describe("Per-pathway demographics (DI-42246DA7)", () => {
  test("adds female to situation A and male to situation B without lifting to global", async ({
    page,
  }) => {
    const dialog = await openEditDialog(page);

    await expect(dialog.getByText("Always true")).toBeVisible();
    await dialog.getByRole("button", { name: "No, nothing else" }).click();

    await expect(dialog.getByText(/the guideline lists 2 situations/i)).toBeVisible();
    await dialog.getByRole("button", { name: "Looks right, continue" }).click();

    await expect(dialog.getByText(/situation a \(1 of 2\)/i)).toBeVisible();
    await expect(dialog.getByTestId("pathway-demographics-panel")).toBeVisible();
    await runAxeAndAssertClean(page);

    await dialog.getByRole("button", { name: /add a sex check for this situation only/i }).click();
    await expect(dialog.getByLabel("Which sex")).toHaveText(/female/i);
    await pickWeightLoss(page, dialog);
    await dialog.getByRole("button", { name: /^confirm situation a/i }).click();

    await expect(dialog.getByText(/situation b \(2 of 2\)/i)).toBeVisible();
    await dialog.getByRole("button", { name: /add a sex check for this situation only/i }).click();
    await dialog.getByLabel("Which sex").click();
    await page.getByRole("option", { name: /^Male$/i }).click();
    await pickWeightLoss(page, dialog);
    await dialog.getByRole("button", { name: /^confirm situation b$/i }).click();

    await expect(dialog.getByTestId("wizard-review")).toBeVisible();
    const preview = dialog.getByRole("region", { name: /live preview of this rule/i });
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/female/i)).toBeVisible();
    await expect(preview.getByText(/male/i)).toBeVisible();
    await expect(preview.getByText(/weight loss/i)).toBeVisible();
  });
});
