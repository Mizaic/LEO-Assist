/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-146D93D0
 *   Also implements: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-146D93D0")
 */
"use client";

import Tooltip from "@mui/material/Tooltip";
import Box from "@mui/material/Box";
import { getStatusLabel, getStatusColour } from "@/lib/pathwayLabels";

interface Props {
  status: string;
}

const COLOUR_MAP = {
  success: "#4caf50",
  warning: "#ff9800",
  error: "#f44336",
  default: "#9e9e9e",
};

export default function StatusBadge({ status }: Props) {
  const colour = getStatusColour(status);
  const label = getStatusLabel(status);
  return (
    <Tooltip title={label} arrow>
      <Box
        aria-label={label}
        sx={{
          width: 12,
          height: 12,
          borderRadius: "50%",
          backgroundColor: COLOUR_MAP[colour],
          display: "inline-block",
          flexShrink: 0,
        }}
      />
    </Tooltip>
  );
}
