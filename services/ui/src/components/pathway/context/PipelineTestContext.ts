"use client";

import { createContext, useContext } from "react";

export interface StepTraceResult {
  step_id: string;
  subgraph_id: string;
  label: string;
  node_type: string;
  input_state: Record<string, unknown>;
  output_state: Record<string, unknown>;
  duration_ms: number;
  error: string | null;
  status: string;
}

export interface PipelineTestContextValue {
  /** null = no test run yet */
  testTrace: Record<string, StepTraceResult> | null;
  isTestRunning: boolean;
  /** Called when the user clicks an edge to peek at its data */
  onPeekEdge: (sourceNodeId: string, targetNodeId: string) => void;
}

export const PipelineTestContext = createContext<PipelineTestContextValue>({
  testTrace: null,
  isTestRunning: false,
  onPeekEdge: () => undefined,
});

export function usePipelineTest() {
  return useContext(PipelineTestContext);
}
