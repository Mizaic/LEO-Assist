/**
 * End-to-end walkthrough: build NG12 recommendation 1.3.1 (offer FIT
 * for suspected colorectal cancer) in the guided EditRuleDialog.
 *
 * Seven structure-sourced situations (A-G). Every user click and typed
 * value is captured as a numbered screenshot (input + outcome) under
 * e2e/screenshots/ng12-1-3-1/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-3-1-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  findAtLeastGroup,
  findDemographic,
  findDirectConcept,
  findLeadPlusEitherOrSituation,
  type TreeNode,
} from "./helpers/ng12-logic-tree-assert";
import {
  btnByLabel,
  chooseOnlyOneGrouping,
  confirmSituation,
  dismissSplash,
  pickRowByName,
  setPathwayAge,
} from "./helpers/ng12-walkthrough-actions";
import {
  createWalkthroughEvidence,
  type Evidence,
} from "./helpers/walkthrough-evidence";
import {
  installFixtures,
  RULE,
  SEARCH_HITS,
  type DecisionBody,
} from "./helpers/ng12-1-3-1-fixtures";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-3-1");

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

function hit(searchKey: string) {
  const hits = SEARCH_HITS[searchKey];
  if (!hits?.[0]) throw new Error(`No SEARCH_HITS[${searchKey}]`);
  return hits[0]!;
}

async function openEditDialog(page: Page, ev: Evidence): Promise<Locator> {
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
  await ev.shot("review-pool-card-before-edit");
  await page.getByRole("button", { name: `Edit rule ${RULE.rule_id}` }).click();

  const dialog = page.getByRole("dialog", { name: /Change this rule/i });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("highlight-wizard")).toBeVisible();
  await ev.shot("edit-dialog-open");
  return dialog;
}

async function pick(
  page: Page,
  dialog: Locator,
  rowName: string | RegExp,
  searchKey: string,
  ev: Evidence,
  slug: string,
) {
  await pickRowByName(page, dialog, rowName, hit(searchKey), ev, slug);
}

test.describe("NG12 1.3.1 rule-build walkthrough (DI-42246DA7)", () => {
  test("builds 1.3.1 end-to-end with seven situations, FIT action, and sign-off", async ({
    page,
  }) => {
    test.setTimeout(480_000);
    const ev = createWalkthroughEvidence(page, SCREENSHOT_DIR);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page, ev);

    // -- Step 1: Always true (seeded adults age>=18) ------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("who-always-true");
    await btnByLabel(dialog, /No, nothing else/i).click();
    await ev.shot("who-after-nothing-else");

    // -- Step 2: seven situations from structure ----------------------
    await expect(
      dialog.getByText(/the guideline lists 7 situations/i),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await ev.shot("situations-split-confirm");
    await btnByLabel(dialog, /Looks right, continue/i).click();

    // -- A: abdominal mass --------------------------------------------
    await expect(dialog.getByText(/situation a \(1 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await ev.shot("situation-a-open");
    await pick(
      page,
      dialog,
      /^abdominal mass$/i,
      "abdominal mass",
      ev,
      "situation-a-mass",
    );
    await confirmSituation(dialog, "a", ev, "b");

    // -- B: change in bowel habit -------------------------------------
    await expect(dialog.getByText(/situation b \(2 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await ev.shot("situation-b-open");
    await pick(
      page,
      dialog,
      /^change in bowel habit$/i,
      "change in bowel habit",
      ev,
      "situation-b-bowel",
    );
    await confirmSituation(dialog, "b", ev, "c");

    // -- C: iron-deficiency anaemia -----------------------------------
    await expect(dialog.getByText(/situation c \(3 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await ev.shot("situation-c-open");
    await pick(
      page,
      dialog,
      /^iron-deficiency anaemia$/i,
      "iron-deficiency anaemia",
      ev,
      "situation-c-anaemia",
    );
    await confirmSituation(dialog, "c", ev, "d");

    // -- D: age >=40 + weight loss + abdominal pain -------------------
    await expect(dialog.getByText(/situation d \(4 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await ev.shot("situation-d-open");
    await setPathwayAge(dialog, /is at least/i, "40", ev, "situation-d");
    await pick(
      page,
      dialog,
      /^unexplained weight loss$/i,
      "unexplained weight loss",
      ev,
      "situation-d-weight-loss",
    );
    await pick(
      page,
      dialog,
      /^abdominal pain$/i,
      "abdominal pain",
      ev,
      "situation-d-pain",
    );
    await confirmSituation(dialog, "d", ev, "e");

    // -- E: age <50 + rectal bleeding AND either-of AT_LEAST(1) -------
    await expect(dialog.getByText(/situation e \(5 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(dialog.getByTestId("lead-either-of-layout")).toBeVisible();
    await expect(
      dialog.getByText(/required in this situation/i),
    ).toBeVisible();
    await ev.shot("situation-e-open");
    await setPathwayAge(dialog, /is less than/i, "50", ev, "situation-e");
    await pick(
      page,
      dialog,
      /^rectal bleeding$/i,
      "rectal bleeding",
      ev,
      "situation-e-bleeding",
    );
    await chooseOnlyOneGrouping(dialog, ev, "situation-e");
    await expect(
      dialog.getByText(/only one of abdominal pain and weight loss needs to match/i),
    ).toBeVisible();
    await expect(dialog.getByText(/plus either of these/i)).toBeVisible();
    await pick(
      page,
      dialog,
      /^abdominal pain$/i,
      "abdominal pain",
      ev,
      "situation-e-pain",
    );
    await pick(
      page,
      dialog,
      /^weight loss$/i,
      "weight loss",
      ev,
      "situation-e-weight-loss",
    );
    const leadLayout = dialog.getByTestId("lead-either-of-layout");
    const bleedingRow = leadLayout.getByTestId(/^list-row-/).first();
    await expect(bleedingRow).toContainText(/rectal bleeding/i);
    await expect(bleedingRow).toHaveAttribute("data-resolved", "true");
    await bleedingRow.scrollIntoViewIfNeeded();
    await expect(leadLayout.getByText(/of 2/i)).toBeVisible();
    await ev.shot("situation-e-complete");
    await confirmSituation(dialog, "e", ev, "f");

    // -- F: age >=50 + any of three (copy-across when offered) --------
    await expect(dialog.getByText(/situation f \(6 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    await ev.shot("situation-f-open");
    await setPathwayAge(dialog, /is at least/i, "50", ev, "situation-f");
    const copyBtn = btnByLabel(dialog, /copy them across/i);
    if (await copyBtn.isVisible().catch(() => false)) {
      await ev.shot("situation-f-copy-across-offer");
      await copyBtn.click();
      await ev.shot("situation-f-copy-across-done");
    } else {
      await chooseOnlyOneGrouping(dialog, ev, "situation-f");
      await pick(
        page,
        dialog,
        /^rectal bleeding$/i,
        "rectal bleeding",
        ev,
        "situation-f-bleeding",
      );
      await pick(
        page,
        dialog,
        /^abdominal pain$/i,
        "abdominal pain",
        ev,
        "situation-f-pain",
      );
      await pick(
        page,
        dialog,
        /^weight loss$/i,
        "weight loss",
        ev,
        "situation-f-weight-loss",
      );
    }
    const onlyOneAlready = dialog.getByText(/only one of .+ needs to match/i);
    if (!(await onlyOneAlready.isVisible().catch(() => false))) {
      await chooseOnlyOneGrouping(dialog, ev, "situation-f-late");
    }
    await ev.shot("situation-f-complete");
    await confirmSituation(dialog, "f", ev, "g");

    // -- G: age >=60 + anaemia (caveats stripped from row) ------------
    await expect(dialog.getByText(/situation g \(7 of 7\)/i)).toBeVisible({
      timeout: 15000,
    });
    const anaemiaRow = dialog
      .getByTestId(/^list-row-/)
      .filter({ hasText: /anaemia even in the absence of iron deficiency/i })
      .first();
    await expect(anaemiaRow).toBeVisible();
    await expect(anaemiaRow).not.toContainText(/FIT should be offered/i);
    await ev.shot("situation-g-open");
    await setPathwayAge(dialog, /is at least/i, "60", ev, "situation-g");
    await pick(
      page,
      dialog,
      /^anaemia even in the absence of iron deficiency$/i,
      "anaemia even in the absence of iron deficiency",
      ev,
      "situation-g-anaemia",
    );
    await confirmSituation(dialog, "g", ev);

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/abdominal mass/i).first()).toBeVisible();
    await expect(preview.getByText(/rectal bleeding/i).first()).toBeVisible();
    await expect(preview.getByText(/has at least 1 of:/i).first()).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("wizard-review-live-preview");

    // -- Suggest: FIT + 2WW + Offer -----------------------------------
    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await ev.shot("suggest-uncoded-action");

    await dialog
      .getByRole("button", {
        name: /no procedure picked yet\. click to pick/i,
      })
      .click();
    const search = dialog.getByLabel(/search clinical terms/i);
    await expect(search).toBeVisible({ timeout: 10000 });
    await ev.shot("suggest-search-open");
    await search.fill("fit");
    await expect(search).toHaveValue("fit");
    const useFit = page.getByRole("button", {
      name: /Use Quantitative faecal immunochemical test/i,
    });
    await expect(useFit).toBeVisible({ timeout: 15000 });
    await ev.shot("suggest-search-typed-fit-with-hit");
    await useFit.click();
    await expect(
      dialog.getByRole("button", {
        name: /quantitative faecal immunochemical test/i,
      }),
    ).toBeVisible({ timeout: 10000 });
    await ev.shot("suggest-action-coded");

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await ev.shot("suggest-priority-menu");
    await page.getByRole("option", { name: /2 week wait/i }).click();
    await ev.shot("suggest-priority-2ww");
    const dueDays = dialog.locator("#edit-rule-due-days");
    await dueDays.scrollIntoViewIfNeeded();
    await dueDays.fill("14");
    await expect(dueDays).toHaveValue("14");
    await ev.shot("suggest-sla-14-days");
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await ev.shot("suggest-strength-menu");
    await page
      .getByRole("option", { name: /offer this test or referral/i })
      .click();
    await ev.shot("suggest-priority-sla-strength");

    await btnByLabel(dialog, /^Next/i).click();

    // -- Save / sign-off ----------------------------------------------
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(/saved, but not live yet/i)).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("save-before-after-preview");

    const reason =
      "Walkthrough: coded NG12 1.3.1 FIT situations A-G, set 2WW / 14 days.";
    await dialog.getByLabel(/why are you changing this rule/i).fill(reason);
    await ev.shot("save-reason-filled");

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    expect(captured.decision?.updates?.priority).toBe("2ww");
    expect(captured.decision?.updates?.due_days).toBe(14);
    expect(captured.decision?.updates?.logic_tree).toBeTruthy();
    const actions = captured.decision?.updates?.actions;
    expect(Array.isArray(actions) && actions.length > 0).toBe(true);
    expect(actions?.[0]?.strength).toBe("offer");
    expect(actions?.[0]?.criterion?.snomed_concept_id).toBe("1049361000000101");

    const situationE = findLeadPlusEitherOrSituation(
      captured.decision?.updates?.logic_tree as TreeNode | undefined,
      "12063002",
    );
    expect(
      situationE,
      `Expected lead+either-or pathway for rectal bleeding. Tree: ${JSON.stringify(
        captured.decision?.updates?.logic_tree,
        null,
        2,
      )}`,
    ).toBeTruthy();
    expect(findDirectConcept(situationE, "12063002")).toBeTruthy();
    const eitherOf = findAtLeastGroup(situationE);
    expect(eitherOf?.min).toBe(1);
    const eitherIds = (eitherOf?.children ?? [])
      .map((c) => c.criterion?.snomed_concept_id)
      .sort();
    expect(eitherIds).toEqual(["21522001", "262285001"]);
    const ageUnder50 =
      findDemographic(situationE, "age", "<") ??
      findDemographic(situationE, "age", "<=");
    expect(
      ageUnder50,
      "Situation E must keep age under 50 on the same pathway as bleeding",
    ).toBeTruthy();
    expect(String(ageUnder50?.value ?? "")).toMatch(/50/);

    await ev.shot("review-pool-after-save");
    expect(ev.count()).toBeGreaterThan(40);
  });
});
