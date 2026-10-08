/**
 * VAL-4E9520BE -- a teacher saves a form whose letter has admin tick boxes.
 *
 * Atlas:
 *   UN: UN-AF530E8E
 *   DI: DI-455C4EF1
 *   VAL: VAL-4E9520BE
 *
 * Detect and save run through the real form-schema router. Only the
 * language model detector and the graph are replaced (see
 * helpers/form_schema_router_bridge.py). Named screenshots are written to
 * e2e/screenshots/add-form-template-skip-boxes/ on every run. When Atlas
 * validation env is set, the run is also recorded in Atlas with the same
 * screenshots as step evidence.
 */
import fs from "fs";
import path from "path";
import type { Page } from "@playwright/test";

import { expect, test, waitForPageSettled } from "./fixtures";
import {
  HOSPITAL_BOXES,
  LOWER_GI_LETTER,
  SKIP_BOX_FINGERPRINT,
  SKIP_BOX_FORM_NAME,
  stubAddTemplateRoutes,
  type SaveLog,
} from "./helpers/form-template-skip-boxes-fixtures";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest, type ValRunContext } from "./helpers/validation-spec-runner";
import { isAtlasValidationConfigured, loadPlaywrightEnv } from "./helpers/validation-env";

loadPlaywrightEnv();

const VAL_ID = "VAL-4E9520BE";
const UN_ID = "UN-AF530E8E";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const SHOT_DIR = path.join(__dirname, "screenshots", "add-form-template-skip-boxes");
const ROUTER_TIMEOUT = 120_000;

const PROTOCOL = [
  "Paste the Lower GI letter into Add form template and open the schema editor. Open the Hospital Use Only section. You should see its tick boxes listed: Pt Contacted, Interpreter Booked, Transport Booked and Accepted. You should be told LEO skips them.",
  "Remove the Hospital Use Only section and click Save schema. You should see a message that names the lines the form does not cover and says nothing was saved.",
  "Click Ask LEO again, then Save schema. The editor should close with no error, and the new form should be in the form template library.",
] as const;

const SLUGS = ["admin-boxes-listed", "refusal-names-lines", "saved-in-library"] as const;

type StepRecorder = (stepIndex: number, notes: string) => Promise<void>;

async function shot(page: Page, stepIndex: number): Promise<string> {
  const name = `${UN_ID}__${VAL_ID}__0${stepIndex + 1}-${SLUGS[stepIndex]}.png`;
  const file = path.join(SHOT_DIR, name);
  await page.screenshot({ path: file, fullPage: false });
  return file;
}

function hospitalCard(page: Page) {
  return page.getByRole("article", { name: /Form section S5: Hospital Use Only/ });
}

async function openEditor(page: Page): Promise<void> {
  await page.goto("/settings/form-schemas");
  await waitForPageSettled(page);
  const dialog = page.getByTestId("form-schema-add-dialog");
  await expect(async () => {
    await page.getByRole("button", { name: "Add template" }).click();
    await expect(dialog).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 60_000 });
  await dialog.getByRole("textbox", { name: "Sample referral letter" }).fill(LOWER_GI_LETTER);
  await dialog.getByRole("textbox", { name: "Form name" }).fill(SKIP_BOX_FORM_NAME);
  await dialog.getByRole("button", { name: "Open schema editor" }).click();
  await expect(hospitalCard(page)).toBeVisible({ timeout: ROUTER_TIMEOUT });
}

async function stepSeeAdminBoxes(page: Page, record: StepRecorder): Promise<void> {
  await openEditor(page);
  const card = hospitalCard(page);
  await card.getByRole("button", { name: "Expand section" }).click();
  const list = card.getByRole("list", { name: "Tick boxes in this section" });
  await expect(list.getByRole("listitem")).toHaveText(HOSPITAL_BOXES);
  await expect(card.getByText(/LEO skips these/)).toBeVisible();
  await list.getByRole("listitem").last().scrollIntoViewIfNeeded();
  await record(0, "The Hospital Use Only section lists its 4 tick boxes and says LEO skips them.");
}

async function stepRefusalNamesLines(
  page: Page,
  log: SaveLog,
  record: StepRecorder,
): Promise<void> {
  const card = hospitalCard(page);
  await card.getByRole("button", { name: "Remove section" }).click();
  await card.getByRole("button", { name: "Yes" }).click();
  await expect(hospitalCard(page)).toHaveCount(0);
  await page.getByRole("button", { name: "Save schema" }).click();
  const refusal = page.getByText(
    "These lines on the letter are not in the form: Pt Contacted, Interpreter Booked, Transport Booked.",
    { exact: false },
  );
  await expect(refusal).toBeVisible({ timeout: ROUTER_TIMEOUT });
  await expect(refusal).toContainText("Nothing was saved.");
  expect(log.accepted).toHaveLength(0);
  await record(1, "Save was refused. The message names the 3 lines the form does not cover.");
}

async function stepSaveAndSeeLibrary(
  page: Page,
  log: SaveLog,
  record: StepRecorder,
): Promise<void> {
  await page.getByRole("button", { name: "Ask LEO again" }).click();
  await expect(hospitalCard(page)).toBeVisible({ timeout: ROUTER_TIMEOUT });
  await page.getByRole("button", { name: "Save schema" }).click();
  await expect(page.getByTestId("form-schema-add-dialog")).toHaveCount(0, {
    timeout: ROUTER_TIMEOUT,
  });
  const card = page.getByTestId("form-schema-card").filter({ hasText: SKIP_BOX_FINGERPRINT });
  await expect(card).toBeVisible({ timeout: 15_000 });
  expect(log.accepted).toHaveLength(1);
  const saved = log.accepted[0].sections as Array<{
    section_id: string;
    items: Array<{ pattern: string }>;
  }>;
  const hospital = saved.find((s) => s.section_id === "S5");
  expect(hospital?.items.map((i) => i.pattern)).toEqual(HOSPITAL_BOXES);
  await record(2, "The form saved with no edits and is in the form template library.");
}

async function walkJourney(page: Page, record: StepRecorder): Promise<void> {
  const log = await stubAddTemplateRoutes(page);
  await stepSeeAdminBoxes(page, record);
  await stepRefusalNamesLines(page, log, record);
  await stepSaveAndSeeLibrary(page, log, record);
}

test.describe("VAL-4E9520BE add form template with admin tick boxes @val", () => {
  test.setTimeout(600_000);

  test.beforeAll(() => {
    fs.rmSync(SHOT_DIR, { recursive: true, force: true });
    fs.mkdirSync(SHOT_DIR, { recursive: true });
  });

  test(
    "saves a taught form whose letter has admin tick boxes",
    {
      tag: ["@UN-AF530E8E", "@VAL-4E9520BE"],
      annotation: [
        {
          type: "Atlas VAL",
          description: "VAL-4E9520BE - Teacher saves a form whose letter has admin tick boxes",
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
        metadata: { atlas_un_id: UN_ID, atlas_di_ids: ["DI-455C4EF1"] },
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
            "Teacher saw the skipped tick boxes, got a refusal naming missing lines, and saved the Lower GI form with no edits.",
          );
        },
      });
    },
  );
});
