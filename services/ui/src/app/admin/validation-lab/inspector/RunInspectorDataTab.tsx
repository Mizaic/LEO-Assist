/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import {
  collectStateChanges,
  labelForChange,
  toneForChange,
} from "@/lib/pipelineStateDiff";
import { formatStageLabel } from "../labRunFormat";
import type { LabStageDetail, LabTraceSpan } from "../inspectorTypes";

interface Props {
  spans: LabTraceSpan[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
  loading: boolean;
}

export function RunInspectorDataTab({
  spans,
  selectedStepId,
  onSelectStep,
  stageDetail,
  loading,
}: Props) {
  const changes =
    stageDetail?.input != null || stageDetail?.output != null
      ? collectStateChanges(stageDetail?.input ?? {}, stageDetail?.output ?? {})
      : [];

  return (
    <Stack spacing={1.5} data-testid="validation-lab-inspector-data">
      <Typography variant="body2" color="text.secondary">
        Select a span on the Trace tab, or pick a completed stage below.
      </Typography>
      <Stack spacing={0.5}>
        {spans.map((span) => (
          <Typography
            key={span.step_id}
            variant="body2"
            sx={{
              cursor: "pointer",
              color: selectedStepId === span.step_id ? "primary.main" : "text.primary",
            }}
            onClick={() => onSelectStep(span.step_id)}
          >
            {formatStageLabel(span.step_id)} ({span.status})
          </Typography>
        ))}
      </Stack>
      {loading ? (
        <Typography variant="body2" color="text.secondary">
          Loading stage detail...
        </Typography>
      ) : null}
      {stageDetail?.truncated ? (
        <Typography variant="caption" color="warning.main">
          Payload truncated for display. Use support export for full JSON.
        </Typography>
      ) : null}
      {selectedStepId && !loading && changes.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No input/output diff yet for {formatStageLabel(selectedStepId)}.
        </Typography>
      ) : null}
      {changes.map((change, index) => (
        <Stack key={`${change.kind}-${index}`} spacing={0.25}>
          <Typography variant="caption" sx={{ color: toneForChange(change.kind) }}>
            {labelForChange(change.kind)} · {change.path.join(".")}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}
