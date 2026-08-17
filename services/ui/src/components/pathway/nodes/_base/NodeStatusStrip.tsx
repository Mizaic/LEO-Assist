/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { color } from "@leo/design-system/tokens";

export type NodeRunStatus =
  | "idle"
  | "queued"
  | "running"
  | "completed"
  | "halted"
  | "error"
  | "skipped";

interface NodeStatusStripProps {
  status: NodeRunStatus;
  /** Last duration in milliseconds; only shown for completed status. */
  durationMs?: number;
  /** Human-readable detail surfaced in the tooltip. */
  detail?: string;
}

function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

const STATUS_LABELS: Record<NodeRunStatus, string> = {
  idle: "",
  queued: "queued",
  running: "running",
  completed: "passed",
  halted: "halted",
  error: "errored",
  skipped: "skipped",
};

/**
 * NodeStatusStrip - the small status pip + label that sits on the right of
 * every pathway node header. Replaces the bespoke spinner/dot/dot-with-label
 * blocks that each node used to roll its own.
 */
export function NodeStatusStrip({
  status,
  durationMs,
  detail,
}: NodeStatusStripProps) {
  if (status === "idle") return null;

  if (status === "running") {
    return (
      <Tooltip title={detail ?? "Running..."}>
        <Box
          aria-label="running"
          role="status"
          sx={{ display: "flex", alignItems: "center" }}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            style={{ animation: "spin 1s linear infinite" }}
            aria-hidden="true"
          >
            <style>{"@keyframes spin { to { transform: rotate(360deg); } }"}</style>
            <circle
              cx="12"
              cy="12"
              r="9"
              fill="none"
              stroke={color.brand.primary}
              strokeWidth="3"
              strokeDasharray="28 56"
              strokeLinecap="round"
            />
          </svg>
        </Box>
      </Tooltip>
    );
  }

  if (status === "queued") {
    return (
      <Tooltip title={detail ?? "Queued for this run"}>
        <Box
          aria-label="queued"
          sx={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            bgcolor: "grey.300",
            flexShrink: 0,
          }}
        />
      </Tooltip>
    );
  }

  if (status === "skipped") {
    return (
      <Tooltip title={detail ?? "Pipeline stopped before reaching this step"}>
        <Typography
          aria-label="skipped"
          variant="caption"
          sx={{ fontSize: "0.6rem", color: "text.disabled" }}
        >
          {STATUS_LABELS.skipped}
        </Typography>
      </Tooltip>
    );
  }

  if (status === "completed") {
    const durationLabel =
      typeof durationMs === "number" ? formatDuration(durationMs) : "";
    return (
      <Tooltip title={detail ?? `Passed${durationLabel ? ` - ${durationLabel}` : ""}`}>
        <Box
          aria-label="passed"
          sx={{ display: "flex", alignItems: "center", gap: 0.4 }}
        >
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              bgcolor: "success.main",
              flexShrink: 0,
            }}
          />
          {durationLabel ? (
            <Typography
              variant="caption"
              sx={{
                fontSize: "0.6rem",
                color: "success.dark",
                fontWeight: 700,
              }}
            >
              {durationLabel}
            </Typography>
          ) : null}
        </Box>
      </Tooltip>
    );
  }

  if (status === "halted") {
    return (
      <Tooltip title={detail ?? "Pipeline stopped here - check the probe for details"}>
        <Box
          aria-label="halted"
          sx={{ display: "flex", alignItems: "center", gap: 0.4 }}
        >
          <Box component="span" aria-hidden="true" sx={{ fontSize: "0.75rem", lineHeight: 1 }}>
            !
          </Box>
          <Typography
            variant="caption"
            sx={{
              fontSize: "0.6rem",
              color: "error.dark",
              fontWeight: 700,
            }}
          >
            {STATUS_LABELS.halted}
          </Typography>
        </Box>
      </Tooltip>
    );
  }

  return (
    <Tooltip title={detail ?? "Step failed"}>
      <Box
        aria-label="errored"
        sx={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          bgcolor: "error.main",
          flexShrink: 0,
        }}
      />
    </Tooltip>
  );
}
