/**
 * usePipelineStageRunner -- hook for triggering a pipeline stage test.
 *
 * Calls POST /api/workbench/stage-test with a case ID and rule override,
 * and returns the staged pipeline output as PipelineStage[].
 *
 * Usage:
 *   const { run, loading, stages, error } = usePipelineStageRunner();
 *   await run({ caseId: "abc", ruleId: "R-123" });
 */
"use client";

import { useCallback, useState } from "react";
import type { PipelineStage } from "./StageOutputViewer";

export interface StageTestRequest {
  caseId: string;
  ruleId?: string;
  ruleOverride?: Record<string, unknown>;
}

export interface UsePipelineStageRunnerResult {
  /** Trigger a stage test run. */
  run: (req: StageTestRequest) => Promise<void>;
  /** True while the request is in flight. */
  loading: boolean;
  /** Pipeline stages returned from the last successful run. */
  stages: PipelineStage[];
  /** Error message from the last failed run. */
  error: string | null;
  /** Clear previous results and error. */
  reset: () => void;
}

const STAGE_TEST_URL = "/api/workbench/stage-test";

export function sanitizeStageError(text: string, status: number): string {
  const trimmed = text.trim();
  if (!trimmed) return `The test could not run (HTTP ${status}).`;
  if (trimmed.startsWith("<!") || /^<html/i.test(trimmed)) {
    return `The test service is not available (HTTP ${status}).`;
  }
  if (trimmed.length > 280) return `${trimmed.slice(0, 280)}...`;
  return trimmed;
}

export function usePipelineStageRunner(): UsePipelineStageRunnerResult {
  const [loading, setLoading] = useState(false);
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setStages([]);
    setError(null);
  }, []);

  const run = useCallback(async (req: StageTestRequest) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(STAGE_TEST_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        throw new Error(sanitizeStageError(text || "", res.status));
      }
      const data = (await res.json()) as { stages: PipelineStage[] };
      setStages(data.stages ?? []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  return { run, loading, stages, error, reset };
}
