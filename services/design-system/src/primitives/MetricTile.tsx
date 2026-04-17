"use client";

import type { ReactNode } from "react";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";

export type DeltaDirection = "up" | "down" | "flat";

export interface MetricDelta {
  value: string;
  direction: DeltaDirection;
  // When true, "up" is rendered in red and "down" in green. Use this
  // for metrics where a lower value is better (wait times, failures).
  invert?: boolean;
}

export interface MetricTileProps {
  id: string;
  label: string;
  value: string | number;
  hint?: string;
  icon?: ReactNode;
  delta?: MetricDelta;
  // Optional tone to lift the tile for attention without changing its
  // meaning (positive | warning | danger). Falls back to neutral.
  tone?: "neutral" | "positive" | "warning" | "danger";
  onClick?: () => void;
}

/**
 * MetricTile - single stat cell used by StatHero and standalone. No
 * @mui imports; all visuals come from the design-system tokens.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

function deltaColor(direction: DeltaDirection, invert: boolean): string {
  if (direction === "flat") return color.text.caption;
  const goodIsUp = !invert;
  const isGood =
    (direction === "up" && goodIsUp) ||
    (direction === "down" && !goodIsUp);
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
  const accent = toneAccent(tone);
  const interactive = typeof onClick === "function";
  const Tag = interactive ? "button" : "div";

  const style: React.CSSProperties = {
    background: color.surface.raised,
    border: "1px solid " + color.surface.divider,
    borderRadius: radius.md,
    padding: "14px 16px",
    minHeight: 96,
    textAlign: "left",
    font: "inherit",
    fontFamily: typography.fontFamily.body,
    cursor: interactive ? "pointer" : "default",
    width: "100%",
    transition: "box-shadow 160ms ease-out, transform 160ms ease-out",
    position: "relative",
  };

  return (
    <Tag
      data-testid={"metric-tile-" + id}
      onClick={onClick}
      type={interactive ? "button" : undefined}
      style={style}
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
          letterSpacing: 0.2,
          textTransform: "uppercase",
        }}
      >
        {icon ?? null}
        <span>{label}</span>
      </span>

      <span
        style={{
          display: "block",
          fontSize: 28,
          fontWeight: 600,
          lineHeight: 1.1,
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
          <span
            style={{ color: deltaColor(delta.direction, delta.invert ?? false) }}
          >
            {deltaArrow(delta.direction)} {delta.value}
          </span>
        ) : null}
        {hint ? <span>{hint}</span> : null}
      </span>
    </Tag>
  );
}
