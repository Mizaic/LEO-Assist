"use client";

import {
  useCallback,
  useMemo,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { motion as fm } from "framer-motion";

import { color } from "../tokens/color";
import { radius, spacing } from "../tokens/spacing";
import { typography } from "../tokens/typography";
import { useMotion } from "../motion";

// Status semantics mirror the existing console HealthStatus vocabulary so
// the PipelineRail is a drop-in replacement for the legacy HealthBar
// without forcing every caller to remap their tone enum. See
// DI-LEO-AI-164 acceptance criteria.
export type PipelineStageStatus =
  | "healthy"
  | "warning"
  | "error"
  | "info"
  | "neutral";

export interface PipelineStage {
  // Stable identifier used for activation, aria-controls and key-based
  // navigation. Should match the consumer's filter / route value.
  id: string;
  // Short label shown in the pill (typically uppercase like DISCOVER /
  // CURATE). Long labels are not truncated; the rail wraps if needed.
  label: string;
  // Status drives the colour of the dot. Defaults to "neutral".
  status?: PipelineStageStatus;
  // Optional plain-language reason shown via the title attribute and
  // appended to the aria-label so assistive tech announces context.
  reason?: string;
  // Optional accent tint for the active pill border + background. If
  // omitted, color.brand.primary is used.
  accentColor?: string;
}

export interface PipelineRailProps {
  // Ordered list of stages rendered left-to-right. The arrow separator
  // is drawn between adjacent items.
  stages: PipelineStage[];
  // Currently activated stage id. May be null/undefined when no stage
  // is selected.
  activeStageId?: string | null;
  // Called when a stage pill is activated via click, Enter or Space.
  // The activeStageId is NOT updated automatically -- the parent owns
  // the state, mirroring the HealthBar contract this primitive
  // replaces.
  onStageSelect?: (id: string) => void;
  // Stagger between pills on mount, in ms. Defaults to 50 ms.
  staggerMs?: number;
  // Optional aria-label override for the rail wrapper. Defaults to
  // "Pipeline stages".
  ariaLabel?: string;
}

// Map status -> dot colour. Mirrors the legacy HEALTH_COLORS table and
// uses semantic tokens so the rail looks consistent with NudgeStrip and
// other surfaces.
const STATUS_DOT: Record<PipelineStageStatus, string> = {
  healthy: color.status.success,
  warning: color.status.warning,
  error: color.status.danger,
  info: color.status.info,
  neutral: color.status.neutral,
};

function dotStyle(status: PipelineStageStatus): CSSProperties {
  return {
    width: 8,
    height: 8,
    borderRadius: radius.pill,
    background: STATUS_DOT[status],
    flexShrink: 0,
  };
}

function pillStyle(active: boolean, accent: string): CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 10px",
    borderRadius: radius.sm,
    cursor: "pointer",
    background: active ? accent + "14" : "transparent",
    border: "1px solid " + (active ? accent : "transparent"),
    transition: "background 150ms ease, border-color 150ms ease",
    fontFamily: typography.fontFamily.body,
    color: active ? accent : color.text.primary,
    fontSize: 12,
    fontWeight: active ? 700 : 500,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  };
}

function StageSeparator({ first }: { first: boolean }): ReactNode | null {
  if (first) return null;
  return (
    <span
      aria-hidden="true"
      style={{
        color: color.text.disabled,
        fontSize: 12,
        margin: "0 " + spacing.xxs + "px",
      }}
    >
      -&gt;
    </span>
  );
}

interface StagePillProps {
  stage: PipelineStage;
  active: boolean;
  index: number;
  reducedMotion: boolean;
  staggerMs: number;
  onSelect: (id: string) => void;
}

function StagePill({
  stage,
  active,
  index,
  reducedMotion,
  staggerMs,
  onSelect,
}: StagePillProps) {
  const status: PipelineStageStatus = stage.status ?? "neutral";
  const accent = stage.accentColor ?? color.brand.primary;
  const reason = stage.reason ? " - " + stage.reason : "";

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect(stage.id);
      }
    },
    [onSelect, stage.id],
  );

  const delay = reducedMotion ? 0 : (index * staggerMs) / 1000;

  return (
    <fm.div
      initial={reducedMotion ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reducedMotion ? 0 : 0.18, delay, ease: "easeOut" }}
      style={{ display: "inline-flex", alignItems: "center" }}
      data-testid={"pipeline-stage-" + stage.id}
    >
      <div
        role="tab"
        aria-selected={active}
        aria-controls={"pipeline-panel-" + stage.id}
        tabIndex={0}
        title={stage.reason ?? stage.label}
        aria-label={stage.label + ": " + status + reason}
        onClick={() => onSelect(stage.id)}
        onKeyDown={handleKeyDown}
        style={pillStyle(active, accent)}
      >
        <span aria-hidden="true" style={dotStyle(status)} />
        <span>{stage.label}</span>
      </div>
    </fm.div>
  );
}

/**
 * PipelineRail -- ordered, accessible row of pipeline stage pills.
 *
 * Replaces the bespoke HealthBar in the Intelligence Console. Exposes
 * role="tablist" semantics (each pill is a tab), supports keyboard
 * activation via Enter / Space, and animates entry with framer-motion.
 * Honours prefers-reduced-motion by collapsing all delays to zero.
 *
 * Design Controls: DI-LEO-AI-164, DO-LEO-AI-163, R-LEO-AI-165, VT-LEO-AI-162.
 */
export function PipelineRail({
  stages,
  activeStageId,
  onStageSelect,
  staggerMs = 50,
  ariaLabel = "Pipeline stages",
}: PipelineRailProps) {
  const { reducedMotion } = useMotion();
  const handleSelect = useCallback(
    (id: string) => {
      if (onStageSelect) onStageSelect(id);
    },
    [onStageSelect],
  );

  // Pre-compute an active set for quick lookup; supports the case where
  // activeStageId is undefined (no selection) without per-render cost.
  const activeId = useMemo(() => activeStageId ?? null, [activeStageId]);

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      data-testid="pipeline-rail"
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: spacing.xxs,
        padding: spacing.xs,
        background: color.surface.raised,
        border: "1px solid " + color.surface.divider,
        borderRadius: radius.md,
      }}
    >
      {stages.map((stage, index) => (
        <span
          key={stage.id}
          style={{ display: "inline-flex", alignItems: "center" }}
        >
          <StageSeparator first={index === 0} />
          <StagePill
            stage={stage}
            active={activeId === stage.id}
            index={index}
            reducedMotion={reducedMotion}
            staggerMs={staggerMs}
            onSelect={handleSelect}
          />
        </span>
      ))}
    </div>
  );
}
