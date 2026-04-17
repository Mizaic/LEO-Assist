"use client";

import Tooltip from "@mui/material/Tooltip";
import { Handle, Position, type HandleType } from "@xyflow/react";

export type PortDataType =
  | "string"
  | "string[]"
  | "object[]"
  | "boolean"
  | "object";

export const PORT_COLORS: Record<PortDataType, string> = {
  string: "#2196F3",
  "string[]": "#4CAF50",
  "object[]": "#FF9800",
  boolean: "#9C27B0",
  object: "#607D8B",
};

interface NodeHandleProps {
  /** React Flow handle id (port key). */
  id: string;
  /** target = input on left side; source = output on right side. */
  type: HandleType;
  /** Visible position on the node. */
  position?: Position;
  /** Optional fill colour; defaults to PORT_COLORS for the dataType, or a neutral grey. */
  color?: string;
  /** Optional dataType to look up a colour from PORT_COLORS. */
  dataType?: PortDataType;
  /** Vertical position when stacking multiple handles, e.g. "33%". */
  top?: string | number;
  /** Tooltip body shown on hover. Also used as aria-label fallback. */
  tooltip?: string;
  /** Explicit aria-label. Falls back to a sentence built from id+type. */
  ariaLabel?: string;
  /** Extra style merged onto the React Flow Handle. */
  style?: React.CSSProperties;
  /** Optional mouse-enter / leave for the parent to track hover. */
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

/**
 * NodeHandle - shared wrapper around React Flow's Handle that:
 *   - applies the canonical 12x12 white-bordered circle styling
 *   - wires a Tooltip for sighted users
 *   - exposes an aria-label so screen-reader users know the handle's role
 *
 * NodeHandle never overrides position / top / right / transform on the inner
 * Handle when those are required by React Flow for connection routing.
 */
export function NodeHandle({
  id,
  type,
  position,
  color,
  dataType,
  top,
  tooltip,
  ariaLabel,
  style,
  onMouseEnter,
  onMouseLeave,
}: NodeHandleProps) {
  const resolvedPosition =
    position ?? (type === "target" ? Position.Left : Position.Right);
  const resolvedColor =
    color ?? (dataType ? PORT_COLORS[dataType] : "#90A4AE");
  const direction = type === "target" ? "input" : "output";
  const resolvedAria =
    ariaLabel ?? `${direction} port ${id}${tooltip ? ` - ${tooltip}` : ""}`;
  const tooltipBody = tooltip ?? `${direction} port ${id}`;
  const placement = resolvedPosition === Position.Left ? "left" : "right";

  return (
    <Tooltip title={tooltipBody} placement={placement} arrow>
      <Handle
        id={id}
        type={type}
        position={resolvedPosition}
        aria-label={resolvedAria}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        style={{
          width: 12,
          height: 12,
          background: resolvedColor,
          border: "2px solid #fff",
          borderRadius: "50%",
          ...(top != null ? { top } : {}),
          ...style,
        }}
      />
    </Tooltip>
  );
}
