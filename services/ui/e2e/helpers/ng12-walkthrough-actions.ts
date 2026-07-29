/**
 * Shared click/type helpers for NG12 rule-build walkthroughs.
 * Each action takes Evidence so screenshots capture input + outcome.
 */
import { expect, type Locator, type Page } from "@playwright/test";
import type { Evidence } from "./walkthrough-evidence";

export type SearchHit = {
  snomed_concept_id: string;
  term: string;
  semantic_tag: string;
};

export function btnByLabel(root: Locator, label: string | RegExp): Locator {
  return root.getByRole("button").filter({ hasText: label });
}

export async function dismissSplash(page: Page) {
  await page
    .getByRole("button", { name: /skip the guideline builder intro animation/i })
    .click({ timeout: 3000 })
    .catch(() => {});
}

/** Click a finding row, tick the SNOMED hit, Add code -- with evidence. */
export async function pickRowByName(
  page: Page,
  dialog: Locator,
  rowName: string | RegExp,
  hit: SearchHit,
  ev: Evidence,
  slug: string,
) {
  const row = dialog
    .getByTestId(/^list-row-/)
    .filter({ hasText: rowName })
    .first();
  await expect(row).toBeVisible({ timeout: 10000 });
  const testId = await row.getAttribute("data-testid");
  if (!testId) throw new Error("list-row missing data-testid");
  await row.scrollIntoViewIfNeeded();
  await ev.shot(`${slug}-row-before-click`);
  await row.click();

  const checkbox = page.getByRole("checkbox", { name: `Select ${hit.term}` });
  await expect(checkbox).toBeVisible({ timeout: 15000 });
  // After hits land so the frame shows the query text and the SNOMED row.
  const search = page.getByLabel(/search clinical terms/i);
  if (await search.isVisible().catch(() => false)) {
    await ev.shot(`${slug}-search-with-hits`);
  } else {
    await ev.shot(`${slug}-hit-visible`);
  }
  await checkbox.check();
  await expect(checkbox).toBeChecked();
  await ev.shot(`${slug}-code-ticked`);
  await page.getByRole("button", { name: "Add 1 code" }).click();
  await expect(page.getByRole("button", { name: "Add 1 code" })).toBeHidden({
    timeout: 10000,
  });
  await expect(dialog.getByTestId(testId)).toHaveAttribute(
    "data-resolved",
    "true",
    { timeout: 10000 },
  );
  await ev.shot(`${slug}-code-added`);
}

export async function chooseOnlyOneGrouping(
  dialog: Locator,
  ev: Evidence,
  slug: string,
) {
  const btn = btnByLabel(dialog, /only one needs to match/i);
  await expect(btn).toBeVisible({ timeout: 10000 });
  await ev.shot(`${slug}-grouping-prompt`);
  await btn.click();
  await expect(
    dialog.getByText(/only one of .+ needs to match/i),
  ).toBeVisible();
  await ev.shot(`${slug}-grouping-only-one`);
}

export async function chooseAtLeastNGrouping(
  dialog: Locator,
  n: number,
  ev: Evidence,
  slug: string,
) {
  const btn = btnByLabel(
    dialog,
    new RegExp(`at least ${n} need to match`, "i"),
  );
  await expect(btn).toBeVisible({ timeout: 10000 });
  await ev.shot(`${slug}-grouping-prompt`);
  await btn.click();
  // Confirmed copy names the findings when known:
  // "At least 2 of cough, fatigue, ... need to match."
  await expect(
    dialog.getByText(new RegExp(`at least ${n} of .+ need to match`, "i")),
  ).toBeVisible();
  await ev.shot(`${slug}-grouping-at-least-${n}`);
}

