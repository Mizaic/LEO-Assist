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

export interface ViewerTraceSnapshot {
  step: StepTraceResult | null;
  source: "single" | "batch" | null;
  candidateId: string | null;
}

export interface PipelineTestContextValue {
  /** null = no test run yet; partial map grows as steps complete during streaming */
  testTrace: Record<string, StepTraceResult> | null;
  /** ID of the step currently executing (null between steps) */
  runningStepId: string | null;
  isTestRunning: boolean;
  /**
   * ID of the node that caused the pipeline to halt (e.g. verification failure).
   * null when the last run completed normally or no run has happened.
   */
  haltedNodeId: string | null;
  /**
   * ID of the furthest node included in the last "Run to here" partial run.
   * null when the last run was a full pipeline run (or no run has happened).
   * Cleared automatically at the start of every new run.
   */
  partialRunEndNodeId: string | null;
  /** Set of edge keys ("sourceId|targetId") the user has clamped a probe onto */
  probedEdges: Set<string>;
  toggleProbe: (sourceNodeId: string, targetNodeId: string) => void;
  /**
   * Run only the pipeline ancestors of `upToNodeId` (inclusive) so the user
   * can validate the output shape at any point in the graph without having
   * completed the full pipeline first.  Re-uses the last test input; if none
   * exists, opens the TestRunDialog.
   */
  runToStep: (upToNodeId: string) => void;
  /**
   * Return the field names that a given step expects to find in pipeline_state
   * (derived from its field_mapping / input_ports config).  Used by the probe
   * monitor to flag connector mismatches.
   */
  getNodeExpectedInputs: (nodeId: string) => string[];
  /**
   * Resolve the most relevant upstream step trace for a canvas viewer node.
   * Uses the currently active inspection trace source (single-run or batch).
   */
  getViewerTraceSnapshot: (viewerNodeId: string) => ViewerTraceSnapshot;
}

export const PipelineTestContext = createContext<PipelineTestContextValue>({
  testTrace: null,
  runningStepId: null,
  isTestRunning: false,
  haltedNodeId: null,
  partialRunEndNodeId: null,
  probedEdges: new Set(),
  toggleProbe: () => undefined,
  runToStep: () => undefined,
  getNodeExpectedInputs: () => [],
  getViewerTraceSnapshot: () => ({ step: null, source: null, candidateId: null }),
});

export function usePipelineTest() {
  return useContext(PipelineTestContext);
}
