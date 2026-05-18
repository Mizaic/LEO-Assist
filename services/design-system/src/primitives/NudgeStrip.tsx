/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
"use client";

import type { CSSProperties, ReactNode } from "react";

import { color } from "../tokens/color";
import { radius, spacing } from "../tokens/spacing";
import { typography } from "../tokens/typography";

// Severity vocabulary mirrors the existing console nudge.severity values
// so the strip is a drop-in replacement for the legacy NudgeBanner.
// "danger" replaces the older "error" label to align with the rest of
// the design-system tone tokens.
export type NudgeSeverity = "info" | "warning" | "danger";

export interface NudgeStripProps {
  // Plain-language nudge message. Should follow the health-literacy
  // standards in copy/readability.ts -- short sentences, active voice.
  message: string;
  // Optional secondary CTA. When both label and handler are provided
  // the strip renders a button on the right.
  actionLabel?: string;
  onAction?: () => void;
  // Tone. Defaults to "info".
  severity?: NudgeSeverity;
  // Optional leading icon (e.g. lightbulb, warning triangle). Caller
  // owns sizing -- the strip provides flexShrink: 0 spacing only.
  icon?: ReactNode;
  // Optional aria-label for the action button when actionLabel is too
  // terse on its own (e.g. "View"). Defaults to actionLabel.
  actionAriaLabel?: string;
}

interface SeverityTone {
  bg: string;
  border: string;
  fg: string;
  accent: string;
}

const TONE: Record<NudgeSeverity, SeverityTone> = {
  info: {
    bg: "rgba(29, 78, 216, 0.06)",
    border: "rgba(29, 78, 216, 0.24)",
    fg: color.text.primary,
    accent: color.status.info,
  },
  warning: {
    bg: "rgba(180, 83, 9, 0.08)",
    border: "rgba(180, 83, 9, 0.32)",
    fg: color.text.primary,
    accent: color.status.warning,
  },
  danger: {
    bg: "rgba(185, 28, 28, 0.08)",
    border: "rgba(185, 28, 28, 0.32)",
    fg: color.text.primary,
    accent: color.status.danger,
  },
};

function stripStyle(tone: SeverityTone): CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    gap: spacing.sm,
    padding: "10px 14px",
    background: tone.bg,
    border: "1px solid " + tone.border,
    borderLeft: "3px solid " + tone.accent,
    borderRadius: radius.md,
    fontFamily: typography.fontFamily.body,
    color: tone.fg,
    marginBottom: spacing.md,
  };
}

function actionStyle(tone: SeverityTone): CSSProperties {
  return {
    appearance: "none",
    background: "transparent",
    border: "1px solid " + tone.border,
    color: tone.accent,
    padding: "4px 12px",
    borderRadius: radius.pill,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 700,
    fontFamily: typography.fontFamily.body,
    whiteSpace: "nowrap",
    flexShrink: 0,
    transition: "background 150ms ease",
  };
}

/**
 * NudgeStrip -- semantic, accessible nudge banner.
 *
 * Replaces the bespoke NudgeBanner in the Intelligence Console. Sets
 * role="status" with aria-live="polite" so the message is announced to
 * assistive tech without interrupting the user. Severity tones are
 * drawn from color.status.* tokens so the strip looks consistent with
 * other surfaces (PipelineRail, StatHero, MetricTile).
 *
 * Design Controls: DI-LEO-AI-164, DO-LEO-AI-163, R-LEO-AI-165, VT-LEO-AI-162.
 */
export function NudgeStrip({
  message,
  actionLabel,
  onAction,
  severity = "info",
  icon,
  actionAriaLabel,
}: NudgeStripProps) {
  const tone = TONE[severity];
  const showAction = actionLabel != null && onAction != null;

  return (
    <section
      role="status"
      aria-live="polite"
      data-testid="nudge-strip"
      data-severity={severity}
      style={stripStyle(tone)}
    >
      {icon ? (
        <span
          aria-hidden="true"
          style={{ color: tone.accent, display: "inline-flex", flexShrink: 0 }}
        >
          {icon}
        </span>
      ) : null}
      <p
        style={{
          margin: 0,
          flex: 1,
          fontSize: 14,
          lineHeight: 1.5,
        }}
      >
        {message}
      </p>
      {showAction ? (
        <button
          type="button"
          onClick={onAction}
          aria-label={actionAriaLabel ?? actionLabel}
          style={actionStyle(tone)}
        >
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}
