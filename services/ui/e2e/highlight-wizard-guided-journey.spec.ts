import { test, expect, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Guided rule-edit journey for the highlight-to-build wizard, driven
 * against a fixture modelled on the real NG12 1.2.9 (upper GI
 * endoscopy) recommendation -- one age prerequisite, then a
 * structured 4-situation split, with two of those situations each
 * carrying their own nested "any of the following" cluster.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Drives every step type the wizard supports in one pass:
 *   Step 1 -- auto-anchors the existing age prerequisite, reviewer
 *             confirms "no, nothing else".
 *   Step 2 -- the guideline's own `recommendation_structure` (4 top
 *             level list items) is preferred over the ", or "-text
 *             heuristic; reviewer confirms "looks right".
 *   Step 3 -- repeated once per situation: two plain single-row
 *             situations (search-and-pick one concept each), then
 *             one situation with a single nested cluster confirmed as
 *             "only one needs to match" (AT_LEAST, lazily
 *             materializing a subgroup), then one situation with
 *             TWO clusters in the SAME situation -- a marker-less
 *             lead-or cluster ("nausea or vomiting") ANDed with a
 *             trailing "any of the following" cluster (weight loss,
 *             reflux) -- each graded independently (AT_LEAST for the
 *             lead cluster, AND for the trailing one), covering the
 *             exact real-world NG12 1.2.9 shape this feature exists
 *             for (see wizardMapping.ts's `PathwayRows.leadCluster`).
 *   Review -- the built tree hands off to the existing SentenceEditor
 *             canvas unchanged.
 *
 * Free-text-selection ("highlight more text") itself is exercised at
 * the component level by HighlightableRecommendationText's own
 * live-render tests and the wizard orchestrator's live-render tests
 * (HighlightWizard.test.tsx) -- this spec's job is the real-browser,
 * real-route, real-axe pass over the click-driven happy path, not a
 * second copy of that coverage.
 *
 * All backend calls are intercepted with route stubs so the spec runs
 * in CI without a live API, matching the pattern established by
 * sentence-editor-guided-journey.spec.ts.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;

interface FixtureItem {
  text: string;
  start: number;
  end: number;
  children?: FixtureItem[];
}

interface Fixture {
  text: string;
  leadText: string;
  items: FixtureItem[];
  trailingText: string;
}

/**
 * Builds the flattened recommendation text plus its structure items
 * by appending each piece in order and recording real offsets as we
 * go -- avoids hand-counted, fragile character positions.
 */
function buildNg12129Fixture(): Fixture {
  const leadText =
    "Consider non-urgent, direct access upper gastrointestinal endoscopy to assess for oesophageal cancer in people aged 55 or over with: ";
  const trailingText = " [2015]";

  let text = leadText;
  const append = (s: string) => {
    text += s;
  };
  const appendItem = (label: string): FixtureItem => {
    const start = text.length;
    append(label);
    return { text: label, start, end: text.length };
  };
  const appendChildren = (labels: string[]): FixtureItem[] => {
    return labels.map((label, i) => {
      if (i > 0) append(", ");
      return appendItem(label);
    });
  };

  const itemA = appendItem("treatment-resistant dyspepsia");
  append(" or ");
  const itemB = appendItem("upper abdominal pain with low haemoglobin levels");
  append(" or ");
  const itemC = appendItem("raised platelet count with any of the following");
  append(": ");
  const itemCChildren = appendChildren(["nausea", "vomiting"]);
  append(" or ");
  const itemD = appendItem("nausea or vomiting with any of the following");
  append(": ");
  const itemDChildren = appendChildren(["weight loss", "reflux"]);
  append(trailingText);

  return {
    text,
    leadText: leadText.trim(),
    trailingText: trailingText.trim(),
    items: [
      itemA,
      itemB,
      { ...itemC, children: itemCChildren },
      { ...itemD, children: itemDChildren },
    ],
  };
}

const FIXTURE = buildNg12129Fixture();

function ageLeaf() {
  return {
    node_id: "age",
    kind: "DEMOGRAPHIC",
    field: "age",
    operator: ">=",
    value: "55",
  };
}

const RULE = {
  rule_id: "e2e-highlight-wizard-ng12-129",
  name: "E2E -- Highlight wizard guided journey (NG12 1.2.9)",
  status: "pending_review",
  strength: "SHOULD",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: FIXTURE.text,
  recommendation_structure: {
    lead_text: FIXTURE.leadText,
    items: FIXTURE.items,
    trailing_text: FIXTURE.trailingText,
  },
  plain_english: "This rule checks for upper GI endoscopy referral criteria.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: { node_id: "root", kind: "AND", children: [ageLeaf()] },
  action: {
    snomed_concept_id: "112788007",
    preferred_term: "Endoscopic examination of upper gastrointestinal tract",
    semantic_tag: "procedure",
  },
  has_predecessor: false,
  updated_at: "2026-07-01T09:00:00Z",
};

/** Exact-match lookup: every row's `initialQuery` is deterministic
 *  (the row's own verbatim text), so the fixture stubs on exact
 *  equality rather than a startsWith prefix -- avoids any risk of
 *  one row's stub accidentally matching another row's search. */
const SEARCH_HITS: Record<
  string,
  { snomed_concept_id: string; term: string; semantic_tag: string }
> = {
  "treatment-resistant dyspepsia": {
    snomed_concept_id: "concept-a",
    term: "Treatment-resistant dyspepsia",
    semantic_tag: "finding",
  },
  "upper abdominal pain with low haemoglobin levels": {
    snomed_concept_id: "concept-b",
    term: "Upper abdominal pain with low haemoglobin",
    semantic_tag: "finding",
  },
  "raised platelet count": {
    snomed_concept_id: "concept-c-lead",
    term: "Raised platelet count",
    semantic_tag: "finding",
  },
  nausea: {
    snomed_concept_id: "concept-nausea",
    term: "Nausea",
    semantic_tag: "finding",
  },
  vomiting: {
    snomed_concept_id: "concept-vomiting",
    term: "Vomiting",
    semantic_tag: "finding",
  },
  "weight loss": {
    snomed_concept_id: "concept-weight-loss",
    term: "Weight loss",
    semantic_tag: "finding",
  },
  reflux: {
    snomed_concept_id: "concept-reflux",
    term: "Reflux",
    semantic_tag: "finding",
  },
};

async function installEditDialogFixtures(page: Page) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([RULE]) }),
  );
  await page.route("**/api/guidance/rules/review*status=active*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }),
  );
  await page.route("**/api/guidance/rules/review*status=superseded*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }),
  );
  await page.route("**/api/guidance/rules/review/*/decision", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ rule_id: RULE.rule_id }) }),
  );
  await page.route("**/api/terminology/prior-resolutions*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) }),
  );
  await page.route("**/api/terminology/search*", (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const hit = SEARCH_HITS[q];
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(hit ? [hit] : []) });
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
  await page.getByRole("button", { name: `Toggle rule from ${RULE.guideline_id}` }).click();
  await page.getByRole("button", { name: `Edit rule ${RULE.rule_id}` }).click();

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("highlight-wizard")).toBeVisible();
  return dialog;
}

