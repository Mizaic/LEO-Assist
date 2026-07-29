/**
 * End-to-end walkthrough: build NG12 recommendation 1.1.2 (urgent
 * chest X-ray for lung cancer) in the guided EditRuleDialog.
 *
 * Situation A uses "At least 2 need to match" (guideline "2 or more").
 * Situation B codes "ever smoked" plus AT_LEAST(1) of the shared
 * 6-symptom list (via Copy across when offered). Every user click and
 * typed value is captured as a numbered screenshot under
 * e2e/screenshots/ng12-1-1-2/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-1-2-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page, type Locator } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  btnByLabel,
  chooseAtLeastNGrouping,
  chooseOnlyOneGrouping,
  confirmSituation,
  fillSaveReason,
  openEditDialog,
  pickRowByName,
  pickSuggestAction,
} from "./helpers/ng12-walkthrough-actions";
import {
  createWalkthroughEvidence,
  type Evidence,
} from "./helpers/walkthrough-evidence";
import {
  hit,
  installFixtures,
  RULE,
  rowTestId,
  SYMPTOMS,
  symptomItem,
  type DecisionBody,
} from "./helpers/ng12-1-1-2-fixtures";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-1-2");

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

async function codeAllSymptoms(
  page: Page,
  dialog: Locator,
  ev: Evidence,
  slugPrefix: string,
) {
  for (const label of SYMPTOMS) {
    const slug = `${slugPrefix}-${label.replace(/\s+/g, "-")}`;
    await pickRowByName(page, dialog, new RegExp(`^${label}$`, "i"), hit(label), ev, slug);
  }
}

test.describe("NG12 1.1.2 rule-build walkthrough (DI-42246DA7)", () => {
  test("builds 1.1.2 end-to-end with coding, navigation, priority/SLA, and sign-off", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const ev = createWalkthroughEvidence(page, SCREENSHOT_DIR);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page, RULE, ev);

    // -- Step 1: Always true (age) ------------------------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toHaveAttribute(
      "data-has-anchor",
      "true",
    );
    await runAxeDialog(page);
    await ev.shot("who-always-true");
    await btnByLabel(dialog, /No, nothing else/i).click();
    await ev.shot("who-after-nothing-else");

    // -- Step 2: two situations (heuristic split for 1.1.2) -----------
    await expect(
      dialog.getByText(/we think we found 2 possible situations/i),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await ev.shot("situations-split-confirm");
    await btnByLabel(dialog, /Looks right, continue/i).click();

    // -- Situation A: AT_LEAST(2) from "2 or more of the following" ---
    await expect(dialog.getByText(/situation a \(1 of 2\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByRole("group", { name: /2 or more of the following/i }),
    ).toBeVisible();
    await ev.shot("situation-a-open");
    await chooseAtLeastNGrouping(dialog, 2, ev, "situation-a");
    await codeAllSymptoms(page, dialog, ev, "situation-a");
    await runAxeDialog(page);
    await ev.shot("situation-a-all-symptoms-coded");
    await confirmSituation(dialog, "a", ev, "b");

    // -- Situation B: ever smoked + copy-across AT_LEAST(1) -----------
    await expect(dialog.getByText(/situation b \(2 of 2\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByRole("button", { name: /^ever smoked$/i }),
    ).toBeVisible();
    await ev.shot("situation-b-open");
    const copyBtn = btnByLabel(dialog, /copy them across/i);
    if (await copyBtn.isVisible().catch(() => false)) {
      await ev.shot("situation-b-copy-across-offer");
      await copyBtn.click();
      await ev.shot("situation-b-copy-across-done");
    } else {
      await chooseOnlyOneGrouping(dialog, ev, "situation-b");
      await codeAllSymptoms(page, dialog, ev, "situation-b");
    }
    const onlyOneAlready = dialog.getByText(
      /only one of .+ needs to match/i,
    );
    if (!(await onlyOneAlready.isVisible().catch(() => false))) {
      await chooseOnlyOneGrouping(dialog, ev, "situation-b-late");
    }
    await pickRowByName(
      page,
      dialog,
      /^ever smoked$/i,
      hit("ever smoked"),
      ev,
      "situation-b-ever-smoked",
    );
    await runAxeDialog(page);
    await ev.shot("situation-b-coded");
    await confirmSituation(dialog, "b", ev);

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.getByRole("region", {
      name: /live preview of this rule/i,
    });
    await expect(preview).toBeVisible();
    // A = AT_LEAST(2) from "2 or more"; B = ever smoked + AT_LEAST(1).
    await expect(preview.getByText(/cough/i).first()).toBeVisible();
    await expect(preview.getByText(/has at least 2 of:/i)).toHaveCount(1);
    await expect(preview.getByText(/has at least 1 of:/i)).toHaveCount(1);
    await expect(preview.getByText(/smoker/i).first()).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("wizard-review-live-preview");

    // -- Back-and-forth: re-open B, swap cough via synonym editor ------
    const wizardBack = dialog
      .getByTestId("highlight-wizard")
      .getByRole("button", { name: /^(Back|Go back to the previous wizard)/i });
    await ev.shot("wizard-back-before");
    await wizardBack.click();
    await expect(dialog.getByText(/situation b \(2 of 2\)/i)).toBeVisible({
      timeout: 10000,
    });
    await ev.shot("situation-b-reopened");
    await dialog.getByTestId(rowTestId(symptomItem("cough"))).click();
    const synonym = page.locator('[aria-labelledby^="synonym-editor-title-"]');
    await expect(synonym).toBeVisible({ timeout: 10000 });
    await ev.shot("synonym-editor-cough");
    await synonym.getByRole("button", { name: /remove this match/i }).click();
    await expect(synonym).toBeHidden({ timeout: 10000 });
    await ev.shot("synonym-cough-removed");
    // Re-code cough with the alternate Dry cough hit.
    await pickRowByName(
      page,
      dialog,
      /^cough$/i,
      hit("cough", 1),
      ev,
      "situation-b-cough-swap",
    );
    await ev.shot("situation-b-cough-swapped");
    await confirmSituation(dialog, "b", ev);
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 10000,
    });
    await ev.shot("wizard-review-after-swap");

    // -- Outer Suggest step -------------------------------------------
    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await runAxeDialog(page);
    await ev.shot("suggest-uncoded-action");

    await pickSuggestAction(
      page,
      dialog,
      "chest x-ray",
      /Use Plain chest X-ray/i,
      ev,
      "suggest",
    );
    await expect(
      dialog.getByRole("button", { name: /plain chest x-ray/i }),
    ).toBeVisible({ timeout: 10000 });

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

    // Outer stepper back-and-forth: Suggest <-> Save.
    await dialog
      .getByRole("button", {
        name: /step 3 of 3: save your change/i,
      })
      .click();
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await ev.shot("stepper-jump-save");
    await dialog
      .getByRole("button", {
        name: /step 2 of 3: what should the system suggest/i,
      })
      .click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 10000 });
    await ev.shot("stepper-jump-back-suggest");
    await btnByLabel(dialog, /^Next/i).click();

    // -- Save / verify / sign-off -------------------------------------
    await expect(
      dialog.getByRole("heading", { name: /save your change/i }),
    ).toBeVisible({ timeout: 10000 });
    await expect(dialog.getByText(/saved, but not live yet/i)).toBeVisible();
    await runAxeDialog(page);
    await fillSaveReason(
      dialog,
      "Walkthrough: coded NG12 1.1.2 symptoms, set 2WW / 14 days, offer chest X-ray.",
      ev,
    );
    await ev.shot("not-live-yet-banner");

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
    expect(actions?.[0]?.criterion?.snomed_concept_id).toBe("399208008");

    await ev.shot("review-pool-after-save");
    expect(ev.count()).toBeGreaterThan(30);
  });
});
