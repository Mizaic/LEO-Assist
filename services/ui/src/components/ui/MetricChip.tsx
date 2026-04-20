/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-0998FAF5
 *   Also implements: DO-E32DAC8D
 *   DI: DI-BE09736F
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { FONT_SIZES } from "@/theme/tokens";

interface MetricChipProps {
  value: string | number;
  label?: string;
  color?: string;
}

export function MetricChip({ value, label, color = "#1565c0" }: MetricChipProps) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "baseline",
        gap: 0.5,
        bgcolor: `${color}12`,
        border: `1px solid ${color}30`,
        borderRadius: 1.5,
        px: 1,
        py: 0.25,
      }}
    >
      <Typography
        component="span"
        sx={{ fontWeight: 700, fontSize: FONT_SIZES.title, color, lineHeight: 1.2 }}
      >
        {value}
      </Typography>
      {label && (
        <Typography
          component="span"
          sx={{ fontSize: FONT_SIZES.label, color: "text.secondary", lineHeight: 1.2 }}
        >
          {label}
        </Typography>
      )}
    </Box>
  );
}
