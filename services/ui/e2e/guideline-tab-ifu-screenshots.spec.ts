/**
 * IFU screenshot pack for the Clinical Guidelines tab CoachTour.
 *
 * Driven by PAGE_TOUR_STEPS / EDIT_RULE_TOUR_STEPS so screenshot
 * filenames never drift from the in-product tour ids.
 *
 * Run from services/ui (needs playwright.config baseURL):
 *   cd services/ui && npx playwright test guideline-tab-ifu-screenshots --project=chromium
 *
 * Atlas trace: DI-LEO-AI-121 / DI-42246DA7 (cosmetic coach / editor chrome).
 */
import { test, expect, type Page } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import fs from "fs";

import {
  EDIT_RULE_TOUR_STEPS,
  PAGE_TOUR_STEPS,
} from "../src/app/admin/guidance/guidanceTourSteps";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots");

interface FixtureItem {
  text: string;
  start: number;
  end: number;
  children?: FixtureItem[];
}

function buildNg12129Fixture() {
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
  const appendChildren = (labels: string[]): FixtureItem[] =>
    labels.map((label, i) => {
      if (i > 0) append(", ");
      return appendItem(label);
    });

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

const RULE = {
  rule_id: "e2e-ifu-ng12-129",
  name: "E2E -- IFU screenshots (NG12 1.2.9)",
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
  plain_english: "Referral criteria for upper GI endoscopy.",
  present_criteria: [],
  absent_criteria: [],
  logic_tree: {
    node_id: "root",
    kind: "AND",
    children: [
      {
        node_id: "age",
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: "55",
      },
    ],
  },
  action: {
    snomed_concept_id: "112788007",
    preferred_term: "Endoscopic examination of upper gastrointestinal tract",
    semantic_tag: "procedure",
  },
  has_predecessor: false,
  updated_at: "2026-07-01T09:00:00Z",
};

async function stubGuidanceApis(page: Page) {
  await page.route("**/api/guidance/rules/review*status=pending_review*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([RULE]),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=active*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=superseded*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/guidance/rules/review*status=rejected*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/guidance/rules/review/*/decision", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rule_id: RULE.rule_id }),
    }),
  );
  await page.route("**/api/nice/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  );
  await page.route("**/api/terminology/**", (route) =>
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

async function clickTourNext(page: Page) {
  await page.getByTestId("coach-tour-next").click({ force: true });
}

async function waitForTourStep(page: Page, stepId: string) {
  await expect(page.getByTestId("coach-tour")).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId("coach-tour")).toHaveAttribute(
    "data-tour-step",
    stepId,
    { timeout: 15000 },
  );
  await expect(page.getByTestId("coach-tour-spotlight")).toBeVisible();
  // Let fixed overlay + bubble settle after prepareStep scroll/measure.
  await page.waitForTimeout(250);
}

async function assertCoachTourAxeClean(page: Page) {
  const results = await new AxeBuilder({ page })
    .include('[data-testid="coach-tour"]')
    .withTags([...WCAG_TAGS])
    .analyze();
  const blockers = results.violations.filter(
    (v) => v.impact === "critical" || v.impact === "serious",
  );
  expect(
    blockers,
    JSON.stringify(
      blockers.map((v) => ({
        id: v.id,
        impact: v.impact,
        help: v.help,
      })),
      null,
      2,
    ),
  ).toEqual([]);
}

test.describe("Guideline tab IFU screenshots", () => {
  test.beforeAll(() => {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("Act A: page tour steps produce screenshots", async ({ page }) => {
    test.setTimeout(90_000);
    await stubGuidanceApis(page);
    await page.goto("/admin/knowledge?tab=clinical-guidelines");
    await page.waitForLoadState("load");
    await dismissSplash(page);

    await page.getByTestId("guidance-tour-trigger").click();
    await waitForTourStep(page, PAGE_TOUR_STEPS[0]!.id);
    await assertCoachTourAxeClean(page);

    for (const step of PAGE_TOUR_STEPS) {
      await waitForTourStep(page, step.id);
      // Viewport only: fullPage drops position:fixed tour overlays.
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `${step.id}.png`),
        fullPage: false,
      });
      await clickTourNext(page);
      if (step.id === PAGE_TOUR_STEPS[PAGE_TOUR_STEPS.length - 1]?.id) {
        await expect(page.getByTestId("coach-tour")).toBeHidden({
          timeout: 10000,
        });
      }
    }
  });

  test("Act B: edit-rule tour steps produce screenshots", async ({ page }) => {
    test.setTimeout(120_000);
    await stubGuidanceApis(page);
    await page.goto("/admin/knowledge?tab=clinical-guidelines");
    await page.waitForLoadState("load");
    await dismissSplash(page);

    await page.getByTestId("segmented-tab-review").click();
    await expect(page.locator("#rule-review-body")).toBeVisible();
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
    await page.getByRole("button", { name: `Edit rule ${RULE.rule_id}` }).click();

    const dialog = page.getByRole("dialog", { name: /Change this rule/i });
    await expect(dialog).toBeVisible();

    await dialog.getByTestId("edit-rule-tour-trigger").click();
    await waitForTourStep(page, EDIT_RULE_TOUR_STEPS[0]!.id);
    await assertCoachTourAxeClean(page);

    const seen = new Set<string>();
    for (let i = 0; i < EDIT_RULE_TOUR_STEPS.length + 3; i += 1) {
      const bubble = page.getByTestId("coach-tour");
      const stillOpen = await bubble.isVisible().catch(() => false);
      if (!stillOpen) break;

      const currentId =
        (await bubble.getAttribute("data-tour-step")) || `er-unknown-${i}`;
      if (!seen.has(currentId)) {
        seen.add(currentId);
        await expect(page.getByTestId("coach-tour-spotlight")).toBeVisible();
        await page.screenshot({
          path: path.join(SCREENSHOT_DIR, `${currentId}.png`),
          fullPage: false,
        });
      }

      const next = page.getByTestId("coach-tour-next");
      const label = (await next.textContent())?.trim();
      await clickTourNext(page);
      if (label === "Done") {
        await expect(bubble).toBeHidden({ timeout: 10000 });
        break;
      }
      // Wait until the step id advances (prepare + measure can take >800ms).
      await expect(bubble).toBeVisible({ timeout: 15000 });
      await expect(bubble).not.toHaveAttribute("data-tour-step", currentId, {
        timeout: 15000,
      });
    }

    // Expect the full Act B set when the NG12 fixture can mount each phase.
    for (const step of EDIT_RULE_TOUR_STEPS) {
      expect(
        seen.has(step.id),
        `Missing IFU screenshot for ${step.id}; captured: ${[...seen].join(", ")}`,
      ).toBe(true);
    }
  });
});
