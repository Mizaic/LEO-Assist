/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { formatStageLabel, formatStageWorkerShort } from "../labRunFormat";
import { statusColor } from "../RunSheetTasks";
import type { LabPlanStep, LabTraceSpan } from "../inspectorTypes";

interface Props {
  spans: LabTraceSpan[];
  planSteps: LabPlanStep[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
}

function spanDurationMs(span: LabTraceSpan): number | null {
  if (span.duration_ms != null) return span.duration_ms;
  if (!span.started_at || !span.completed_at) return null;
  const start = Date.parse(span.started_at);
  const end = Date.parse(span.completed_at);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return Math.max(0, end - start);
}

export function RunInspectorTraceTab({
  spans,
  planSteps,
  selectedStepId,
  onSelectStep,
}: Props) {
  const ordered =
    spans.length > 0
      ? spans
      : planSteps.map((s) => ({
          step_id: s.action_id,
          status: "pending",
          subgraph_id: s.subgraph_id,
        }));

  const maxMs = Math.max(
    1,
    ...ordered.map((s) => spanDurationMs(s as LabTraceSpan) || 0),
  );

  return (
    <Stack spacing={1} data-testid="validation-lab-inspector-trace">
      {ordered.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No spans yet. Bootstrap and durable steps appear here as they run.
        </Typography>
      ) : (
        ordered.map((span) => {
          const ms = spanDurationMs(span as LabTraceSpan);
          const width = ms != null ? Math.max(4, (ms / maxMs) * 100) : 8;
          const selected = selectedStepId === span.step_id;
          return (
            <Box
              key={span.step_id}
              onClick={() => onSelectStep(span.step_id)}
              sx={{
                p: 1,
                borderRadius: 1,
                border: "1px solid",
                borderColor: selected ? "primary.main" : "divider",
                cursor: "pointer",
              }}
              data-testid={`validation-lab-inspector-span-${span.step_id}`}
            >
              <Stack direction="row" justifyContent="space-between" spacing={1}>
                <Typography variant="body2" fontWeight={600}>
                  {formatStageLabel(span.step_id)}
                </Typography>
                <Typography variant="caption" color={statusColor(span.status)}>
                  {span.status}
                </Typography>
              </Stack>
              {span.worker_id ? (
                <Typography variant="caption" color="text.secondary">
                  {formatStageWorkerShort(span.worker_id)}
                </Typography>
              ) : null}
              <LinearProgress
                variant="determinate"
                value={width}
                sx={{ mt: 0.75, height: 6, borderRadius: 1 }}
              />
              {ms != null ? (
                <Typography variant="caption" color="text.secondary">
                  {ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`}
                </Typography>
              ) : null}
            </Box>
          );
        })
      )}
    </Stack>
  );
}
