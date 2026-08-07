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

interface Props {
  events: LabTraceEvent[];
}

export function RunInspectorLogTab({ events }: Props) {
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
    <Stack spacing={1} data-testid="validation-lab-inspector-log">
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
          fontFamily: "monospace",
          fontSize: 12,
          bgcolor: "grey.900",
          color: "grey.100",
          p: 1.5,
          borderRadius: 1,
          maxHeight: 420,
          overflow: "auto",
        }}
        ref={(node) => {
          if (autoScroll && node) node.scrollTop = node.scrollHeight;
        }}
      >
        {filtered.length === 0 ? (
          <Typography variant="caption" color="grey.400">
            Waiting for pipeline events...
          </Typography>
        ) : (
          filtered.map((ev) => (
            <Box key={ev.id} sx={{ mb: 0.75 }}>
              <Typography component="span" sx={{ color: "#89b4fa" }}>
                {ev.ts.slice(11, 23)}
              </Typography>{" "}
              <Typography component="span" sx={{ color: "#cba6f7" }}>
                {ev.type}
              </Typography>{" "}
              <Typography component="span" sx={{ color: "#a6adc8" }}>
                {String(ev.payload.action_id || ev.payload.step_id || "")}
              </Typography>
              {ev.payload.error ? (
                <Typography component="div" sx={{ color: "#f38ba8" }}>
                  {String(ev.payload.error)}
                </Typography>
              ) : null}
            </Box>
          ))
        )}
      </Box>
    </Stack>
  );
}
