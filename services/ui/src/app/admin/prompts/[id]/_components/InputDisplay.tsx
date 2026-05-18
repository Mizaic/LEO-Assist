/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Renders a few-shot example input string with `[s0]` sentence chips.
 * Extracted from prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

export function InputDisplay({ text }: { text: string }) {
  if (!text.trim()) {
    return (
      <Typography variant="body2" color="text.disabled" fontStyle="italic">
        No input text yet
      </Typography>
    );
  }
  const segments = text.split(/(?=\[s\d+\])/g).filter(Boolean);
  return (
    <Stack spacing={0.5}>
      {segments.map((seg, i) => {
        const m = seg.match(/^\[s(\d+)\]\s*([\s\S]*)/);
        if (m) {
          return (
            <Stack
              key={i}
              direction="row"
              spacing={0.75}
              alignItems="flex-start"
            >
              <Chip
                size="small"
                label={`s${m[1]}`}
                variant="outlined"
                sx={{
                  height: 18,
                  fontSize: "0.62rem",
                  fontFamily: "monospace",
                  flexShrink: 0,
                  mt: "3px",
                }}
              />
              <Typography variant="body2">{m[2]}</Typography>
            </Stack>
          );
        }
        return (
          <Typography key={i} variant="body2">
            {seg}
          </Typography>
        );
      })}
    </Stack>
  );
}
