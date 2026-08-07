/**
 * Zipkin-style pipeline trace waterfall for Validation Lab inspector.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { formatStageLabel, formatStageWorkerShort } from "../labRunFormat";
import { statusColor } from "../RunSheetTasks";
import type { LabTraceSpan } from "../inspectorTypes";
import {
  buildWaterfallBars,
  computeTraceBounds,
  formatAxisLabel,
  formatDurationLabel,
  statusBarColor,
} from "./traceWaterfallUtils";

interface Props {
  spans: LabTraceSpan[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
  compact?: boolean;
}

export function TraceWaterfallChart({
  spans,
  selectedStepId,
  onSelectStep,
  compact = false,
}: Props) {
  const bounds = computeTraceBounds(spans);
  if (!bounds || spans.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No timed spans yet. Stages appear here once they start.
      </Typography>
    );
  }

  const bars = buildWaterfallBars(spans, bounds);
  const axisMarks = [0, 0.5, 1].map((ratio) => ({
    ratio,
    label: formatAxisLabel(bounds.totalMs * ratio),
  }));

  return (
    <Stack spacing={0.75} data-testid="validation-lab-inspector-waterfall">
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: compact ? "120px 1fr 52px" : "160px 1fr 64px",
          gap: 1,
          alignItems: "center",
          px: 0.5,
        }}
      >
        <Typography variant="caption" color="text.secondary">
          Stage
        </Typography>
        <Box sx={{ position: "relative", height: 16 }}>
          {axisMarks.map((mark) => (
            <Typography
              key={mark.ratio}
              variant="caption"
              color="text.secondary"
              sx={{
                position: "absolute",
                left: `${mark.ratio * 100}%`,
                transform:
                  mark.ratio === 1
                    ? "translateX(-100%)"
                    : mark.ratio === 0.5
                      ? "translateX(-50%)"
                      : "none",
                fontSize: 10,
              }}
            >
              {mark.label}
            </Typography>
          ))}
        </Box>
        <Typography variant="caption" color="text.secondary" textAlign="right">
          Duration
        </Typography>
      </Box>

      {bars.map(({ span, leftPct, widthPct, durationMs }) => {
        const selected = selectedStepId === span.step_id;
        return (
          <Box
            key={span.step_id}
            onClick={() => onSelectStep(span.step_id)}
            sx={{
              display: "grid",
              gridTemplateColumns: compact ? "120px 1fr 52px" : "160px 1fr 64px",
              gap: 1,
              alignItems: "center",
              py: 0.5,
              px: 0.5,
              borderRadius: 1,
              cursor: "pointer",
              bgcolor: selected ? "action.selected" : "transparent",
              "&:hover": { bgcolor: selected ? "action.selected" : "action.hover" },
            }}
            data-testid={`validation-lab-inspector-span-${span.step_id}`}
          >
            <Box>
              <Typography variant="body2" fontWeight={600} noWrap>
                {formatStageLabel(span.step_id)}
              </Typography>
              {!compact && span.worker_id ? (
                <Typography variant="caption" color="text.secondary" noWrap>
                  {formatStageWorkerShort(span.worker_id)}
                </Typography>
              ) : null}
            </Box>
            <Box
              sx={{
                position: "relative",
                height: compact ? 18 : 28,
                bgcolor: "grey.100",
                borderRadius: 0.5,
                overflow: "hidden",
              }}
            >
              <Box
                sx={{
                  position: "absolute",
                  top: 2,
                  bottom: 2,
                  left: `${leftPct}%`,
                  width: `${widthPct}%`,
                  bgcolor: statusBarColor(span.status),
                  borderRadius: 0.5,
                  minWidth: 4,
                }}
              />
            </Box>
            <Stack alignItems="flex-end" spacing={0}>
              <Typography variant="caption" color={statusColor(span.status)}>
                {span.status}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {formatDurationLabel(durationMs)}
              </Typography>
            </Stack>
          </Box>
        );
      })}
    </Stack>
  );
}
