/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-65E7BCF8
 *   Also implements: DO-C4EC82F9
 *   DI: DI-B0832A64, DI-B95A73E9, DI-BE09736F
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-65E7BCF8")
 */
"use client";

import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import { HEALTH_COLORS, HealthStatus } from "@/theme/tokens";

interface StatusDotProps {
  status: HealthStatus;
  reason?: string;
  size?: number;
}

type Shape = "circle" | "triangle" | "square" | "diamond" | "pill";

const STATUS_SHAPE: Record<HealthStatus, Shape> = {
  healthy: "circle",
  warning: "triangle",
  error: "square",
  info: "pill",
  neutral: "diamond",
};

const STATUS_LABEL: Record<HealthStatus, string> = {
  healthy: "Healthy",
  warning: "Warning",
  error: "Error",
  info: "Information",
  neutral: "Not applicable",
};

/**
 * StatusDot communicates status through THREE channels so no single
 * perception (colour, shape, text) is load-bearing:
 * - colour (HEALTH_COLORS token)
 * - shape (STATUS_SHAPE; exposed as data-shape for testability)
 * - accessible label (STATUS_LABEL + optional reason, aria-label)
 *
 * See DI-LEO-AI-120 and VT-LEO-AI-115.
 */
export function StatusDot({ status, reason, size = 12 }: StatusDotProps) {
  const color = HEALTH_COLORS[status] ?? HEALTH_COLORS.neutral;
  const shape = STATUS_SHAPE[status] ?? "circle";
  const statusLabel = STATUS_LABEL[status] ?? "Unknown";
  const ariaLabel = reason
    ? `${statusLabel}: ${reason}`
    : `Status: ${statusLabel}`;

  const shapeSx = shapeStyle(shape, color, size);

  const dot = (
    <Box
      role="img"
      data-shape={shape}
      data-status={status}
      aria-label={ariaLabel}
      sx={{
        width: size,
        height: size,
        display: "inline-block",
        flexShrink: 0,
        boxShadow: status !== "neutral" ? `0 0 0 2px ${color}33` : "none",
        ...shapeSx,
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

function shapeStyle(
  shape: Shape,
  color: string,
  size: number,
): Record<string, string | number> {
  if (shape === "circle") {
    return { bgcolor: color, borderRadius: "50%" };
  }
  if (shape === "square") {
    return { bgcolor: color, borderRadius: 2 };
  }
  if (shape === "pill") {
    return { bgcolor: color, borderRadius: size };
  }
  if (shape === "diamond") {
    return { bgcolor: color, borderRadius: 2, transform: "rotate(45deg)" };
  }
  return {
    width: 0,
    height: 0,
    bgcolor: "transparent",
    borderLeft: `${size / 2}px solid transparent`,
    borderRight: `${size / 2}px solid transparent`,
    borderBottom: `${size}px solid ${color}`,
  };
}
