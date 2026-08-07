/**
 * Data flow tab: Zipkin-style endpoint map, timeline, and state diff.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import {
  collectStateChanges,
  formatPrimitive,
  labelForChange,
  safeStringify,
  toneForChange,
  type StateChange,
} from "@/lib/pipelineStateDiff";
import { formatStageLabel } from "../labRunFormat";
import type {
  LabPlanEdge,
  LabPlanStep,
  LabStageDetail,
  LabTraceSpan,
} from "../inspectorTypes";
import { TraceEndpointPanel } from "./TraceEndpointPanel";
import { TraceFlowGraph } from "./TraceFlowGraph";
import { TraceWaterfallChart } from "./TraceWaterfallChart";

interface Props {
  spans: LabTraceSpan[];
  planSteps: LabPlanStep[];
  planEdges?: LabPlanEdge[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
  loading: boolean;
}

type DataView = "map" | "timeline";

function formatChangeValue(value: unknown): string {
  if (value === undefined) return "(none)";
  if (value === null) return "null";
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return formatPrimitive(value);
  }
  return safeStringify(value, 2);
}

function DiffChangeRow({ change, index }: { change: StateChange; index: number }) {
  const [open, setOpen] = useState(false);
  const pathLabel = change.path.join(".");

  return (
    <Box
      sx={{
        borderBottom: "1px solid",
        borderColor: "divider",
        pb: 0.5,
        mb: 0.5,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={0.5}>
        <IconButton
          size="small"
          aria-label={open ? "Collapse diff" : "Expand diff"}
          aria-expanded={open}
          onClick={() => setOpen((prev) => !prev)}
          sx={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.15s ease",
          }}
        >
          <ExpandMoreIcon fontSize="small" />
        </IconButton>
        <Typography variant="caption" sx={{ color: toneForChange(change.kind), flex: 1 }}>
          {labelForChange(change.kind)} · {pathLabel}
        </Typography>
      </Stack>
      <Collapse in={open}>
        <Stack spacing={0.5} sx={{ pl: 4, pb: 0.5 }}>
          {change.kind !== "added" ? (
            <Typography
              variant="caption"
              component="pre"
              sx={{
                m: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: "#f38ba8",
                fontFamily: "monospace",
              }}
            >
              before: {formatChangeValue(change.beforeValue)}
            </Typography>
          ) : null}
          {change.kind !== "removed" ? (
            <Typography
              variant="caption"
              component="pre"
              sx={{
                m: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: "#a6e3a1",
                fontFamily: "monospace",
              }}
            >
              after: {formatChangeValue(change.afterValue)}
            </Typography>
          ) : null}
        </Stack>
      </Collapse>
    </Box>
  );
}

export function RunInspectorDataTab({
  spans,
  planSteps,
  planEdges,
  selectedStepId,
  onSelectStep,
  stageDetail,
  loading,
}: Props) {
  const [view, setView] = useState<DataView>("map");
  const ordered: LabTraceSpan[] =
    spans.length > 0
      ? spans
      : planSteps.map((step) => ({
          step_id: step.action_id,
          status: "pending",
          subgraph_id: step.subgraph_id,
        }));

  const changes =
    stageDetail?.input != null || stageDetail?.output != null
      ? collectStateChanges(stageDetail?.input ?? {}, stageDetail?.output ?? {})
      : [];

  return (
    <Stack
      spacing={1.5}
      data-testid="validation-lab-inspector-data"
      sx={{ flex: 1, minHeight: 0, overflow: "auto" }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="body2" color="text.secondary">
          Pipeline endpoints and how data flows between stages.
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={view}
          onChange={(_, next: DataView | null) => {
            if (next) setView(next);
          }}
          aria-label="Data flow view"
        >
          <ToggleButton value="map" aria-label="Flow map">
            Flow map
          </ToggleButton>
          <ToggleButton value="timeline" aria-label="Timeline">
            Timeline
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      {view === "map" ? (
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={1.5}
          alignItems="stretch"
        >
          <Box
            sx={{
              flex: 1,
              minWidth: 0,
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              overflow: "hidden",
              bgcolor: "grey.50",
            }}
          >
            <TraceFlowGraph
              planSteps={planSteps}
              planEdges={planEdges}
              spans={ordered}
              selectedStepId={selectedStepId}
              onSelectStep={onSelectStep}
            />
          </Box>
          {selectedStepId ? (
            <TraceEndpointPanel
              stepId={selectedStepId}
              planSteps={planSteps}
              planEdges={planEdges}
              spans={ordered}
              onSelectStep={onSelectStep}
            />
          ) : null}
        </Stack>
      ) : (
        <Box
          sx={{
            minHeight: 160,
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1.5,
            bgcolor: "background.paper",
          }}
        >
          <TraceWaterfallChart
            spans={ordered}
            selectedStepId={selectedStepId}
            onSelectStep={onSelectStep}
          />
        </Box>
      )}

      <Divider />
      {!selectedStepId ? (
        <Typography variant="body2" color="text.secondary">
          Select an endpoint to inspect upstream/downstream links and state changes.
        </Typography>
      ) : null}
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
      {changes.length > 0 ? (
        <Box
          sx={{
            flex: 1,
            minHeight: 160,
            maxHeight: 280,
            overflow: "auto",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
            p: 1,
          }}
        >
          {changes.map((change, index) => (
            <DiffChangeRow key={`${change.kind}-${index}`} change={change} index={index} />
          ))}
        </Box>
      ) : null}
    </Stack>
  );
}
