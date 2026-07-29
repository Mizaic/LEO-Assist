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

/**
 * One representative frame per protocol step. Resolve by slug substring
 * against the numbered 1.1.2 pack (NNN-slug.png) so renumbering does not
 * break the VAL when the walkthrough adds intermediate click frames.
 */
const STEP_EVIDENCE_SLUGS = [
  /review-pool-card-before-edit/,
  /who-always-true/,
  /situations-split-confirm/,
  /situation-a-all-symptoms-coded/,
  /suggest-action-coded/,
  /save-reason-filled/,
  /review-pool-after-save/,
] as const;

function resolveEvidenceFile(slugPattern: RegExp): string {
  if (!fs.existsSync(SHOT_DIR)) {
    throw new Error(
      `Missing walkthrough pack dir ${SHOT_DIR}. Run ng12-1-1-2-rule-build-walkthrough.spec.ts first.`,
    );
  }
  const matches = fs
    .readdirSync(SHOT_DIR)
    .filter((name) => name.endsWith(".png") && slugPattern.test(name))
    .sort();
  if (matches.length === 0) {
    throw new Error(
      `No screenshot in ${SHOT_DIR} matching ${slugPattern}. ` +
        "Run ng12-1-1-2-rule-build-walkthrough.spec.ts first.",
    );
  }
  return matches[0]!;
}

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
    for (const slug of STEP_EVIDENCE_SLUGS) {
      expect(fs.existsSync(evidencePath(resolveEvidenceFile(slug)))).toBe(true);
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
            "ng12-1-3-2",
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
            const fileName = resolveEvidenceFile(STEP_EVIDENCE_SLUGS[stepIndex]!);
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