export async function setPathwayAge(
  dialog: Locator,
  operatorOption: RegExp,
  value: string,
  ev: Evidence,
  slug: string,
) {
  const page = dialog.page();
  const panel = dialog.getByTestId("pathway-demographics-panel");
  await expect(panel).toBeVisible({ timeout: 10000 });
  const addAge = dialog.getByRole("button", {
    name: /add an age check for this situation only/i,
  });
  const rows = panel.getByTestId("pathway-demographic-rows");
  if (!(await rows.isVisible().catch(() => false))) {
    await expect(addAge).toBeEnabled();
    await ev.shot(`${slug}-add-age-before`);
    await addAge.click();
  }
  await expect(rows).toBeVisible({ timeout: 10000 });
  await expect(addAge).toBeDisabled();
  await ev.shot(`${slug}-age-editor-open`);

  const compare = rows.getByRole("combobox", { name: /^how to compare age$/i });
  const valueField = rows.locator('input[aria-label="Lower bound"]');
  await expect(valueField).toBeVisible();
  await valueField.fill(value);
  await expect(valueField).toHaveValue(value);
  await ev.shot(`${slug}-age-value-${value}`);

  const currentOp = (await compare.innerText()).trim();
  if (!operatorOption.test(currentOp)) {
    await compare.click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible({ timeout: 5000 });
    await ev.shot(`${slug}-age-operator-menu`);
    const option = listbox.getByRole("option", { name: operatorOption });
    await option.scrollIntoViewIfNeeded();
    await option.click();
    await expect(listbox).toBeHidden({ timeout: 5000 });
    await expect(compare).toHaveText(operatorOption);
  }
  await expect(rows).toBeVisible();
  await expect(valueField).toHaveValue(value);
  await ev.shot(`${slug}-age-set`);
}

export async function confirmSituation(
  dialog: Locator,
  letter: string,
  ev: Evidence,
  next?: string,
) {
  const label = next
    ? new RegExp(`confirm situation ${letter}, next -> ${next}`, "i")
    : new RegExp(`^confirm situation ${letter}$`, "i");
  await ev.shot(`situation-${letter}-ready-to-confirm`);
  await btnByLabel(dialog, label).click();
}

/** Open clinical-guidelines review pool and Edit for a pending rule. */
export async function openEditDialog(
  page: Page,
  rule: { guideline_id: string; rule_id: string },
  ev: Evidence,
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

  await expect(
    page.getByRole("button", { name: `Toggle rule from ${rule.guideline_id}` }),
  ).toBeVisible({ timeout: 15000 });
  await page
    .getByRole("button", { name: `Toggle rule from ${rule.guideline_id}` })
    .click();
  await expect(
    page.getByRole("button", { name: `Edit rule ${rule.rule_id}` }),
  ).toBeVisible();
  await ev.shot("review-pool-card-before-edit");
  await page.getByRole("button", { name: `Edit rule ${rule.rule_id}` }).click();

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("highlight-wizard")).toBeVisible();
  await ev.shot("edit-dialog-open");
  return dialog;
}

/**
 * Suggest step when the clinical-term search is already open
 * (blank first row, or a new row after If not available / Or instead).
 */
export async function typeSuggestProcedure(
  page: Page,
  dialog: Locator,
  query: string,
  useButtonName: RegExp,
  ev: Evidence,
  slug: string,
) {
  const search = dialog.getByLabel(/search clinical terms/i);
  await expect(search).toBeVisible({ timeout: 10000 });
  await ev.shot(`${slug}-search-open`);
  await search.fill(query);
  await expect(search).toHaveValue(query);
  const useBtn = page.getByRole("button", { name: useButtonName });
  await expect(useBtn).toBeVisible({ timeout: 15000 });
  await ev.shot(`${slug}-search-typed-with-hit`);
  await useBtn.click();
  await ev.shot(`${slug}-action-coded`);
}

/** Suggest step: open blank procedure, type query, Use hit. */
export async function pickSuggestAction(
  page: Page,
  dialog: Locator,
  query: string,
  useButtonName: RegExp,
  ev: Evidence,
  slug = "suggest",
) {
  await dialog
    .getByRole("button", {
      name: /no procedure picked yet\. click to pick/i,
    })
    .click();
  await typeSuggestProcedure(page, dialog, query, useButtonName, ev, slug);
}

/** Fill change reason and capture before Approve. */
export async function fillSaveReason(
  dialog: Locator,
  reason: string,
  ev: Evidence,
) {
  await expect(
    dialog.getByRole("heading", { name: /save your change/i }),
  ).toBeVisible({ timeout: 10000 });
  await ev.shot("save-before-after-preview");
  await dialog.getByLabel(/why are you changing this rule/i).fill(reason);
  await ev.shot("save-reason-filled");
}