/** Scopes the axe scan to the Edit-rule dialog only -- the rest of
 *  the guidance page sits behind the modal backdrop and is out of
 *  scope for this feature. */
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

/** Clicks a Step 3 row (by its own [start, end) span) and picks the
 *  stubbed SNOMED hit registered for that row's exact text. Relies
 *  on ConceptSearchPanel pre-filling the search box from the row's
 *  own text (`initialQuery`), so no typing is needed here. */
async function pickConceptForRow(page: Page, row: Locator, rowText: string) {
  const hit = SEARCH_HITS[rowText];
  if (!hit) throw new Error(`No stubbed search hit registered for row text: "${rowText}"`);
  await row.click();
  const useButton = page.getByRole("button", { name: `Use ${hit.term}` });
  await expect(useButton).toBeVisible();
  await useButton.click();
  await expect(useButton).toBeHidden();
}

function rowTestId(item: FixtureItem): string {
  return `list-row-${item.start}-${item.end}`;
}

/**
 * Mirrors wizardMapping.ts's `locateItemsFrom`: finds each `term` as a
 * literal substring of `parent.text`, starting the search after the
 * previous match, so the resulting offsets are the exact ones
 * `buildPathwayRows` computes for a marker-less lead-or cluster
 * embedded in a structure-sourced item's own text (e.g. "nausea" and
 * "vomiting" inside item D's own "nausea or vomiting with any of the
 * following"). Kept local to this spec rather than importing the
 * production helper, since e2e specs intentionally exercise the real
 * rendered DOM rather than reaching into implementation internals.
 */
