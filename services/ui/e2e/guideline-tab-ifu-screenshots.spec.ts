/**
 * IFU screenshot pack for the Clinical Guidelines tab CoachTour.
 *
 * Driven by PAGE_TOUR_STEPS / EDIT_RULE_TOUR_STEPS so screenshot
 * filenames never drift from the in-product tour ids.
 *
 * Atlas trace: DI-LEO-AI-121 / DI-42246DA7 (cosmetic coach / editor chrome).
 */
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "path";
import fs from "fs";

import {
  EDIT_RULE_TOUR_STEPS,
  PAGE_TOUR_STEPS,
} from "../src/app/admin/guidance/guidanceTourSteps";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;
const SCREENSHOT_DIR = path.join(__dirname, "screenshots");

const RULE = {
  rule_id: "e2e-ifu-ng12-129",
  name: "E2E -- IFU screenshots",
  status: "pending_review",
  strength: "SHOULD",
  schema_version: 2,
  guideline_id: "NG12",
  guideline_version: 1,
  chapter_title: "Chapter 1",
  recommendation_text:
    "Consider endoscopy in people aged 55 or over with treatment-resistant dyspepsia or upper abdominal pain.",
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
  await page.route("**/api/guidance/**", async (route) => {
    const url = route.request().url();
    if (url.includes("status=pending_review")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([RULE]),
      });
    }
    if (
      url.includes("status=active") ||
      url.includes("status=superseded") ||
      url.includes("status=rejected")
    ) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }
    if (url.includes("/loaded") || url.includes("guidelines")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
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

async function assertNoAxeBlockers(page: Page, include?: string) {
  let builder = new AxeBuilder({ page }).withTags([...WCAG_TAGS]);
  if (include) builder = builder.include(include);
  const results = await builder.analyze();
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
    await stubGuidanceApis(page);
    await page.goto("/admin/knowledge?tab=clinical-guidelines");
    await page.waitForLoadState("load");
    await dismissSplash(page);

    await page.getByTestId("guidance-tour-trigger").click();
    await expect(page.getByTestId("coach-tour")).toBeVisible();

    for (const step of PAGE_TOUR_STEPS) {
      await expect(page.getByTestId("coach-tour")).toHaveAttribute(
        "data-tour-step",
        step.id,
      );
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `${step.id}.png`),
        fullPage: true,
      });
      const next = page.getByTestId("coach-tour-next");
      if (step.id === PAGE_TOUR_STEPS[PAGE_TOUR_STEPS.length - 1]?.id) {
        await next.click();
        await expect(page.getByTestId("coach-tour")).toBeHidden();
      } else {
        await next.click();
      }
    }

    await assertNoAxeBlockers(page);
  });

  test("Act B: edit-rule tour steps produce screenshots", async ({ page }) => {
    await stubGuidanceApis(page);
    await page.goto("/admin/knowledge?tab=clinical-guidelines");
    await page.waitForLoadState("load");
    await dismissSplash(page);

    await page.locator("#rule-review").scrollIntoViewIfNeeded();
    await page
      .getByRole("button", { name: `Toggle rule from ${RULE.guideline_id}` })
      .click();
    await page.getByRole("button", { name: `Edit rule ${RULE.rule_id}` }).click();

    const dialog = page.getByRole("dialog", { name: /Change this rule/i });
    await expect(dialog).toBeVisible();

    await dialog.getByTestId("edit-rule-tour-trigger").click();
    await expect(page.getByTestId("coach-tour")).toBeVisible();

    for (const step of EDIT_RULE_TOUR_STEPS) {
      const bubble = page.getByTestId("coach-tour");
      const stillOpen = await bubble.isVisible().catch(() => false);
      if (!stillOpen) break;

      const currentId = await bubble.getAttribute("data-tour-step");
      // CoachTour may skip missing anchors; screenshot whatever step is showing.
      const fileId = currentId || step.id;
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `${fileId}.png`),
        fullPage: true,
      });

      const next = page.getByTestId("coach-tour-next");
      const label = await next.textContent();
      await next.click();
      if (label?.trim() === "Done") {
        await expect(bubble).toBeHidden();
        break;
      }
    }

    await assertNoAxeBlockers(page, '[role="dialog"]');
  });
});