/**
 * Like pickRowByName, but types `query` into the clinical-term search
 * (needed when the row phrase is too vague for auto-hits).
 */
export async function pickRowWithTypedSearch(
  page: Page,
  dialog: Locator,
  rowName: string | RegExp,
  query: string,
  hit: SearchHit,
  ev: Evidence,
  slug: string,
) {
  const row = dialog
    .getByTestId(/^list-row-/)
    .filter({ hasText: rowName })
    .first();
  await expect(row).toBeVisible({ timeout: 10000 });
  const testId = await row.getAttribute("data-testid");
  if (!testId) throw new Error("list-row missing data-testid");
  await row.scrollIntoViewIfNeeded();
  await ev.shot(`${slug}-row-before-click`);
  await row.click();

  const search = page.getByLabel(/search clinical terms/i);
  await expect(search).toBeVisible({ timeout: 15000 });
  await ev.shot(`${slug}-search-open`);
  await search.fill("");
  await search.fill(query);
  await expect(search).toHaveValue(query);
  // Multi-pick uses checkboxes; single-pick uses a Use button.
  const checkbox = page.getByRole("checkbox", { name: `Select ${hit.term}` });
  const useBtn = page.getByRole("button", {
    name: new RegExp(`Use ${hit.term}`, "i"),
  });
  await expect(checkbox.or(useBtn).first()).toBeVisible({ timeout: 15000 });
  if (await checkbox.isVisible().catch(() => false)) {
    await ev.shot(`${slug}-search-typed-with-hits`);
    await checkbox.check();
    await expect(checkbox).toBeChecked();
    await ev.shot(`${slug}-code-ticked`);
    await page.getByRole("button", { name: "Add 1 code" }).click();
    await expect(page.getByRole("button", { name: "Add 1 code" })).toBeHidden({
      timeout: 10000,
    });
  } else {
    await ev.shot(`${slug}-search-typed-with-hits`);
    await useBtn.click();
  }
  await expect(dialog.getByTestId(testId)).toHaveAttribute(
    "data-resolved",
    "true",
    { timeout: 10000 },
  );
  await ev.shot(`${slug}-code-added`);
}

/**
 * Vague phrase -> no SNOMED hits -> Ask LEO -> tick terms -> add codes.
 * Captures evidence at each Ask LEO step.
 */
export async function askLeoForRow(
  page: Page,
  dialog: Locator,
  rowText: string | RegExp,
  expectedTerms: readonly string[],
  ev: Evidence,
  slug: string,
) {
  const row = dialog
    .getByTestId(/^list-row-/)
    .filter({ hasText: rowText })
    .first();
  await expect(row).toBeVisible({ timeout: 10000 });
  const testId = await row.getAttribute("data-testid");
  if (!testId) throw new Error("list-row missing data-testid");
  await row.scrollIntoViewIfNeeded();
  await ev.shot(`${slug}-row-before-click`);
  await row.click();

  await expect(page.getByText(/No clinical terms match/i)).toBeVisible({
    timeout: 15000,
  });
  const askLeo = page.getByRole("button", { name: /Ask LEO for ideas/i });
  await expect(askLeo).toBeVisible();
  await ev.shot(`${slug}-no-results-ask-leo`);
  await askLeo.click();

  const askDialog = page.getByRole("dialog", { name: /Ask LEO for ideas/i });
  await expect(askDialog).toBeVisible({ timeout: 10000 });
  for (const term of expectedTerms) {
    await expect(askDialog.getByText(term, { exact: true })).toBeVisible();
  }
  await ev.shot(`${slug}-tick-terms`);
  await askDialog.getByRole("button", { name: /Look up ticked terms/i }).click();

  await expect(
    askDialog.getByRole("button", { name: /Add the matched clinical terms/i }),
  ).toBeEnabled({ timeout: 15000 });
  await ev.shot(`${slug}-resolved`);
  await askDialog
    .getByRole("button", { name: /Add the matched clinical terms/i })
    .click();
  await expect(askDialog).toBeHidden({ timeout: 10000 });
  await expect(dialog.getByTestId(testId)).toHaveAttribute(
    "data-resolved",
    "true",
    { timeout: 10000 },
  );
  await ev.shot(`${slug}-code-added`);
}
