/**
 * Zipkin-style trace waterfall tab for Validation Lab run inspector.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 */
"use client";

import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { LabPlanStep, LabTraceSpan } from "../inspectorTypes";
import { TraceWaterfallChart } from "./TraceWaterfallChart";

interface Props {
  spans: LabTraceSpan[];
  planSteps: LabPlanStep[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
}

export function RunInspectorTraceTab({
  spans,
  planSteps,
  selectedStepId,
  onSelectStep,
}: Props) {
  const ordered: LabTraceSpan[] =
    spans.length > 0
      ? spans
      : planSteps.map((step) => ({
          step_id: step.action_id,
          status: "pending",
          subgraph_id: step.subgraph_id,
        }));

  return (
    <Stack spacing={1} data-testid="validation-lab-inspector-trace">
      <Typography variant="body2" color="text.secondary">
        Click a span to inspect state changes on the Data flow tab.
      </Typography>
      <TraceWaterfallChart
        spans={ordered}
        selectedStepId={selectedStepId}
        onSelectStep={onSelectStep}
      />
    </Stack>
  );
}
