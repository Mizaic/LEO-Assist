/**
 * End-to-end walkthrough: build NG12 recommendation 1.5.5 (ovarian
 * cancer tests when IBS-suggestive symptoms present at age 50+) in the
 * guided EditRuleDialog.
 *
 * Inclusive sex phrasing ("any woman, or trans man or non-binary...")
 * must NOT become Situation A/B. Empty recommendation_structure falls
 * back to the text heuristic, which correctly reports no split.
 *
 * IBS row uses typed search (query + hits evidenced). Every click/type
 * is a numbered screenshot under e2e/screenshots/ng12-1-5-5/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-5-5-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  btnByLabel,
  confirmSituation,
  fillSaveReason,
  openEditDialog,
  pickRowWithTypedSearch,
  pickSuggestAction,
} from "./helpers/ng12-walkthrough-actions";
import {
  createWalkthroughEvidence,
  type Evidence,
} from "./helpers/walkthrough-evidence";
import {
  IBS_ROW,
  installFixtures,
  RULE,
  SEARCH_HITS,
  type DecisionBody,
} from "./helpers/ng12-1-5-5-fixtures";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-5-5");

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

test.describe("NG12 1.5.5 rule-build walkthrough (DI-42246DA7)", () => {
  test("builds 1.5.5 end-to-end with no fake sex-phrase situations", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    const ev: Evidence = createWalkthroughEvidence(page, SCREENSHOT_DIR);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page, RULE, ev);

    // -- Step 1: Always true (age + sex) ------------------------------
    await expect(dialog.getByText("Always true")).toBeVisible();
    await expect(dialog.getByTestId("prerequisite-row-age")).toHaveAttribute(
      "data-has-anchor",
      "true",
    );
    await expect(dialog.getByTestId("prerequisite-row-sex")).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("who-always-true-age-sex");
    await btnByLabel(dialog, /No, nothing else/i).click();
    await ev.shot("who-after-nothing-else");

    // -- Step 2: inclusive sex ", or " must NOT invent Situation A/B --
    await expect(
      dialog.getByText(/couldn't find more than one situation/i),
    ).toBeVisible({ timeout: 15000 });
    await expect(dialog.getByText(/\(A\)/i)).toHaveCount(0);
    await expect(dialog.getByText(/\(B\)/i)).toHaveCount(0);
    await runAxeDialog(page);
    await ev.shot("situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    // -- Step 3: single situation -- IBS-suggestive symptoms ----------
    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByTestId(/^list-row-/).filter({ hasText: IBS_ROW }),
    ).toBeVisible();
    await ev.shot("situation-a-open");
    await pickRowWithTypedSearch(
      page,
      dialog,
      /irritable bowel syndrome/i,
      "irritable bowel",
      hit("irritable bowel"),
      ev,
      "situation-a-ibs",
    );
    await runAxeDialog(page);
    await confirmSituation(dialog, "a", ev);

    // -- Wizard Review ------------------------------------------------
    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    const preview = dialog.locator('[data-tour="er-06-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText(/irritable bowel/i).first()).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("wizard-review-live-preview");

    // -- Suggest: ovarian cancer tests --------------------------------
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
      "Walkthrough: coded NG12 1.5.5 age/sex + IBS-suggestive symptoms, no sex-phrase split.",
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
    expect(ev.count()).toBeGreaterThan(15);
  });
});
