/**
 * My work queue and every in-page task window, including the engineer panel.
 * Named screenshots live in e2e/screenshots/work-task-dialogs/.
 */
import path from "path";
import { expect, test } from "./fixtures";
import { createWalkthroughEvidence } from "./helpers/walkthrough-evidence";
import {
  CODING_REVIEW_ID,
  EXTRACT_TASK_ID,
  GOLD_CANDIDATE_ID,
  PHRASE_PUBLISH_KEY,
  SAFETY_ALERT_ID,
  SURFACE_TASK_ID,
  stubWorkTaskDialogRoutes,
} from "./helpers/work-task-dialog-fixtures";

const SHOT_DIR = path.join(__dirname, "screenshots", "work-task-dialogs");

test.describe("My work task windows walkthrough", () => {
  test("opens every task window and the fix panel", async ({ page }) => {
    test.setTimeout(120_000);
    await stubWorkTaskDialogRoutes(page);
    const evidence = createWalkthroughEvidence(page, SHOT_DIR);

    await page.goto("/work");
    await expect(
      page.getByRole("heading", { name: "My work", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("task-queue-list")).toBeVisible();
    await evidence.shot("my-work-queue");

    await page.getByTestId("task-queue-row-coding_review:" + CODING_REVIEW_ID).click();
    await expect(page.getByTestId("work-task-dialog")).toBeVisible();
    await expect(page.getByTestId("work-fix-panel")).toBeVisible();
    await expect(page.getByText("Engineer panel")).toBeVisible();
    await expect(page.getByText("This phrase is not mapped yet.")).toBeVisible();
    await evidence.shot("coding-review-and-fix-panel");

    const panel = page.getByTestId("work-fix-panel");
    await panel.getByRole("button", { name: "Fix" }).click();
    await page.getByRole("button", { name: "Do not code this" }).click();
    await expect(page.getByLabel("Nearby words (optional)")).toBeVisible();
    await page.getByLabel("Nearby words (optional)").fill("family history");
    await evidence.shot("fix-do-not-code-form");
    await page.getByRole("button", { name: "Do not code this" }).last().click();
    await expect(page.getByText(/Saved as a draft/)).toBeVisible();
    await evidence.shot("fix-do-not-code-saved");

    await page.getByRole("button", { name: "Add a context cue" }).click();
    await expect(page.getByLabel("Meaning")).toBeVisible();
    await evidence.shot("fix-context-cue-form");
    await page.getByRole("button", { name: "Save cue" }).click();
    await expect(page.getByText(/This cue is live now/)).toBeVisible();
    await evidence.shot("fix-context-cue-saved");

    await page.getByRole("button", { name: "Map this phrase" }).click();
    await expect(page.getByLabel("Search SNOMED terms")).toBeVisible();
    await evidence.shot("fix-map-this-phrase");
    await page.keyboard.press("Escape");

    await panel.getByRole("button", { name: "Review" }).click();
    await expect(panel.getByRole("button", { name: "Submit for review" })).toBeEnabled();
    await evidence.shot("engineer-submit-for-review");
    await panel.getByRole("button", { name: "Submit for review" }).click();
    await expect(page.getByText(/Submitted for review/)).toBeVisible();

    await panel.getByRole("button", { name: "Deploy" }).click();
    await expect(panel.getByRole("button", { name: "Publish to live" })).toBeEnabled();
    await evidence.shot("engineer-deploy");
    await panel.getByRole("button", { name: "Publish to live" }).click();
    await expect(page.getByText(/Published. Live coding will use this fix/)).toBeVisible();

    await page.getByRole("button", { name: "Close" }).first().click();
    await expect(page.getByTestId("work-task-dialog")).toHaveCount(0);

    await page
      .getByTestId("task-queue-row-extraction_quality_pause:" + EXTRACT_TASK_ID)
      .click();
    await expect(page.getByText("Check paused extraction")).toBeVisible();
    await expect(page.getByTestId("work-fix-panel")).toBeVisible();
    await expect(page.getByTestId("extraction-quality-letter")).toContainText("HbA1c");
    await evidence.shot("extraction-letter-and-fix-panel");
    await page.getByRole("button", { name: "Close review" }).click();

    await page
      .getByTestId("task-queue-row-surface_form_approval:" + SURFACE_TASK_ID)
      .click();
    await expect(page.getByTestId("work-task-dialog")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Check mapping for T2DM/ }),
    ).toBeVisible();
    await expect(page.getByTestId("work-fix-panel")).toBeVisible();
    await evidence.shot("surface-form-and-fix-panel");
    await page.getByRole("button", { name: "Close" }).first().click();

    await page.getByTestId("task-queue-row-gold_label:" + GOLD_CANDIDATE_ID).click();
    await expect(page.getByTestId("dialog-title-strip")).toBeVisible({
      timeout: 15_000,
    });
    await evidence.shot("gold-label-editor");
    await page.getByTestId("dialog-close-button").click();

    await page.getByTestId("task-queue-row-safety_net_alert:" + SAFETY_ALERT_ID).click();
    await expect(page.getByTestId("work-task-dialog")).toBeVisible();
    await expect(page.getByRole("button", { name: "Resolve" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Escalate" })).toBeVisible();
    await evidence.shot("safety-alert-dialog");
    await page.getByRole("button", { name: "Close" }).first().click();

    // -- Fix -> Submit -> Reviewer task appears -> Publish ----------------
    // Open the engineer panel for the coding review task.
    await page.getByTestId("task-queue-row-coding_review:" + CODING_REVIEW_ID).click();
    await expect(page.getByTestId("work-fix-panel")).toBeVisible();
    // The failure kind headline should lead the Debug pane.
    await expect(page.getByText(/No safe code yet|Wrong kind of code|Check assertion/)).toBeVisible();
    await evidence.shot("engineer-failure-headline");

    // Engineer saves a fix (do-not-code) then submits for review.
    await panel.getByRole("button", { name: "Fix" }).click();
    await page.getByRole("button", { name: "Do not code this" }).click();
    await page.getByRole("button", { name: "Do not code this" }).last().click();
    await expect(page.getByText(/Saved as a draft/)).toBeVisible();
    await panel.getByRole("button", { name: "Review" }).click();
    await panel.getByRole("button", { name: "Submit for review" }).click();
    await expect(page.getByText(/Submitted for review/)).toBeVisible();
    await evidence.shot("engineer-submitted-for-review");
    await page.getByRole("button", { name: "Close" }).first().click();

    // The phrase_publish task is already in the queue (mocked).
    await expect(
      page.getByTestId("task-queue-row-phrase_publish:" + PHRASE_PUBLISH_KEY),
    ).toBeVisible();
    await evidence.shot("reviewer-task-appears");

    // A reviewer opens the publish dialog.
    await page.getByTestId("task-queue-row-phrase_publish:" + PHRASE_PUBLISH_KEY).click();
    await expect(page.getByText("Change to publish")).toBeVisible();
    await expect(page.getByRole("button", { name: "Publish to live" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Send back" })).toBeVisible();
    await evidence.shot("reviewer-publish-dialog");

    // Reviewer publishes.
    await page.getByRole("button", { name: "Publish to live" }).click();
    await expect(
      page.getByText(/Published. The pipeline will use this from the next run/),
    ).toBeVisible();
    await evidence.shot("reviewer-published");

    expect(evidence.count()).toBeGreaterThanOrEqual(13);
  });
});
