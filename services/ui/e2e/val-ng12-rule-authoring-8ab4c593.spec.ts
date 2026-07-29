/**
 * VAL-8AB4C593 -- Guided NG12 recommendation rule authoring walkthrough.
 *
 * Atlas artefacts
 *   VAL : VAL-8AB4C593
 *   UN  : UN-49C83395   Load, Review, and Publish Guideline Rules
 *   DI  : DI-42246DA7   Review, Edit, Approve, or Reject Guideline Rules
 *   DO  : DO-F8C56339   Rule generation, review, and edit surface
 *
 * Uploads the NG12 1.1.2 walkthrough screenshot pack as step evidence.
 * Sister walkthroughs under e2e/ng12-*-rule-build-walkthrough.spec.ts
 * exercise the same DI surface (1.3.x, 1.5.x, 1.7.x).
 */

import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import {
  atlasValidationSkipReason,
  isAtlasValidationConfigured,
  loadPlaywrightEnv,
} from "./helpers/validation-env";
import { assertValidationRunConfig } from "./helpers/atlas-validation-runs";
import { recordProtocolStep } from "./helpers/leo-validation-steps";
import { finishValPass, runValTest } from "./helpers/validation-spec-runner";

loadPlaywrightEnv();

const VAL_ID = "VAL-8AB4C593";
const UN_ID = "UN-49C83395";
const TARGET_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const SHOT_DIR = path.join(__dirname, "screenshots", "ng12-1-1-2");

const PROTOCOL = [
  "Open /admin/knowledge?tab=clinical-guidelines, open pending review, expand the NG12 1.1.2 rule card, and open Edit rule.",
  "On Who, confirm always-true criteria (for example age band) and proceed to Situations.",
  "Split or confirm situations so recommendation branches are clear (for example situation A cluster vs situation B).",
  "Code situation conditions with clinical terms; confirm coded chips and any Copy across offer when shared lists apply.",
  "Reach Suggest; set priority and strength; confirm uncoded then coded action as required by the recommendation.",
  "Open Save, enter a change reason, and Approve and save. Confirm the dialog closes and the edit decision was posted.",
  "Confirm the walkthrough screenshot pack for the protocol steps is attached to the Atlas execution run.",
] as const;

/** One representative screenshot per protocol step from the 1.1.2 pack. */
const STEP_EVIDENCE = [
  "01-review-pool-card.png",
  "02-who-always-true-age.png",
  "03-situations-split-confirm.png",
  "05-situation-a-all-symptoms-coded.png",
  "13-suggest-action-coded.png",
  "20-save-reason-filled.png",
  "22-review-pool-after-save.png",
] as const;

function evidencePath(fileName: string): string {
  const full = path.join(SHOT_DIR, fileName);
  if (!fs.existsSync(full)) {
    throw new Error(
      `Missing walkthrough evidence ${full}. Run ng12-1-1-2-rule-build-walkthrough.spec.ts first.`,
    );
  }
  return full;
}

test.describe("VAL-8AB4C593 NG12 guided rule authoring @val", () => {
  test.setTimeout(180_000);

  test.beforeAll(() => {
    test.skip(!isAtlasValidationConfigured(), atlasValidationSkipReason());
    assertValidationRunConfig();
    for (const fileName of STEP_EVIDENCE) {
      expect(fs.existsSync(path.join(SHOT_DIR, fileName))).toBe(true);
    }
  });

  test(
    "uploads NG12 1.1.2 walkthrough screenshots as validation evidence",
    {
      tag: ["@UN-49C83395", "@VAL-8AB4C593"],
      annotation: [
        {
          type: "Atlas VAL",
          description:
            "VAL-8AB4C593 - Guided NG12 recommendation rule authoring",
        },
      ],
    },
    async ({ page, request }, testInfo) => {
      await runValTest(page, request, testInfo, {
        valId: VAL_ID,
        targetUrl: TARGET_URL,
        metadata: {
          atlas_un_id: UN_ID,
          atlas_di_id: "DI-42246DA7",
          evidence_source: "ng12-1-1-2-rule-build-walkthrough.spec.ts",
          sister_walkthroughs: [
            "ng12-1-3-1",
            "ng12-1-3-3",
            "ng12-1-5-2",
            "ng12-1-5-5",
            "ng12-1-7-1",
            "ng12-1-7-2",
            "ng12-1-7-6",
            "ng12-1-7-7",
          ],
        },
        protocol: PROTOCOL,
        body: async (ctx) => {
          // Lightweight live check that the guidelines surface is reachable.
          await ctx.page.goto("/admin/knowledge?tab=clinical-guidelines");
          await ctx.page.waitForLoadState("load");

          for (let stepIndex = 0; stepIndex < PROTOCOL.length; stepIndex++) {
            const fileName = STEP_EVIDENCE[stepIndex];
            await recordProtocolStep({
              request: ctx.request,
              runId: ctx.runId,
              valId: ctx.valId,
              page: ctx.page,
              testInfo: ctx.testInfo,
              protocol: ctx.protocol,
              stepIndex,
              evidencePath: evidencePath(fileName),
              notes:
                `Evidence from ng12-1-1-2 walkthrough pack (${fileName}). ` +
                "Sister NG12 rule-build walkthroughs cover the same DI-42246DA7 surface.",
            });
            ctx.lastCompletedStep.value = stepIndex;
          }

          await finishValPass(
            ctx.request,
            ctx.runId,
            "VAL-8AB4C593 passed: NG12 1.1.2 walkthrough screenshot pack uploaded for all protocol steps.",
          );
        },
      });
    },
  );
});
