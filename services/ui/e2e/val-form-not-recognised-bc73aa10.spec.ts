/**
 * VAL-BC73AA10 -- a reviewer is stopped by an unrecognised referral form.
 *
 * Atlas:
 *   UN: UN-AF530E8E
 *   DI: DI-E21DF9EF
 *   VAL: VAL-BC73AA10
 *
 * Review APIs are stubbed. This run does not start a live pipeline.
 * Named screenshots are written to e2e/screenshots/form-not-recognised/
 * on every run. When Atlas validation env is set, the run is also
 * recorded in Atlas with the same screenshots as step evidence.
 */
import fs from "fs";
import path from "path";
import type { Page } from "@playwright/test";

import { expect, test, waitForPageSettled } from "./fixtures";
import {
  CLOSEST_FORM,
  FNR_PATIENT_ID,
  FNR_TASK_ID,
  stubFormNotRecognisedRoutes,
} from "./helpers/form-not-recognised-fixtures";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest, type ValRunContext } from "./helpers/validation-spec-runner";
import { isAtlasValidationConfigured, loadPlaywrightEnv } from "./helpers/validation-env";

loadPlaywrightEnv();

const VAL_ID = "VAL-BC73AA10";
const UN_ID = "UN-AF530E8E";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const SHOT_DIR = path.join(__dirname, "screenshots", "form-not-recognised");

const PROTOCOL = [
  "Open My work. You should see a task for the paused referral that says Form not recognised.",
  "Open the task. You should see the closest taught form and the headings it was missing.",
  "Click Teach this form. You should see the teach page for this letter.",
  "Look at the paused referral. You should not see a finished SBAR.",
] as const;

const SLUGS = ["my-work-task", "closest-form", "teach-page", "no-sbar"] as const;

type StepRecorder = (stepIndex: number, notes: string) => Promise<void>;

async function shot(page: Page, stepIndex: number): Promise<string> {
  const name = `${UN_ID}__${VAL_ID}__0${stepIndex + 1}-${SLUGS[stepIndex]}.png`;
  const file = path.join(SHOT_DIR, name);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

async function walkJourney(page: Page, record: StepRecorder): Promise<void> {
  await stubFormNotRecognisedRoutes(page);
  await page.goto("/work");
  await waitForPageSettled(page);
  await expect(page.getByRole("heading", { name: "My work", level: 1 })).toBeVisible({
    timeout: 15_000,
  });
  const row = page.getByTestId("task-queue-row-extraction_quality_pause:" + FNR_TASK_ID);
  await expect(row).toContainText("Form not recognised: " + FNR_PATIENT_ID);
  await record(0, "My work lists the paused referral as Form not recognised.");

  await row.click();
  const notice = page.getByTestId("form-recognition-notice");
  await expect(notice).toContainText(
    "We did not recognise this form. Teach it, then run extraction again.",
  );
  await expect(notice).toContainText(`Closest taught form: ${CLOSEST_FORM}.`);
  await expect(notice).toContainText("We found 1 of its 4 headings.");
  await expect(notice).toContainText("Headings we could not find:");
  await expect(notice).toContainText("Gynaecological cancer type suspected");
  await record(1, "The review shows the closest taught form and the missing headings.");

  await notice.getByRole("button", { name: "Teach this form" }).click();
  await expect(page.getByRole("tab", { name: "Teach this form" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByRole("button", { name: "Save schema" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/we check this form against the letter/)).toBeVisible();
  await expect(page.getByText(/Could not load organisations/)).toHaveCount(0);
  await record(2, "Teach this form opened the teach page for this letter.");

  const dialog = page.getByTestId("extraction-quality-review-dialog");
  await expect(dialog).toContainText("Check paused extraction");
  await expect(dialog.getByText(/SBAR/i)).toHaveCount(0);
  await record(3, "The paused referral shows no finished SBAR.");
}

test.describe("VAL-BC73AA10 form not recognised @val", () => {
  test.setTimeout(300_000);

  test.beforeAll(() => {
    fs.rmSync(SHOT_DIR, { recursive: true, force: true });
    fs.mkdirSync(SHOT_DIR, { recursive: true });
  });

  test(
    "stops the reviewer at an unrecognised form and offers Teach this form",
    {
      tag: ["@UN-AF530E8E", "@VAL-BC73AA10"],
      annotation: [
        {
          type: "Atlas VAL",
          description: "VAL-BC73AA10 - Reviewer is stopped by an unrecognised referral form",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      if (!isAtlasValidationConfigured()) {
        await walkJourney(page, async (stepIndex) => {
          await shot(page, stepIndex);
        });
        return;
      }
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: { atlas_un_id: UN_ID, atlas_di_ids: ["DI-E21DF9EF"] },
        protocol: PROTOCOL,
        body: async (ctx: ValRunContext) => {
          await walkJourney(ctx.page, async (stepIndex, notes) => {
            await recordProtocolStep({
              request: ctx.request,
              runId: ctx.runId,
              valId: ctx.valId,
              page: ctx.page,
              testInfo: ctx.testInfo,
              protocol: PROTOCOL,
              stepIndex,
              notes,
              evidencePath: await shot(ctx.page, stepIndex),
            });
            ctx.lastCompletedStep.value = stepIndex;
          });
          await finishValPass(
            ctx.request,
            ctx.runId,
            "Reviewer saw Form not recognised on My work, the closest form and missing headings, and opened Teach this form.",
          );
        },
      });
    },
  );
});
