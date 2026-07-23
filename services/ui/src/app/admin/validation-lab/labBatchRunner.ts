/**
 * Multi-case Lab queue + live poll orchestration for the run sheet.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-020F98AE, DI-12D40786, DI-2289D095, DI-43E908C6, DI-62175179, DI-9138BAC9, DI-A898556B, DI-FE423B8D
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
import type { LabCase } from "./labApi";
import type { MultiRunSheet, MultiRunSheetItem } from "./RunSheetDialog";
import {
  pollManyCasePipelines,
  queueCasePipelines,
  summarizeLiveResults,
  summarizeQueueResults,
  type ManyRunTick,
  type QueueCaseResult,
} from "./labRun";

export interface BatchRunFeedback {
  notice: string;
  error: string | null;
}

function mapLiveStatus(status: string): MultiRunSheetItem["status"] {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  if (status === "queued") return "queued";
  return "running";
}

export function initialMultiSheet(
  caseIds: string[],
  cases: LabCase[],
): MultiRunSheet {
  const byId = new Map(cases.map((c) => [c.id, c]));
  return {
    mode: "multi",
    items: caseIds.map((caseId) => ({
      caseId,
      title: byId.get(caseId)?.title || caseId,
      status: "pending",
    })),
    phase: "queueing",
    done: false,
  };
}

export function applyQueuePatch(
  sheet: MultiRunSheet,
  result: QueueCaseResult,
): MultiRunSheet {
  return {
    ...sheet,
    items: sheet.items.map((item) =>
      item.caseId !== result.caseId
        ? item
        : {
            ...item,
            status: result.error ? "failed" : "queued",
            runId: result.runId,
            error: result.error,
          },
    ),
  };
}

export function applyLiveTick(
  sheet: MultiRunSheet,
  tick: ManyRunTick,
): MultiRunSheet {
  const cost =
    tick.run.outputs?.llm_usage?.cost_usd ?? tick.run.llm_cost_usd ?? null;
  return {
    ...sheet,
    phase: "watching",
    items: sheet.items.map((item) =>
      item.caseId !== tick.caseId
        ? item
        : {
            ...item,
            runId: tick.runId,
            status: mapLiveStatus(tick.run.status),
            error: tick.run.error_message || undefined,
            costUsd: cost,
          },
    ),
  };
}

/** Queue selected cases then poll live until terminal or cancelled. */
export async function runBatchWithLiveProgress(opts: {
  caseIds: string[];
  cases: LabCase[];
  isOpen: () => boolean;
  onSheet: (updater: (prev: MultiRunSheet) => MultiRunSheet) => void;
}): Promise<BatchRunFeedback> {
  const { caseIds, cases, isOpen, onSheet } = opts;
  const byId = new Map(cases.map((c) => [c.id, c]));

  const results = await queueCasePipelines(
    caseIds.map((caseId) => ({
      caseId,
      planId: byId.get(caseId)?.plan_id,
    })),
    (result) => {
      if (!isOpen()) return;
      onSheet((prev) => applyQueuePatch(prev, result));
    },
  );

  const summary = summarizeQueueResults(results, caseIds.length);
  const active = results
    .filter((r): r is QueueCaseResult & { runId: string } => Boolean(r.runId))
    .map((r) => ({ caseId: r.caseId, runId: r.runId }));

  if (!isOpen() || active.length === 0) {
    return summary;
  }

  onSheet((prev) => ({ ...prev, phase: "watching", done: false }));
  const ticks = await pollManyCasePipelines(
    active,
    (tick) => {
      if (!isOpen()) return;
      onSheet((prev) => applyLiveTick(prev, tick));
    },
    { shouldContinue: isOpen },
  );

  if (!isOpen()) return summary;
  onSheet((prev) => ({ ...prev, done: true }));
  return {
    notice: summarizeLiveResults(
      active.length,
      ticks,
      results.filter((r) => r.error).length,
    ),
    error: summary.error,
  };
}
