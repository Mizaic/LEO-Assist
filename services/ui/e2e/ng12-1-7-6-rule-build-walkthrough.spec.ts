/**
 * End-to-end walkthrough: build NG12 recommendation 1.7.6 (consider
 * 2WW for BCC-suspicious lesion when delay would matter) via Ask LEO.
 *
 * Peels to two AND rows (lesion suspicion + delay concern). Both are
 * vague; Ask LEO interprets them into SNOMED codes before Suggest.
 *
 * Evidence at each Ask LEO step (no results, tick terms, resolved).
 * Numbered screenshots under e2e/screenshots/ng12-1-7-6/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-7-6-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  askLeoForRow,
  btnByLabel,
  confirmSituation,
  fillSaveReason,
  openEditDialog,
  pickSuggestAction,
} from "./helpers/ng12-walkthrough-actions";
import {
  createWalkthroughEvidence,
  type Evidence,
} from "./helpers/walkthrough-evidence";
import {
  BCC_ROW,
  BCC_TERMS,
  DELAY_ROW,
  DELAY_TERMS,
  installFixtures,
  RULE,
  type DecisionBody,
} from "./helpers/ng12-1-7-6-fixtures";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-7-6");

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

test.describe("NG12 1.7.6 rule-build walkthrough (DI-42246DA7)", () => {
  test("builds 1.7.6 via Ask LEO on BCC + delay-concern rows", async ({
    page,
  }) => {
    test.setTimeout(300_000);
    const ev: Evidence = createWalkthroughEvidence(page, SCREENSHOT_DIR);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

    const dialog = await openEditDialog(page, RULE, ev);

    await expect(dialog.getByText("Always true")).toBeVisible();
    await runAxeDialog(page);
    await ev.shot("who-always-true");
    await btnByLabel(dialog, /No, nothing else/i).click();
    await ev.shot("who-after-nothing-else");

    await expect(
      dialog.getByText(/couldn't find more than one situation/i),
    ).toBeVisible({ timeout: 15000 });
    await ev.shot("situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(
      dialog.getByTestId(/^list-row-/).filter({ hasText: BCC_ROW }),
    ).toBeVisible();
    await expect(
      dialog.getByTestId(/^list-row-/).filter({ hasText: DELAY_ROW }),
    ).toBeVisible();
    await ev.shot("situation-a-two-and-rows");

    await askLeoForRow(page, dialog, BCC_ROW, BCC_TERMS, ev, "ask-leo-bcc");
    await askLeoForRow(page, dialog, DELAY_ROW, DELAY_TERMS, ev, "ask-leo-delay");
    await runAxeDialog(page);
    await ev.shot("situation-a-both-rows-coded");
    await confirmSituation(dialog, "a", ev);

    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    await ev.shot("wizard-review-live-preview");

    await btnByLabel(dialog, /^Next/i).click();
    await expect(
      dialog.getByRole("heading", {
        name: /what should the system suggest/i,
      }),
    ).toBeVisible({ timeout: 15000 });
    await ev.shot("suggest-uncoded-action");

    await pickSuggestAction(
      page,
      dialog,
      "skin cancer",
      /Use Fast track referral for suspected skin cancer/i,
      ev,
      "suggest",
    );

    const prioritySelect = dialog.locator("#edit-rule-priority");
    await prioritySelect.scrollIntoViewIfNeeded();
    await prioritySelect.click();
    await ev.shot("suggest-priority-menu");
    await page.getByRole("option", { name: /2 week wait/i }).click();
    await ev.shot("suggest-priority-2ww");
    const strengthSelect = dialog.locator("#edit-rule-action-strength-0");
    await strengthSelect.scrollIntoViewIfNeeded();
    await strengthSelect.click();
    await ev.shot("suggest-strength-menu");
    await page
      .getByRole("option", { name: /Think about this test or referral/i })
      .click();
    await ev.shot("suggest-consider-2ww");

    await btnByLabel(dialog, /^Next/i).click();

    await fillSaveReason(
      dialog,
      "Walkthrough: Ask LEO coded NG12 1.7.6 BCC suspicion + delay concern.",
      ev,
    );

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    const ids = (captured.decision?.updates?.logic_tree?.children ?? [])
      .filter((c) => c.kind === "CONCEPT")
      .map((c) => c.criterion?.snomed_concept_id);
    expect(ids).toEqual(
      expect.arrayContaining([
        "254701007",
        "274142008",
        "161590003",
        "103323008",
      ]),
    );
    expect(ids).toHaveLength(4);
    expect(
      captured.decision?.updates?.actions?.[0]?.criterion?.snomed_concept_id,
    ).toBe("276281000000104");
    expect(captured.decision?.updates?.actions?.[0]?.strength).toBe("consider");

    await ev.shot("review-pool-after-save");
    expect(ev.count()).toBeGreaterThan(20);
  });
});
