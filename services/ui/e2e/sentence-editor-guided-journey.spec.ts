import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Guided rule-edit journey for the Simple sentence canvas (SentenceEditor).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Drives a real reviewer path through the Edit-rule dialog -- expand a
 * pending rule, land on the Simple sentence canvas, build a two-condition
 * nested rule purely through the fill-in-the-blank prose canvas
 * (search-and-pick a symptom, add a nested "any of these" group,
 * search-and-pick a second symptom), and confirm the Advanced tree view
 * renders the exact same structure. Runs an axe-core WCAG 2.1 AA pass at
 * the empty state and again once the rule has been built.
 *
 * The Simple/Advanced view-mode toggle only renders once the logic tree
 * is non-empty (Step1Who.tsx shows a mode-specific empty state below the
 * toggle otherwise), so every test seeds the `leo.editRuleDialog.viewMode`
 * localStorage key before navigating rather than clicking a toggle that
 * may not exist yet.
 *
 * All backend calls are intercepted with route stubs so the spec runs in
 * CI without a live API, matching the pattern established by
 * val-guideline-workflow-1963da04.spec.ts.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;

const EMPTY_RULE = {
  rule_id: "e2e-simple-canvas-01",
  name: "E2E -- Simple canvas guided journey (empty)",
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

const PREFILLED_RULE = {
  ...EMPTY_RULE,
  rule_id: "e2e-simple-canvas-02",
  name: "E2E -- Simple canvas guided journey (prefilled)",
  guideline_id: "NG84",
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "CONCEPT",
        criterion: { snomed_concept_id: "43364001", preferred_term: "Upper abdominal pain" },
      },
    ],
  },
};

const SEARCH_HITS: Record<string, Array<{ snomed_concept_id: string; term: string; semantic_tag: string }>> = {
  abdo: [{ snomed_concept_id: "43364001", term: "Upper abdominal pain", semantic_tag: "finding" }],
  nause: [{ snomed_concept_id: "422587007", term: "Nausea", semantic_tag: "finding" }],
};

async function installEditDialogFixtures(page: Page) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([EMPTY_RULE, PREFILLED_RULE]),
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

/** Seeds the reviewer's Simple/Advanced preference before the app boots,
 *  since useViewMode() only reads localStorage in a post-mount effect. */
async function seedViewMode(page: Page, mode: "simple" | "advanced") {
  await page.addInitScript(
    ([key, value]) => {
      try {
        window.localStorage.setItem(key, value);
      } catch {
        // Private browsing / storage quota -- the test proceeds with the
        // in-memory default instead of a persisted preference.
      }
    },
    ["leo.editRuleDialog.viewMode", mode],
  );
}

/** Opens the guidance admin page, dismisses the first-visit splash if
 *  shown, expands the named rule's card, and opens the Edit-rule dialog. */
async function openEditDialog(
  page: Page,
  rule: { rule_id: string; guideline_id: string },
) {
  await installEditDialogFixtures(page);
  await page.goto("/admin/knowledge?tab=clinical-guidelines");
  await page.waitForLoadState("load");

  await page
    .getByRole("button", { name: /skip the guideline builder intro animation/i })
    .click({ timeout: 3000 })
    .catch(() => {});

  await page.locator("#rule-review").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: `Toggle rule from ${rule.guideline_id}` }).click();
  await page.getByRole("button", { name: `Edit rule ${rule.rule_id}` }).click();

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("heading", { name: "Who is this rule about?" })).toBeVisible();
  return dialog;
}

/** Scopes the axe scan to the Edit-rule dialog only. The rest of the
 *  guidance page sits behind the modal backdrop and is out of scope for
 *  this feature; auditing it here would fail on pre-existing issues
 *  unrelated to the Simple sentence canvas. */
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

/** Uses the concept search popover opened by clicking `trigger` to pick
 *  the hit registered under `searchPrefix` in SEARCH_HITS. */
async function searchAndPick(page: Page, trigger: () => Promise<void>, searchPrefix: string) {
  await trigger();
  const searchInput = page.getByLabel("Search clinical terms");
  await expect(searchInput).toBeVisible();
  await searchInput.fill(searchPrefix);
  const hit = SEARCH_HITS[searchPrefix][0];
  await page.getByRole("button", { name: `Use ${hit.term}` }).click();
  await expect(searchInput).toBeHidden();
}