function locateLeadClusterMembers(parent: FixtureItem, terms: string[]): FixtureItem[] {
  let cursor = 0;
  return terms.map((term) => {
    const idx = parent.text.indexOf(term, cursor);
    const start = parent.start + idx;
    const end = start + term.length;
    cursor = idx + term.length;
    return { text: term, start, end };
  });
}

/**
 * Mirrors pathwayTextSplit.ts's `resolveAtLeastCluster`/`splitAtMarker`
 * for a single-cluster structural item: a structural item's own `text`
 * still carries its lead-in sentence PLUS the "any of the following"
 * marker phrase itself (NICE's markup keeps them in the same `<li>`
 * paragraph, only the nested list is split out), so the row the wizard
 * actually renders for the item's own lead-in is the marker-stripped
 * prefix, not the item's full raw text. Item C ("raised platelet count
 * with any of the following") is the only fixture item this applies to
 * -- item D's own lead-in is instead a `leadCluster` (see
 * `locateLeadClusterMembers`), which never renders as a single row.
 */
const AT_LEAST_MARKER_RE = /\b(?:with\s+)?any\s+of\s+the\s+following:?\s*/i;
function ownClusterLeadRow(item: FixtureItem): FixtureItem {
  const match = AT_LEAST_MARKER_RE.exec(item.text);
  const text = (match ? item.text.slice(0, match.index) : item.text).trim();
  return { text, start: item.start, end: item.start + text.length };
}

