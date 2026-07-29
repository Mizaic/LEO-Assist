/**
 * Helpers for CandidateLabTestDialog scoring and selection.
 *
 * Atlas trace:
 *   DO: DO-599B9828
 *   DI: DI-8DD23CE2
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-599B9828")
 */
import type { CandidateTestSummary } from "./bitmapLifecycleHelpers";
import type { MultiRunSheetItem } from "../validation-lab/RunSheetDialog";
import { getRun, scoreRun } from "../validation-lab/labApi";

export const SOFT_CASE_WARN = 10;

export type CaseGoldScore = "pass" | "fail" | "error" | "pending";

export async function scoreSheetItems(
  items: MultiRunSheetItem[],
): Promise<{
  summary: CandidateTestSummary;
  byCase: Record<string, CaseGoldScore>;
}> {
  const byCase: Record<string, CaseGoldScore> = {};
  let passed = 0;
  let failed = 0;
  let errored = 0;

  for (const item of items) {
    if (item.status !== "completed" || !item.runId) {
      byCase[item.caseId] = "error";
      errored += 1;
      continue;
    }
    try {
      const score = (await scoreRun(item.caseId, item.runId)) as {
        pass?: boolean;
      };
      if (score.pass) {
        byCase[item.caseId] = "pass";
        passed += 1;
      } else {
        byCase[item.caseId] = "fail";
        failed += 1;
      }
    } catch {
      byCase[item.caseId] = "error";
      errored += 1;
    }
  }

  return {
    summary: { tested: items.length, passed, failed, errored },
    byCase,
  };
}

export async function loadSbarAssessmentId(
  caseId: string,
  runId: string,
): Promise<string | null> {
  const packed = await getRun(caseId, runId);
  return packed.run.outputs?.sbar_assessment_id || null;
}

export function progressCounts(items: MultiRunSheetItem[]): {
  terminal: number;
  running: number;
  queued: number;
  failed: number;
} {
  return {
    terminal: items.filter(
      (i) => i.status === "completed" || i.status === "failed",
    ).length,
    running: items.filter((i) => i.status === "running").length,
    queued: items.filter((i) => i.status === "queued").length,
    failed: items.filter((i) => i.status === "failed").length,
  };
}

export function goldScoreColor(
  gold: CaseGoldScore,
): "success.main" | "error.main" | "warning.main" {
  if (gold === "pass") return "success.main";
  if (gold === "fail") return "error.main";
  return "warning.main";
}
