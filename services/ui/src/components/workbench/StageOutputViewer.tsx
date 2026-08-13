/**
 * StageOutputViewer -- pipeline stage-by-stage process-mining inspector.
 *
 * Renders each pipeline stage as an expandable card showing:
 * - Input (what the stage received)
 * - What happened (prompt / rule applied / guard outcome)
 * - Output (what was emitted downstream)
 *
 * Used by the Validation Lab run review and the Workbench live test preview.
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";

export type StageStatus = "passed" | "failed" | "skipped" | "running";

export interface PipelineStage {
  name: string;
  status: StageStatus;
  /** Plain-English description of what this stage does. */
  description?: string;
  /** What the stage received as input. */
  input?: unknown;
  /** What the stage produced as output. */
  output?: unknown;
  /** Error message when status is "failed". */
  error?: string;
  /** LLM telemetry (prompt tokens, cost, model) when relevant. */
  llmTelemetry?: {
    model?: string;
    promptTokens?: number;
    completionTokens?: number;
    estimatedCostGbp?: number;
  };
}

interface StatusBadgeProps {
  status: StageStatus;
}

function StatusBadge({ status }: StatusBadgeProps) {
  const config: Record<StageStatus, { label: string; color: "success" | "error" | "default" | "warning"; icon: React.ReactNode }> = {
    passed: { label: "Passed", color: "success", icon: <CheckCircleOutlineIcon fontSize="small" /> },
    failed: { label: "Failed", color: "error", icon: <ErrorOutlineIcon fontSize="small" /> },
    skipped: { label: "Skipped", color: "default", icon: <RemoveCircleOutlineIcon fontSize="small" /> },
    running: { label: "Running", color: "warning", icon: null },
  };
  const { label, color, icon } = config[status];
  return <Chip size="small" label={label} color={color} icon={icon ?? undefined} />;
}

interface StageCardProps {
  stage: PipelineStage;
  defaultExpanded?: boolean;
}

function StageCard({ stage, defaultExpanded = false }: StageCardProps) {
  const [open, setOpen] = useState(defaultExpanded || stage.status === "failed");

  return (
    <Paper
      variant="outlined"
      sx={{ mb: 1.5, overflow: "hidden", borderRadius: "8px" }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          px: 2,
          py: 1.25,
          gap: 1.5,
          cursor: "pointer",
          "&:hover": { bgcolor: "action.hover" },
        }}
        onClick={() => setOpen((v) => !v)}
      >
        <StatusBadge status={stage.status} />
        <Typography variant="body2" sx={{ fontWeight: 500, flex: 1 }}>
          {stage.name}
        </Typography>
        {stage.llmTelemetry?.estimatedCostGbp != null && (
          <Typography variant="caption" color="text.secondary">
            {`${(stage.llmTelemetry.estimatedCostGbp * 100).toFixed(3)}p`}
          </Typography>
        )}
        <IconButton
          size="small"
          sx={{ transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}
          aria-label={open ? "collapse" : "expand"}
        >
          <ExpandMoreIcon fontSize="small" />
        </IconButton>
      </Box>

      <Collapse in={open}>
        <Divider />
        <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 2 }}>
          {stage.description && (
            <Typography variant="caption" color="text.secondary">
              {stage.description}
            </Typography>
          )}

          {stage.error && (
            <Box sx={{ bgcolor: "error.50", borderRadius: 1, p: 1.5 }}>
              <Typography variant="caption" sx={{ color: "error.main", fontFamily: "monospace" }}>
                {stage.error}
              </Typography>
            </Box>
          )}

          {stage.input != null && (
            <StageSection label="Input" data={stage.input} />
          )}
          {stage.output != null && (
            <StageSection label="Output" data={stage.output} />
          )}

          {stage.llmTelemetry && (
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                LLM telemetry
              </Typography>
              <Box sx={{ mt: 0.5, display: "flex", gap: 2, flexWrap: "wrap" }}>
                {stage.llmTelemetry.model && (
                  <Typography variant="caption">{`Model: ${stage.llmTelemetry.model}`}</Typography>
                )}
                {stage.llmTelemetry.promptTokens != null && (
                  <Typography variant="caption">{`Prompt: ${stage.llmTelemetry.promptTokens} tok`}</Typography>
                )}
                {stage.llmTelemetry.completionTokens != null && (
                  <Typography variant="caption">{`Completion: ${stage.llmTelemetry.completionTokens} tok`}</Typography>
                )}
              </Box>
            </Box>
          )}
        </Box>
      </Collapse>
    </Paper>
  );
}

interface StageSectionProps {
  label: string;
  data: unknown;
}

function StageSection({ label, data }: StageSectionProps) {
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
        {label}
      </Typography>
      <Box
        component="pre"
        sx={{
          mt: 0.5,
          p: 1,
          bgcolor: "grey.50",
          borderRadius: 1,
          fontSize: "0.72rem",
          overflowX: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontFamily: "monospace",
          m: 0,
        }}
      >
        {text}
      </Box>
    </Box>
  );
}

export interface StageOutputViewerProps {
  stages: PipelineStage[];
  /** When true, all cards start expanded. */
  defaultExpanded?: boolean;
  /** Shown when stages is empty. */
  emptyMessage?: string;
}

export default function StageOutputViewer({
  stages,
  defaultExpanded = false,
  emptyMessage = "No pipeline stages to show.",
}: StageOutputViewerProps) {
  if (stages.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
        {emptyMessage}
      </Typography>
    );
  }

  return (
    <Box>
      {stages.map((stage, i) => (
        <StageCard key={`${stage.name}-${i}`} stage={stage} defaultExpanded={defaultExpanded} />
      ))}
    </Box>
  );
}
