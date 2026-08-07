/**
 * Data flow tab: Zipkin waterfall plus stage input/output diff.
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
import type { LabStageDetail, LabTraceSpan } from "../inspectorTypes";
import { TraceWaterfallChart } from "./TraceWaterfallChart";

interface Props {
  spans: LabTraceSpan[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
  loading: boolean;
}

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
      <TraceWaterfallChart
        spans={spans}
        selectedStepId={selectedStepId}
        onSelectStep={onSelectStep}
        compact
      />
      <Divider />
      {!selectedStepId ? (
        <Typography variant="body2" color="text.secondary">
          Select a span above to view input/output changes for that stage.
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
            maxHeight: 320,
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