test.describe("Highlight-to-build wizard guided journey (NG12 1.2.9 fixture, DI-42246DA7)", () => {
  test("walks Step 1 through Review across all four situations, zero axe blockers at every step", async ({
    page,
  }) => {
    const dialog = await openEditDialog(page);

    // -- Step 1: the existing age prerequisite auto-anchors onto
    // "aged 55 or over" with no reviewer action needed.
    await expect(dialog.getByText("Step 1 of 3")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toHaveAttribute("data-has-anchor", "true");
    await runAxeAndAssertClean(page);

    await dialog.getByRole("button", { name: "No, nothing else" }).click();

    // -- Step 2: the guideline's own 4-item list structure is
    // preferred over the ", or " text heuristic.
    await expect(dialog.getByText("The guideline lists 4 situations. Here they are.")).toBeVisible();
    await expect(dialog.getByText("Found from the guideline's own list formatting.")).toBeVisible();
    await runAxeAndAssertClean(page);

    await dialog.getByRole("button", { name: "Looks right, continue" }).click();

    // -- Step 3, situation A: one plain row, search-and-pick.
    await expect(dialog.getByText(/situation a \(1 of 4\)/i)).toBeVisible();
    const [itemA, itemB, itemC, itemD] = FIXTURE.items;
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(itemA)), itemA.text);
    await runAxeAndAssertClean(page);
    await dialog.getByRole("button", { name: /confirm situation a, next -> b/i }).click();

    // -- Step 3, situation B: one plain row, search-and-pick.
    await expect(dialog.getByText(/situation b \(2 of 4\)/i)).toBeVisible();
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(itemB)), itemB.text);
    await dialog.getByRole("button", { name: /confirm situation b, next -> c/i }).click();

    // -- Step 3, situation C: a nested "any of the following"
    // cluster -- confirm "only one needs to match" (AT_LEAST), which
    // lazily materializes a subgroup on the first child row's own add.
    await expect(dialog.getByText(/situation c \(3 of 4\)/i)).toBeVisible();
    // Scoped to the cluster-grouping group (not a bare text match): the
    // same "We noticed..." copy is intentionally reused as the disabled
    // Confirm button's blocked-reason caption below, so a plain getByText
    // would be ambiguous between the two.
    await expect(
      dialog.getByRole("group", { name: /we noticed "any of the following"/i }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: /only one needs to match/i }).click();

    const itemCRow = ownClusterLeadRow(itemC);
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(itemCRow)), itemCRow.text);
    const [nauseaRow, vomitingRow] = itemC.children!;
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(nauseaRow)), nauseaRow.text);
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(vomitingRow)), vomitingRow.text);
    await runAxeAndAssertClean(page);
    await dialog.getByRole("button", { name: /confirm situation c, next -> d/i }).click();

    // -- Step 3, situation D: TWO clusters in the SAME situation --
    // item D's own text is "nausea or vomiting with any of the
    // following", a marker-less lead-or cluster ("nausea or vomiting")
    // ANDed with the trailing "any of the following" list (weight
    // loss, reflux). Both rows must be individually resolvable and
    // each cluster's AT_LEAST-vs-AND choice is asked independently --
    // this is the exact NG12 1.2.9 defect this feature exists to fix
    // (previously only one combined "nausea or vomiting with any of
    // the following" pseudo-row was offered).
    await expect(dialog.getByText(/situation d \(4 of 4\)/i)).toBeVisible();
    const leadGroup = dialog.getByRole("group", { name: /nausea or vomiting/i });
    const trailingGroup = dialog.getByRole("group", { name: /any of the following/i });
    await expect(leadGroup).toBeVisible();
    await expect(trailingGroup).toBeVisible();
    await runAxeAndAssertClean(page);

    // Lead cluster ("nausea or vomiting"): only one needs to match.
    await leadGroup.getByRole("button", { name: /only one needs to match/i }).click();
    // Trailing cluster ("any of the following: weight loss, reflux"):
    // all must match -- covers the AND path for the trailing cluster
    // while situation C already covered AT_LEAST for a single cluster.
    await trailingGroup.getByRole("button", { name: "All must match" }).click();

    const [leadNauseaRow, leadVomitingRow] = locateLeadClusterMembers(itemD, ["nausea", "vomiting"]);
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(leadNauseaRow)), leadNauseaRow.text);
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(leadVomitingRow)), leadVomitingRow.text);
    const [weightLossRow, refluxRow] = itemD.children!;
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(weightLossRow)), weightLossRow.text);
    await pickConceptForRow(page, dialog.getByTestId(rowTestId(refluxRow)), refluxRow.text);
    // Last situation -- no "next" pathway, so the label drops the arrow.
    await dialog.getByRole("button", { name: /^confirm situation d$/i }).click();

    // -- Review: confirm via the right-column live preview (no embedded
    // sentence editor). Key concepts from situations A and D must appear
    // in the plain-English preview summary.
    await expect(dialog.getByTestId("wizard-review")).toBeVisible();
    await expect(dialog.getByText(/check the live preview/i)).toBeVisible();
    const preview = dialog.getByRole("region", { name: /live preview of this rule/i });
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/dyspepsia|indigestion/i)).toBeVisible();
    await expect(preview.getByText(/nausea/i)).toBeVisible();
    await expect(preview.getByText(/vomiting/i)).toBeVisible();
    await expect(preview.getByText(/weight loss/i)).toBeVisible();
    await expect(preview.getByText(/reflux/i)).toBeVisible();
    await runAxeAndAssertClean(page);
  });
});

