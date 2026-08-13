/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BCA9B190
 *   DI: DI-C5A523A7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BCA9B190")
 */
"use client";

import { color } from "../tokens/color";
import { radius } from "../tokens/spacing";
import { typography } from "../tokens/typography";
import { useMotion } from "../motion";
import { ProgressStripScanner } from "./ProgressStripScanner";

export interface ProgressStripProps {
  label: string;
  /** Ignored when indeterminate is true. */
  value?: number;
  /** Ignored when indeterminate is true. */
  total?: number;
  // Optional right-hand side subtitle (e.g. "55% complete").
  subtitle?: string;
  tone?: "neutral" | "positive" | "warning" | "danger";
  /**
   * When true, shows a slow mindfulness pulse instead of a percent fill.
   * Use for long jobs with no server-side percent.
   */
  indeterminate?: boolean;
}

/**
 * ProgressStrip -- labelled horizontal progress bar. Animates the fill
 * on mount and on value change; collapses to an instant transition when
 * reduced-motion is set.
 *
 * Design Controls: DI-LEO-AI-142, DO-LEO-AI-139, VT-LEO-AI-141.
 */

function toneFill(tone: ProgressStripProps["tone"]): string {
  if (tone === "positive") return color.status.success;
  if (tone === "warning") return color.status.warning;
  if (tone === "danger") return color.status.danger;
  return color.brand.primary;
}

function clampPct(value: number, total: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
}

export function ProgressStrip({
  label,
  value = 0,
  total = 0,
  subtitle,
  tone = "neutral",
  indeterminate = false,
}: ProgressStripProps) {
  const { reducedMotion } = useMotion();
  const pct = indeterminate ? 0 : clampPct(value, total);
  const fill = toneFill(tone);
  const transitionMs = reducedMotion ? 0 : 360;
  const rightLabel =
    subtitle ?? (indeterminate ? "In progress" : pct + "% complete");
  const trackHeight = 8;

  return (
    <section
      aria-label={label}
      aria-busy={indeterminate || undefined}
      data-testid="progress-strip"
      data-indeterminate={indeterminate ? "true" : "false"}
      style={{
        background: color.surface.raised,
        border: "1px solid " + color.surface.divider,
        borderRadius: radius.md,
        padding: "14px 16px",
        fontFamily: typography.fontFamily.body,
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: 12,
          marginBottom: 10,
        }}
      >
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: color.text.primary,
          }}
        >
          {label}
        </span>
        <span
          style={{
            fontSize: 12,
            color: color.text.caption,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {rightLabel}
        </span>
      </header>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={indeterminate ? undefined : pct}
        aria-valuemin={0}
        aria-valuemax={100}
        data-testid="progress-strip-track"
        style={{
          position: "relative",
          height: trackHeight,
          borderRadius: radius.pill,
          background: color.surface.alt,
          overflow: "hidden",
        }}
      >
        {indeterminate ? (
          <ProgressStripScanner reducedMotion={reducedMotion} />
        ) : (
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              inset: 0,
              width: pct + "%",
              background: fill,
              borderRadius: radius.pill,
              transition:
                "width " +
                transitionMs +
                "ms ease-out, background 180ms ease-out",
            }}
          />
        )}
      </div>
    </section>
  );
}
