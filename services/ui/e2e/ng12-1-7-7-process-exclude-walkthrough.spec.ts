/**
 * End-to-end walkthrough: NG12 1.7.7 is a process / cross-reference
 * recommendation (follow another NICE skin-tumour guideline). Reviewers
 * confirm "no coded rule needed" and move it to Excluded.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Run from services/ui:
 *   npx playwright test ng12-1-7-7-process-exclude-walkthrough --project=chromium
 */
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "fs";
import path from "path";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-7-7");

const REC_TEXT =
  "1.7.7 Follow NICE's guidance on improving outcomes for people with " +
  "skin tumours including melanoma for advice on who should excise " +
  "suspected basal cell carcinomas. [2015]";

const RULE = {
  rule_id: "e2e-ng12-1-7-7-process-exclude",
  name: "NG12 1.7.7 -- follow skin-tumour guidance (process)",
  status: "pending_review",
  strength: "unspecified",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text: REC_TEXT,
  recommendation_structure: null,
  generation_outcome: "no_rule_expected",
  generation_errors: [
    "Process/communication recommendation - no codeable clinical criterion",
  ],
  needs_human_review: true,
  plain_english:
    "Follow separate NICE skin-tumour guidance for BCC excision advice.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: {
    node_id: "root",
    kind: "AND",
    children: [],
  },
  action: {
    snomed_concept_id: "",
    preferred_term: "",
    semantic_tag: "procedure",
  },
  has_predecessor: false,
  updated_at: "2026-07-01T09:00:00Z",
};

type DecisionBody = {
  action?: string;
  reason?: string;
};

async function installFixtures(
  page: Page,
  captured: { decision: DecisionBody | null },
) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([RULE]),
    }),
  );
  for (const status of ["active", "superseded", "rejected"]) {
    await page.route(`**/api/guidance/rules/review*status=${status}*`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      }),
    );
  }
  await page.route("**/api/guidance/rules/review/*/decision", async (route) => {
    const raw = route.request().postData();
    captured.decision = raw ? (JSON.parse(raw) as DecisionBody) : null;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rule_id: `${RULE.rule_id}:rejected` }),
    });
  });
  await page.route("**/api/nice/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
}

async function dismissSplash(page: Page) {
  await page
    .getByRole("button", { name: /skip the guideline builder intro animation/i })
    .click({ timeout: 3000 })
    .catch(() => {});
}

async function shot(page: Page, name: string) {
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, `${name}.png`),
    fullPage: false,
  });
}

test.describe("NG12 1.7.7 process exclude walkthrough (DI-42246DA7)", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("confirms no coded rule needed for process cross-reference", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const captured: { decision: DecisionBody | null } = { decision: null };
    await installFixtures(page, captured);

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
      page.getByText(/no coded rule is needed/i),
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByRole("button", {
        name: `Confirm no rule needed for ${RULE.rule_id}`,
      }),
    ).toBeVisible();
    await shot(page, "01-process-rec-card");

    const axe = await new AxeBuilder({ page })
      .include("#rule-review-body")
      .withTags([...WCAG_TAGS])
      .analyze();
    const blockers = axe.violations.filter(
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

    await page
      .getByRole("button", {
        name: `Confirm no rule needed for ${RULE.rule_id}`,
      })
      .click();

    await expect
      .poll(() => captured.decision?.action, { timeout: 10000 })
      .toBe("reject");
    expect(captured.decision?.reason).toBe("No coded rule needed");
    await shot(page, "02-confirmed-excluded");
  });
});