test.describe("Simple sentence canvas guided journey (DI-42246DA7)", () => {
  test("empty rule opens on the Simple canvas with a plain-English empty state and zero axe blockers", async ({
    page,
  }) => {
    await seedViewMode(page, "simple");
    const dialog = await openEditDialog(page, EMPTY_RULE);

    await expect(dialog.getByRole("status", { name: "This rule is empty" })).toBeVisible();
    await expect(dialog.getByText("This rule doesn\u2019t check anything yet.")).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Add the first symptom, sign, procedure, or situation to this rule" }),
    ).toBeVisible();

    await runAxeAndAssertClean(page);
  });

  test("builds a nested two-condition rule entirely via the Simple canvas and mirrors it in Advanced view", async ({
    page,
  }) => {
    await seedViewMode(page, "simple");
    const dialog = await openEditDialog(page, EMPTY_RULE);

    // -- Add the first symptom from the empty state. AddInlineLinks sets an
    // aria-label that overrides the visible "+ add the first symptom" text,
    // so the accessible name to match on is the aria-label. The search
    // popover portals to document.body (outside the dialog), so its
    // trigger click stays dialog-scoped but the popover itself is queried
    // page-wide inside searchAndPick().
    await searchAndPick(
      page,
      () =>
        dialog
          .getByRole("button", { name: "Add the first symptom, sign, procedure, or situation to this rule" })
          .click(),
      "abdo",
    );
    // Matches the ConceptPill chip's exact accessible name -- a plain
    // substring match would also hit the dialog header's echo of the
    // fixture's recommendation_text and the pill's own "Edit synonyms"
    // button, both of which also contain "Upper abdominal pain".
    await expect(
      dialog.getByRole("button", { name: "Upper abdominal pain. Click to swap, X to remove." }),
    ).toBeVisible();

    const rootGroup = dialog.getByRole("group", { name: "Patient must have ALL of these" });
    await expect(rootGroup).toBeVisible();

    // -- Now that the tree is non-empty, the Simple/Advanced toggle appears.
    await expect(dialog.getByTestId("segmented-tab-simple")).toHaveAttribute("aria-selected", "true");

    // -- Add a nested "any of these" group under the root.
    await rootGroup
      .getByRole("button", { name: "Add a condition group, for example a set of options where any one match is enough" })
      .click();
    const nestedGroup = dialog.getByRole("group", { name: "Patient must have ANY of these" });
    await expect(nestedGroup).toBeVisible();

    // -- Add a second symptom inside the nested group. Scoped to
    // nestedGroup because the un-overridden "add concept" aria-label
    // ("Add a symptom, sign, procedure, or situation") is shared with the
    // root group's own add-link.
    await searchAndPick(
      page,
      () => nestedGroup.getByRole("button", { name: "Add a symptom, sign, procedure, or situation" }).click(),
      "nause",
    );
    await expect(nestedGroup.getByText("Nausea")).toBeVisible();

    await runAxeAndAssertClean(page);

    // -- Switch to Advanced and confirm the exact same tree renders there.
    await dialog.getByTestId("segmented-tab-advanced").click();
    const treeEditor = dialog.getByTestId("logic-tree-editor");
    await expect(treeEditor).toBeVisible();
    await expect(
      treeEditor.getByRole("button", { name: "Upper abdominal pain. Click to swap, X to remove." }),
    ).toBeVisible();
    await expect(treeEditor.getByText("Patient must have ALL of these")).toBeVisible();
    await expect(treeEditor.getByText("Patient must have ANY of these")).toBeVisible();
    await expect(treeEditor.getByRole("button", { name: "Nausea. Click to swap, X to remove." })).toBeVisible();
  });

  test("Simple/Advanced toggle is fully keyboard-operable on a rule that already has conditions", async ({
    page,
  }) => {
    await seedViewMode(page, "simple");
    const dialog = await openEditDialog(page, PREFILLED_RULE);

    const simpleTab = dialog.getByTestId("segmented-tab-simple");
    const advancedTab = dialog.getByTestId("segmented-tab-advanced");
    await expect(simpleTab).toHaveAttribute("aria-selected", "true");
    await expect(dialog.getByTestId("sentence-editor")).toBeVisible();

    await simpleTab.focus();
    await page.keyboard.press("ArrowRight");
    await expect(advancedTab).toBeFocused();

    await page.keyboard.press("Enter");
    await expect(advancedTab).toHaveAttribute("aria-selected", "true");
    await expect(dialog.getByTestId("logic-tree-editor")).toBeVisible();

    await page.keyboard.press("ArrowLeft");
    await expect(simpleTab).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(simpleTab).toHaveAttribute("aria-selected", "true");
    await expect(dialog.getByTestId("sentence-editor")).toBeVisible();
  });
});
