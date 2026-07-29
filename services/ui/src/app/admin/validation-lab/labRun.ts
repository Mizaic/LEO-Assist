/**
 * Shared Lab pipeline run defaults for wizard and patient-card Test.
 *
 * Atlas: DI-12D40786 / DI-2289D095 / DI-020F98AE
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
import {
  getRun,
  pollRunUntilTerminal,
  startRun,
  type LabRun,
} from "./labApi";

export const DEFAULT_LAB_PLAN_ID = "pd-referral-assessment";

export const DEFAULT_LAB_PHASES = [
  "extraction",
  "verification",
  "persist",
  "guidance",
  "sbar",
];

export interface QueueCasePlan {
  caseId: string;
  planId?: string | null;
  rulesetVersion?: string | null;
}

export interface QueueCaseResult {
  caseId: string;
  runId?: string;
  error?: string;
}

function productionStartPayload(
  planId?: string | null,
  rulesetVersion?: string | null,
) {
  return {
    plan_id: planId || DEFAULT_LAB_PLAN_ID,
    phase_ids: DEFAULT_LAB_PHASES,
    persist_mode: "production" as const,
    ...(rulesetVersion ? { ruleset_version: rulesetVersion } : {}),
  };
}

/** Start a production Lab run and poll until terminal. */
export async function runCasePipeline(
  caseId: string,
  planId?: string | null,
  rulesetVersion?: string | null,
): Promise<LabRun> {
  const started = await startRun(
    caseId,
    productionStartPayload(planId, rulesetVersion),
  );
  return pollRunUntilTerminal(caseId, started.run.id);
}

/** Queue a production Lab run without waiting for a terminal status. */
export async function queueCasePipeline(
  caseId: string,
  planId?: string | null,
  rulesetVersion?: string | null,
): Promise<LabRun> {
  const started = await startRun(
    caseId,
    productionStartPayload(planId, rulesetVersion),
  );
  return started.run;
}

/** Poll a run and invoke onTick after every status read. */
export async function pollCasePipeline(
  caseId: string,
  runId: string,
  onTick?: (run: LabRun) => void,
  opts?: { intervalMs?: number; timeoutMs?: number },
): Promise<LabRun> {
  const intervalMs = opts?.intervalMs ?? 2000;
  const timeoutMs = opts?.timeoutMs ?? 120000;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const packed = await getRun(caseId, runId);
    onTick?.(packed.run);
    if (
      packed.run.status === "completed" ||
      packed.run.status === "failed" ||
      Date.now() > deadline
    ) {
      return packed.run;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

/**
 * Queue production Lab runs for many cases (set-and-forget / volume test).
 * Does not poll any run to completion so workers can process in parallel.
 */
export async function queueCasePipelines(
  cases: QueueCasePlan[],
  onProgress?: (result: QueueCaseResult) => void,
): Promise<QueueCaseResult[]> {
  const results: QueueCaseResult[] = [];
  // Stagger starts so workers are not flooded with 30+ first steps at once.
  const staggerMs = cases.length > 4 ? 200 : 0;
  for (const item of cases) {
    try {
      const run = await queueCasePipeline(
        item.caseId,
        item.planId,
        item.rulesetVersion,
      );
      const row = { caseId: item.caseId, runId: run.id };
      results.push(row);
      onProgress?.(row);
    } catch (err) {
      const row = {
        caseId: item.caseId,
        error: err instanceof Error ? err.message : "Failed to start run",
      };
      results.push(row);
      onProgress?.(row);
    }
    if (staggerMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, staggerMs));
    }
  }
  return results;
}

export function summarizeQueueResults(
  results: QueueCaseResult[],
  total: number,
): { notice: string; error: string | null } {
  const queued = results.filter((r) => r.runId && !r.error);
  const failed = results.filter((r) => r.error);
  if (failed.length === 0) {
    return {
      notice: `Queued ${queued.length} pipeline run${queued.length === 1 ? "" : "s"}. Watching live progress...`,
      error: null,
    };
  }
  return {
    notice: `Queued ${queued.length} of ${total} pipeline runs. ${failed.length} failed to start.`,
    error: failed
      .slice(0, 3)
      .map((r) => `${r.caseId}: ${r.error}`)
      .join("; "),
  };
}

export interface ActiveLabRun {
  caseId: string;
  runId: string;
}

export interface ManyRunTick {
  caseId: string;
  runId: string;
  run: LabRun;
}

function isTerminalStatus(status: string): boolean {
  return status === "completed" || status === "failed";
}

/** Scale multi-case poll window with batch size (min 10m, max 45m). */
export function batchPollTimeoutMs(caseCount: number): number {
  const perCaseMs = 90_000;
  const floorMs = 600_000;
  const ceilingMs = 2_700_000;
  return Math.min(ceilingMs, Math.max(floorMs, caseCount * perCaseMs));
}

/**
 * Poll many already-queued Lab runs in parallel rounds for live progress.
 * Stops when all are terminal, timeout elapses, or shouldContinue returns false.
 */
export async function pollManyCasePipelines(
  active: ActiveLabRun[],
  onTick: (tick: ManyRunTick) => void,
  opts?: {
    intervalMs?: number;
    timeoutMs?: number;
    shouldContinue?: () => boolean;
  },
): Promise<ManyRunTick[]> {
  const intervalMs = opts?.intervalMs ?? 2000;
  const timeoutMs = opts?.timeoutMs ?? batchPollTimeoutMs(active.length);
  const deadline = Date.now() + timeoutMs;
  const pending = new Map(
    active.map((item) => [item.caseId, item] as const),
  );
  const finals: ManyRunTick[] = [];

  while (pending.size > 0) {
    if (opts?.shouldContinue && !opts.shouldContinue()) break;
    if (Date.now() > deadline) break;

    await Promise.all(
      Array.from(pending.values()).map(async ({ caseId, runId }) => {
        try {
          const packed = await getRun(caseId, runId);
          const tick = { caseId, runId, run: packed.run };
          onTick(tick);
          if (isTerminalStatus(packed.run.status)) {
            pending.delete(caseId);
            finals.push(tick);
          }
        } catch {
          // Leave pending for the next round.
        }
      }),
    );

    if (pending.size === 0) break;
    if (opts?.shouldContinue && !opts.shouldContinue()) break;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  return finals;
}

export function summarizeLiveResults(
  queued: number,
  ticks: ManyRunTick[],
  startFailures: number,
): string {
  const completed = ticks.filter((t) => t.run.status === "completed").length;
  const failed = ticks.filter((t) => t.run.status === "failed").length;
  const parts = [
    `${completed} completed`,
    `${failed} failed`,
    `${queued} queued`,
  ];
  if (startFailures > 0) parts.push(`${startFailures} failed to start`);
  return `Live batch finished: ${parts.join(" · ")}.`;
}
