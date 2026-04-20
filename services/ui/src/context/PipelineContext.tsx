/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  type ReactNode,
} from "react";
import { usePipelineStream } from "@/hooks/usePipelineStream";
import type { PipelineRunResponse } from "@/lib/types";
import type {
  ClassificationSummary,
  EncounterLogEntry,
  PipelineStreamParams,
  WorkerState,
} from "@/hooks/usePipelineStream";

export interface PipelineContextValue {
  running: boolean;
  status: string | null;
  live: PipelineRunResponse | null;
  result: PipelineRunResponse | null;
  error: string | null;
  workerStates: Record<number, WorkerState>;
  encounterLog: EncounterLogEntry[];
  classification: ClassificationSummary | null;
  start: (params: PipelineStreamParams) => void;
  subscribeToRun: (runId: string) => void;
  cancel: () => void;
}

const PipelineContext = createContext<PipelineContextValue | null>(null);

export function PipelineProvider({ children }: { children: ReactNode }) {
  const stream = usePipelineStream();
  const start = useCallback((params: PipelineStreamParams) => {
    stream.start(params);
  }, [stream.start]);

  const subscribeToRun = useCallback((runId: string) => {
    stream.subscribeToRun(runId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.subscribeToRun]);

  const value: PipelineContextValue = {
    running: stream.running,
    status: stream.status,
    live: stream.live,
    result: stream.result,
    error: stream.error,
    workerStates: stream.workerStates,
    encounterLog: stream.encounterLog,
    classification: stream.classification,
    start,
    subscribeToRun,
    cancel: stream.cancel,
  };

  return (
    <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>
  );
}

export function usePipeline() {
  const ctx = useContext(PipelineContext);
  if (!ctx) {
    throw new Error("usePipeline must be used within PipelineProvider");
  }
  return ctx;
}
