/**
 * Zipkin-style endpoint detail: upstream/downstream flow links.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { formatStageLabel, formatStageWorkerShort } from "../labRunFormat";
import { statusColor } from "../RunSheetTasks";
import type { LabPlanEdge, LabPlanStep, LabTraceSpan } from "../inspectorTypes";
import {
  buildFlowEndpoints,
  endpointLinkRows,
  resolveFlowLinks,
} from "./traceFlowUtils";
import { formatDurationLabel, spanDurationMs } from "./traceWaterfallUtils";

interface Props {
  stepId: string;
  planSteps: LabPlanStep[];
  planEdges?: LabPlanEdge[];
  spans: LabTraceSpan[];
  onSelectStep: (id: string | null) => void;
}

function LinkTable({
  title,
  caption,
  rows,
  onSelectStep,
}: {
  title: string;
  caption: string;
  rows: ReturnType<typeof endpointLinkRows>;
  onSelectStep: (id: string | null) => void;
}) {
  return (
    <Box>
      <Typography variant="subtitle2" fontWeight={700}>
        {title}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
        {caption}
      </Typography>
      {rows.length === 0 ? (
        <Typography variant="caption" color="text.secondary">
          None
        </Typography>
      ) : (
        <Stack spacing={0.5}>
          {rows.map((row) => (
            <Box
              key={row.stepId}
              onClick={() => onSelectStep(row.stepId)}
              sx={{
                px: 1,
                py: 0.5,
                borderRadius: 1,
                border: "1px solid",
                borderColor: "divider",
                cursor: "pointer",
                "&:hover": { bgcolor: "action.hover" },
              }}
            >
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="caption" fontWeight={600}>
                  {row.label}
                </Typography>
                <Chip
                  size="small"
                  label={row.status}
                  sx={{
                    height: 20,
                    fontSize: 10,
                    color: statusColor(row.status),
                    borderColor: statusColor(row.status),
                  }}
                  variant="outlined"
                />
              </Stack>
              <Typography variant="caption" color="text.secondary" display="block">
                {row.subgraphId || "stage"} · {row.durationLabel}
              </Typography>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}

export function TraceEndpointPanel({
  stepId,
  planSteps,
  planEdges,
  spans,
  onSelectStep,
}: Props) {
  const links = resolveFlowLinks(planSteps, planEdges);
  const endpoints = buildFlowEndpoints(planSteps, spans);
  const current = endpoints.find((item) => item.id === stepId);
  const step = planSteps.find((item) => item.action_id === stepId);
  const span = spans.find((item) => item.step_id === stepId);
  const downstream = endpointLinkRows(stepId, "downstream", endpoints, links);
  const upstream = endpointLinkRows(stepId, "upstream", endpoints, links);

  if (!current) return null;

  return (
    <Box
      data-testid="validation-lab-inspector-endpoint-panel"
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        p: 1.5,
        bgcolor: "background.paper",
        minWidth: 240,
      }}
    >
      <Typography variant="subtitle2" fontWeight={700}>
        {formatStageLabel(stepId)}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block">
        {current.subgraphId || step?.node_type || "endpoint"}
      </Typography>
      <Stack direction="row" spacing={1} sx={{ mt: 0.75, mb: 1 }}>
        <Chip
          size="small"
          label={current.status}
          sx={{ color: statusColor(current.status) }}
          variant="outlined"
        />
        <Typography variant="caption" color="text.secondary">
          {formatDurationLabel(span ? spanDurationMs(span) : current.durationMs)}
        </Typography>
      </Stack>
      {span?.worker_id ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          Worker: {formatStageWorkerShort(span.worker_id)}
        </Typography>
      ) : null}
      {step?.durable_loads?.length ? (
        <Typography variant="caption" color="text.secondary" display="block">
          Loads: {step.durable_loads.join(", ")}
        </Typography>
      ) : null}
      {step?.durable_persists?.length ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          Persists: {step.durable_persists.join(", ")}
        </Typography>
      ) : null}
      <Divider sx={{ my: 1 }} />
      <Stack spacing={1.5}>
        <LinkTable
          title="Downstream"
          caption="Stages this endpoint triggers next."
          rows={downstream}
          onSelectStep={onSelectStep}
        />
        <LinkTable
          title="Upstream"
          caption="Stages that feed this endpoint."
          rows={upstream}
          onSelectStep={onSelectStep}
        />
      </Stack>
    </Box>
  );
}
