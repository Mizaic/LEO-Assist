/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import type { ReactNode } from "react";
import { motion as fm } from "framer-motion";

import { useMotion } from "../motion";
import { springOrInstant, springs, tapScale } from "../motion/springs";
import { color } from "../tokens/color";
import { elevation, radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";

export type DeltaDirection = "up" | "down" | "flat";

export interface MetricDelta {
  value: string;
  direction: DeltaDirection;
  invert?: boolean;
}

export interface MetricTileProps {
  id: string;
  label: string;
  value: string | number;
  hint?: string;
  icon?: ReactNode;
  delta?: MetricDelta;
  tone?: "neutral" | "positive" | "warning" | "danger";
  onClick?: () => void;
}

function deltaColor(direction: DeltaDirection, invert: boolean): string {
  if (direction === "flat") return color.text.caption;
  const goodIsUp = !invert;
  const isGood =
    (direction === "up" && goodIsUp) || (direction === "down" && !goodIsUp);
  return isGood ? color.status.success : color.status.danger;
}

function deltaArrow(direction: DeltaDirection): string {
  if (direction === "up") return "\u2191";
  if (direction === "down") return "\u2193";
  return "\u2192";
}

function toneAccent(tone: MetricTileProps["tone"]): string | undefined {
  if (tone === "positive") return color.status.success;
  if (tone === "warning") return color.status.warning;
  if (tone === "danger") return color.status.danger;
  return undefined;
}

function tileStyle(interactive: boolean): React.CSSProperties {
  return {
    background: color.surface.raised,
    border: "1px solid " + color.surface.divider,
    boxShadow: elevation.card,
    borderRadius: radius.md,
    padding: "14px 16px",
    minHeight: 96,
    textAlign: "left",
    font: "inherit",
    fontFamily: typography.fontFamily.body,
    cursor: interactive ? "pointer" : "default",
    width: "100%",
    position: "relative",
  };
}

/**
 * MetricTile - single stat cell used by StatHero and standalone.
 * Press scale fires on pointer-down. Display figures use heading
 * tracking so large numbers sit tighter than body copy.
 */
export function MetricTile({
  id,
  label,
  value,
  hint,
  icon,
  delta,
  tone = "neutral",
  onClick,
}: MetricTileProps) {
  const { reducedMotion } = useMotion();
  const accent = toneAccent(tone);
  const interactive = typeof onClick === "function";
  const Tag = interactive ? fm.button : fm.div;

  return (
    <Tag
      data-testid={"metric-tile-" + id}
      onClick={onClick}
      type={interactive ? "button" : undefined}
      whileTap={interactive ? tapScale(reducedMotion) : undefined}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={tileStyle(interactive)}
    >
      {accent ? (
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            left: 0,
            top: 12,
            bottom: 12,
            width: 3,
            borderRadius: radius.sm,
            background: accent,
          }}
        />
      ) : null}

      <span
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          color: color.text.caption,
          fontSize: 12,
          fontWeight: 500,
          letterSpacing: typography.letterSpacing.caption,
          textTransform: "uppercase",
        }}
      >
        {icon ?? null}
        <span>{label}</span>
      </span>

      <span
        style={{
          display: "block",
          fontFamily: typography.fontFamily.heading,
          fontSize: 28,
          fontWeight: 600,
          lineHeight: 1.05,
          letterSpacing: typography.letterSpacing.display,
          fontVariantNumeric: "tabular-nums",
          marginTop: 6,
          color: color.text.primary,
        }}
      >
        {value}
      </span>

      <span
        style={{
          display: "flex",
          marginTop: 6,
          fontSize: 12,
          color: color.text.caption,
          gap: 6,
          alignItems: "baseline",
          flexWrap: "wrap",
        }}
      >
        {delta ? (
          <span style={{ color: deltaColor(delta.direction, delta.invert ?? false) }}>
            {deltaArrow(delta.direction)} {delta.value}
          </span>
        ) : null}
        {hint ? <span>{hint}</span> : null}
      </span>
    </Tag>
  );
}
