/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";

export type BaseNodeTone =
  | "neutral"
  | "running"
  | "selected"
  | "halted";

interface BaseNodeProps {
  /** Node accent colour applied to the border when not selected/halted/running. */
  accentColor: string;
  /** Whether React Flow has selected this node (overrides accentColor border). */
  selected?: boolean;
  /** Active status during a test run. Drives border glow + background tint. */
  runStatus?: BaseNodeTone;
  /**
   * Whether the node fades out because the pipeline halted upstream and never
   * reached it. Applied as opacity 0.45.
   */
  notReached?: boolean;
  /** Stylistic variant: solid border (default) or dashed (sources/connectors). */
  borderStyle?: "solid" | "dashed";
  /** Width floor; React Flow widths are content-driven so we only set min. */
  minWidth?: number;
  /** Optional max width cap. */
  maxWidth?: number;
  /** Optional aria-label for the whole node. Used by screen readers. */
  ariaLabel?: string;
  /** Single-click handler. Standardised configure interaction. */
  onActivate?: () => void;
  /** Children render the node body (handles + header + chips + extras). */
  children: ReactNode;
  /** Extra sx escape hatch for nodes that need bespoke padding etc. */
  sx?: SxProps<Theme>;
}

const PULSE_KEYFRAMES = {
  "0%": { boxShadow: "0 0 0 0 rgba(25,118,210,0.4)" },
  "70%": { boxShadow: "0 0 0 8px rgba(25,118,210,0)" },
  "100%": { boxShadow: "0 0 0 0 rgba(25,118,210,0)" },
};

const HALT_KEYFRAMES = {
  "0%": { boxShadow: "0 0 0 0 rgba(211,47,47,0.55)" },
  "60%": { boxShadow: "0 0 0 10px rgba(211,47,47,0)" },
  "100%": { boxShadow: "0 0 0 0 rgba(211,47,47,0)" },
};

function resolveBorderColor(
  tone: BaseNodeTone,
  selected: boolean,
  accent: string,
): string {
  if (tone === "halted") return "#D32F2F";
  if (tone === "running" || selected) return "#1976D2";
  return accent;
}

function resolveBackground(tone: BaseNodeTone): string {
  if (tone === "halted") return "#FFEBEE";
  if (tone === "running") return "#E3F2FD";
  return "#FFFFFF";
}

/**
 * BaseNode - canonical shell every pathway node renders inside.
 *
 * Contract:
 *   - Always single-click to activate (configure). Double-click is reserved
 *     for React Flow's own zoom-to-node behaviour.
 *   - 12px border radius, 2px solid border, white background by default.
 *   - Standard 12px horizontal / 16px vertical padding.
 *   - Selected / running / halted states are managed centrally so every node
 *     looks and behaves the same.
 */
export function BaseNode({
  accentColor,
  selected = false,
  runStatus = "neutral",
  notReached = false,
  borderStyle = "solid",
  minWidth = 200,
  maxWidth,
  ariaLabel,
  onActivate,
  children,
  sx,
}: BaseNodeProps) {
  const borderColor = resolveBorderColor(runStatus, selected, accentColor);
  const bgcolor = resolveBackground(runStatus);
  const isInteractive = typeof onActivate === "function";

  return (
    <Box
      role={isInteractive ? "button" : undefined}
      tabIndex={isInteractive ? 0 : undefined}
      aria-label={ariaLabel}
      onClick={onActivate}
      onKeyDown={
        isInteractive
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onActivate?.();
              }
            }
          : undefined
      }
      sx={{
        position: "relative",
        px: 1.5,
        py: 1.25,
        minWidth,
        maxWidth,
        borderRadius: "12px",
        border: `2px ${borderStyle}`,
        borderColor,
        bgcolor: notReached ? "#F5F5F5" : bgcolor,
        opacity: notReached ? 0.45 : 1,
        cursor: isInteractive ? "pointer" : "default",
        transition: "border-color 120ms ease-out, box-shadow 120ms ease-out",
        ...(runStatus === "running" && {
          animation: "nodePulse 1s ease-in-out infinite",
          "@keyframes nodePulse": PULSE_KEYFRAMES,
        }),
        ...(runStatus === "halted" && {
          animation: "nodeHalt 1.4s ease-in-out infinite",
          "@keyframes nodeHalt": HALT_KEYFRAMES,
        }),
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}
