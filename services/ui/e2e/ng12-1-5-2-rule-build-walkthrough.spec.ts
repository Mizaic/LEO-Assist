/**
 * End-to-end walkthrough: build NG12 recommendation 1.5.2 (primary-care
 * ovarian tests for persistent/frequent symptoms) in the guided
 * EditRuleDialog.
 *
 * The guideline's 4-item symptom `<ul>` under a verbose "any of the
 * following symptoms on a persistent or frequent basis..." lead must
 * stay ONE situation with AT_LEAST(1), not Situation A-D. Inclusive
 * sex phrasing in the lead must not invent a split either.
 *
 * Every user click and typed value is captured as a numbered screenshot
 * under e2e/screenshots/ng12-1-5-2/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-5-2-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  btnByLabel,
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
  FIXTURE_ITEMS,
  installFixtures,
  RULE,
  SEARCH_HITS,
  type DecisionBody,
} from "./helpers/ng12-1-5-2-fixtures";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-5-2");

const SYMPTOM_KEYS = [
  "persistent abdominal distension (often referred to as 'bloating')",
  "feeling full (early satiety) and/or loss of appetite",
  "pelvic or abdominal pain",
  "increased urinary urgency and/or frequency",
] as const;

const SYMPTOM_SLUGS = [
  "situation-a-bloating",
  "situation-a-satiety",
  "situation-a-pain",
  "situation-a-urgency",
] as const;

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

test.describe("NG12 1.5.2 rule-build walkthrough (DI-42246DA7)", () => {
  test("builds 1.5.2 end-to-end as one AT_LEAST situation, not four", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const ev: Evidence = createWalkthroughEvidence(page, SCREENSHOT_DIR);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page, RULE, ev);

    // -- Step 1: Always true (sex; age is soft "especially if") -------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-sex")).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("who-always-true-sex");
    await btnByLabel(dialog, /No, nothing else/i).click();
    await ev.shot("who-after-nothing-else");

    // -- Step 2: must NOT invent Situation A-D from the symptom list --
    await expect(
      dialog.getByText(/couldn't find more than one situation/i),
    ).toBeVisible({ timeout: 15000 });
    await expect(dialog.getByText(/\(A\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(B\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(C\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(D\)/i)).toHaveCount(0);
    await runAxeDialog(page);
    await ev.shot("situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    // -- Step 3: one situation, AT_LEAST(1) over 4 symptom bullets ----
    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByRole("group", { name: /any of the following/i }),
    ).toBeVisible();
    await ev.shot("situation-a-open");
    await chooseOnlyOneGrouping(dialog, ev, "situation-a");
    await expect(
      dialog.getByText(/only one of .+ needs to match/i),
    ).toBeVisible();

    for (const [i, item] of FIXTURE_ITEMS.entries()) {
      await pickRowByName(
        page,
        dialog,
        item.text,
        hit(SYMPTOM_KEYS[i]!),
        ev,
        SYMPTOM_SLUGS[i]!,
      );
    }
    await runAxeDialog(page);
    await ev.shot("situation-a-all-symptoms-coded");
    await confirmSituation(dialog, "a", ev);

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/abdominal bloating/i).first()).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("wizard-review-live-preview");

    // -- Suggest: primary-care ovarian tests --------------------------
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
      "ovarian cancer",
      /Use Ovarian cancer screening/i,
      ev,
      "suggest",
    );
    await expect(
      dialog.getByRole("button", { name: /ovarian cancer screening/i }),
    ).toBeVisible({ timeout: 10000 });

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await ev.shot("suggest-priority-menu");
    await page.getByRole("option", { name: /routine/i }).click();
    await ev.shot("suggest-priority-routine");
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await ev.shot("suggest-strength-menu");
    await page
      .getByRole("option", { name: /offer this test or referral/i })
      .click();
    await ev.shot("suggest-priority-strength");

    await btnByLabel(dialog, /^Next/i).click();

    // -- Save / sign-off ----------------------------------------------
    await runAxeDialog(page);
    await fillSaveReason(
      dialog,
      "Walkthrough: coded NG12 1.5.2 as one AT_LEAST(1) symptom cluster, not four situations.",
      ev,
    );

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    expect(captured.decision?.updates?.logic_tree).toBeTruthy();
    const actions = captured.decision?.updates?.actions;
    expect(Array.isArray(actions) && actions.length > 0).toBe(true);
    expect(actions?.[0]?.strength).toBe("offer");
    expect(actions?.[0]?.criterion?.snomed_concept_id).toBe("268544008");

    await ev.shot("review-pool-after-save");
    expect(ev.count()).toBeGreaterThan(20);
  });
});
