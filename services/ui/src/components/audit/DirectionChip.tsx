/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";

export type Direction = "better" | "worse" | "unchanged" | "unknown";

interface DirectionChipProps {
  direction: Direction;
  /** Optional short explanation shown in tooltip */
  reason?: string;
  size?: "small" | "medium";
}

const CONFIG: Record<Direction, { label: string; color: "success" | "error" | "default"; icon: string }> = {
  better:    { label: "Better",    color: "success", icon: "↑" },
  worse:     { label: "Worse",     color: "error",   icon: "↓" },
  unchanged: { label: "Unchanged", color: "default", icon: "→" },
  unknown:   { label: "—",         color: "default", icon: "—" },
};

export default function DirectionChip({ direction, reason, size = "small" }: DirectionChipProps) {
  const { label, color, icon } = CONFIG[direction];
  const chip = (
    <Chip
      label={`${icon} ${label}`}
      color={color}
      size={size}
      variant="outlined"
      aria-label={`Trend: ${label}${reason ? `. ${reason}` : ""}`}
      sx={{ fontWeight: 600, fontSize: "0.72rem" }}
    />
  );
  return reason ? <Tooltip title={reason}>{chip}</Tooltip> : chip;
}

/**
 * Compute the direction of travel for a metric.
 *
 * @param live        Current practice value (null if unavailable)
 * @param baseline    2018 benchmark value (null if unavailable)
 * @param higherIsBetter  true for metrics where a higher value is clinically better
 *                        (e.g. early stage %, fewer-than-3 %, TWW %)
 * @param threshold   Minimum absolute difference to count as "changed" (default 2pp)
 */
export function computeDirection(
  live: number | null | undefined,
  baseline: number | null | undefined,
  higherIsBetter: boolean,
  threshold = 2,
): Direction {
  if (live == null || baseline == null) return "unknown";
  const diff = live - baseline;
  if (Math.abs(diff) < threshold) return "unchanged";
  if (higherIsBetter) return diff > 0 ? "better" : "worse";
  return diff < 0 ? "better" : "worse";
}
