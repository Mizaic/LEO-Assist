/**
 * End-to-end walkthrough: build NG12 recommendation 1.7.1 (melanoma
 * referral when weighted 7-point checklist score >= 3) in the guided
 * EditRuleDialog.
 *
 * Expands the companion weighted checklist into major/minor feature
 * rows, codes them, and confirms the tree reifies to
 * OR(AT_LEAST 2 majors | AND(1 maj, 1 min) | AT_LEAST 3 minors).
 *
 * Evidence: before/after expand and each feature coded. Numbered
 * screenshots under e2e/screenshots/ng12-1-7-1/.
 *
 * Atlas trace: UN-49C83395 / DI-42246DA7 / DO-F8C56339 / VAL-8AB4C593
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-7-1-rule-build-walkthrough --project=chromium
 */
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import {
  btnByLabel,
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
  FEATURES,
  findOrNode,
  installFixtures,
  RULE,
  SEARCH_HITS,
  type DecisionBody,
} from "./helpers/ng12-1-7-1-fixtures";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-7-1");

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

function featureSlug(feature: string): string {
  return `feature-${feature.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
}

test.describe("NG12 1.7.1 rule-build walkthrough (DI-42246DA7)", () => {
  test("builds 1.7.1 with expanded weighted checklist OR tree", async ({
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
    await runAxeDialog(page);
    await ev.shot("situations-no-split");
    await btnByLabel(
      dialog,
      /Doesn't split -- one set of rules for everyone/i,
    ).click();

    await expect(dialog.getByText(/situation a \(1 of 1\)/i)).toBeVisible({
      timeout: 15000,
    });
    await expect(dialog.getByTestId("weighted-checklist-expand")).toBeVisible();
    await expect(
      dialog.getByRole("button", {
        name: /expand weighted checklist \(score at least 3\)/i,
      }),
    ).toBeVisible();
    await ev.shot("weighted-checklist-before-expand");
    await dialog
      .getByRole("button", {
        name: /expand weighted checklist \(score at least 3\)/i,
      })
      .click();

    await expect(
      dialog.getByText(/major features \(3\) and minor features \(4\)/i),
    ).toBeVisible({ timeout: 10000 });
    await ev.shot("weighted-checklist-after-expand");

    for (const feature of FEATURES) {
      await pickRowByName(
        page,
        dialog,
        feature,
        hit(feature),
        ev,
        featureSlug(feature),
      );
    }
    await runAxeDialog(page);
    await ev.shot("situation-a-all-features-coded");
    await confirmSituation(dialog, "a", ev);

    await expect(dialog.getByTestId("wizard-review")).toBeVisible({
      timeout: 15000,
    });
    await runAxeDialog(page);
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
      "melanoma",
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
      .getByRole("option", { name: /offer this test or referral/i })
      .click();
    await ev.shot("suggest-priority-strength");

    await btnByLabel(dialog, /^Next/i).click();

    await fillSaveReason(
      dialog,
      "Walkthrough: expanded NG12 1.7.1 weighted 7-point checklist into OR of AT_LEAST groups.",
      ev,
    );

    await btnByLabel(dialog, /approve and save/i).click();
    await expect(dialog).toBeHidden({ timeout: 15000 });

    expect(captured.decision).not.toBeNull();
    expect(captured.decision?.action).toBe("edit");
    const scoreOr = findOrNode(captured.decision?.updates);
    expect(scoreOr).toBeTruthy();
    expect(scoreOr!.children).toHaveLength(3);
    expect(scoreOr!.children?.[0]?.kind).toBe("AT_LEAST");
    expect(scoreOr!.children?.[0]?.min).toBe(2);
    expect(scoreOr!.children?.[1]?.kind).toBe("AND");
    expect(scoreOr!.children?.[2]?.kind).toBe("AT_LEAST");
    expect(scoreOr!.children?.[2]?.min).toBe(3);
    expect(
      captured.decision?.updates?.actions?.[0]?.criterion?.snomed_concept_id,
    ).toBe("276281000000104");
    expect(captured.decision?.updates?.actions?.[0]?.strength).toBe("offer");

    await ev.shot("review-pool-after-save");
    expect(ev.count()).toBeGreaterThan(30);
  });
});
