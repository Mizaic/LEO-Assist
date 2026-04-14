"use client";

import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import { HEALTH_COLORS, HealthStatus } from "@/theme/tokens";

interface StatusDotProps {
  status: HealthStatus;
  reason?: string;
  size?: number;
}

export function StatusDot({ status, reason, size = 10 }: StatusDotProps) {
  const color = HEALTH_COLORS[status] ?? HEALTH_COLORS.neutral;
  const dot = (
    <Box
      aria-label={reason ? `Status: ${status} - ${reason}` : `Status: ${status}`}
      sx={{
        width: size,
        height: size,
        borderRadius: "50%",
        bgcolor: color,
        display: "inline-block",
        flexShrink: 0,
        boxShadow: status !== "neutral" ? `0 0 0 2px ${color}33` : "none",
      }}
    />
  );
  if (!reason) return dot;
  return (
    <Tooltip title={reason} arrow placement="top">
      {dot}
    </Tooltip>
  );
}
