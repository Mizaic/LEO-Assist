/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { LabTraceEvent } from "../inspectorTypes";
import {
  plainEnglishPipelineMessage,
  summarizeStageErrors,
  summarizeStageMessages,
} from "../pipelineStageErrors";

interface Props {
  events: LabTraceEvent[];
  terminal?: boolean;
  runStatus?: string;
}

function emptyLogMessage(
  terminal: boolean | undefined,
  runStatus: string | undefined,
  filteredEmpty: boolean,
): string {
  if (filteredEmpty) return "No events match your filter.";
  if (terminal) {
    return `No live events captured for this ${runStatus || "completed"} run. Stage history is on the Data flow tab.`;
  }
  return "Waiting for pipeline events...";
}

function formatKeyList(keys: unknown): string | null {
  if (!Array.isArray(keys) || keys.length === 0) return null;
  return keys.map(String).join(", ");
}

function formatMetrics(metrics: unknown): string | null {
  if (!metrics || typeof metrics !== "object") return null;
  const entries = Object.entries(metrics as Record<string, unknown>).filter(
    ([, value]) => value != null && value !== "",
  );
  if (!entries.length) return null;
  return entries.map(([key, value]) => `${key}=${String(value)}`).join(" · ");
}

function formatErrors(errors: unknown): string | null {
  if (!Array.isArray(errors) || errors.length === 0) return null;
  return summarizeStageErrors(errors.map(String));
}

function formatEventError(payload: Record<string, unknown>): string | null {
  const summary =
    typeof payload.error === "string" && payload.error.trim()
      ? payload.error.trim()
      : "";
  if (summary) return plainEnglishPipelineMessage(summary);
  return formatErrors(payload.errors);
}

function formatEventWarning(payload: Record<string, unknown>): string | null {
  const summary =
    typeof payload.warning === "string" && payload.warning.trim()
      ? payload.warning.trim()
      : "";
  if (summary) return plainEnglishPipelineMessage(summary);
  if (!Array.isArray(payload.warnings) || payload.warnings.length === 0) {
    return null;
  }
  return summarizeStageMessages(payload.warnings.map(String));
}

export function RunInspectorLogTab({ events, terminal, runStatus }: Props) {
  const [filter, setFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return events;
    return events.filter(
      (ev) =>
        ev.type.toLowerCase().includes(q) ||
        JSON.stringify(ev.payload).toLowerCase().includes(q),
    );
  }, [events, filter]);

  return (
    <Stack
      spacing={1}
      data-testid="validation-lab-inspector-log"
      sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField
          size="small"
          placeholder="Filter events"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          fullWidth
        />
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
          }
          label="Auto-scroll"
        />
      </Stack>
      <Box
        sx={{
          flex: 1,
          minHeight: 300,
          fontFamily: "monospace",
          fontSize: 12,
          bgcolor: "grey.900",
          color: "grey.100",
          p: 1.5,
          borderRadius: 1,
          overflow: "auto",
        }}
        ref={(node: HTMLDivElement | null) => {
          if (autoScroll && node) node.scrollTop = node.scrollHeight;
        }}
      >
        {filtered.length === 0 ? (
          <Typography variant="caption" color="grey.400">
            {emptyLogMessage(terminal, runStatus, events.length > 0)}
          </Typography>
        ) : (
          filtered.map((ev) => {
            const payload = ev.payload;
            const inputKeys = formatKeyList(payload.input_keys);
            const outputKeys = formatKeyList(payload.output_keys);
            const metrics = formatMetrics(payload.metrics);
            const plainError = formatEventError(payload);
            const plainWarning = formatEventWarning(payload);
            const duration =
              typeof payload.duration_ms === "number"
                ? `${payload.duration_ms}ms`
                : null;

            return (
              <Box key={ev.id} sx={{ mb: 0.75 }}>
                <Typography component="span" sx={{ color: "#89b4fa" }}>
                  {ev.ts.slice(11, 23)}
                </Typography>{" "}
                <Typography component="span" sx={{ color: "#cba6f7" }}>
                  {ev.type}
                </Typography>{" "}
                <Typography component="span" sx={{ color: "#a6adc8" }}>
                  {String(payload.action_id || payload.step_id || "")}
                </Typography>
                {duration ? (
                  <Typography component="span" sx={{ color: "#6c7086", ml: 0.5 }}>
                    ({duration})
                  </Typography>
                ) : null}
                {inputKeys ? (
                  <Typography component="div" sx={{ color: "#94e2d5", fontSize: 11 }}>
                    in: {inputKeys}
                  </Typography>
                ) : null}
                {outputKeys ? (
                  <Typography component="div" sx={{ color: "#94e2d5", fontSize: 11 }}>
                    out: {outputKeys}
                  </Typography>
                ) : null}
                {metrics ? (
                  <Typography component="div" sx={{ color: "#f9e2af", fontSize: 11 }}>
                    metrics: {metrics}
                  </Typography>
                ) : null}
                {plainWarning ? (
                  <Typography component="div" sx={{ color: "#f9e2af", fontSize: 12, mt: 0.25 }}>
                    {plainWarning}
                  </Typography>
                ) : null}
                {plainError ? (
                  <Typography component="div" sx={{ color: "#f38ba8", fontSize: 12, mt: 0.25 }}>
                    {plainError}
                  </Typography>
                ) : null}
              </Box>
            );
          })
        )}
      </Box>
    </Stack>
  );
}
