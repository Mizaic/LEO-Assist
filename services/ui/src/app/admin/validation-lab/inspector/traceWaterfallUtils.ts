/**
 * Zipkin-style trace waterfall helpers for Validation Lab inspector.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */

import type { LabTraceSpan } from "../inspectorTypes";

export interface TraceBounds {
  startMs: number;
  endMs: number;
  totalMs: number;
}

export interface WaterfallBar {
  span: LabTraceSpan;
  leftPct: number;
  widthPct: number;
  durationMs: number | null;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "#10b981",
  failed: "#ef4444",
  poisoned: "#ef4444",
  running: "#3b82f6",
  pending: "#94a3b8",
  skipped_persist: "#f59e0b",
};

export function spanDurationMs(span: LabTraceSpan): number | null {
  if (span.duration_ms != null) return span.duration_ms;
  if (!span.started_at || !span.completed_at) return null;
  const start = Date.parse(span.started_at);
  const end = Date.parse(span.completed_at);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return Math.max(0, end - start);
}

export function statusBarColor(status: string): string {
  return STATUS_COLORS[status] || "#64748b";
}

export function computeTraceBounds(spans: LabTraceSpan[]): TraceBounds | null {
  let startMs = Infinity;
  let endMs = 0;
  for (const span of spans) {
    if (span.started_at) {
      const start = Date.parse(span.started_at);
      if (Number.isFinite(start)) startMs = Math.min(startMs, start);
    }
    const endRaw = span.completed_at || span.started_at;
    if (endRaw) {
      const end = Date.parse(endRaw);
      if (Number.isFinite(end)) endMs = Math.max(endMs, end);
    }
    const dur = spanDurationMs(span);
    if (dur != null && span.started_at) {
      const start = Date.parse(span.started_at);
      if (Number.isFinite(start)) endMs = Math.max(endMs, start + dur);
    }
  }
  if (!Number.isFinite(startMs)) return null;
  if (endMs <= startMs) endMs = startMs + 1;
  return { startMs, endMs, totalMs: endMs - startMs };
}

export function buildWaterfallBars(
  spans: LabTraceSpan[],
  bounds: TraceBounds,
): WaterfallBar[] {
  return spans.map((span) => {
    const durationMs = spanDurationMs(span);
    const startRaw = span.started_at
      ? Date.parse(span.started_at)
      : bounds.startMs;
    const startMs = Number.isFinite(startRaw) ? startRaw : bounds.startMs;
    const endMs =
      durationMs != null ? startMs + durationMs : startMs + bounds.totalMs * 0.04;
    const leftPct = ((startMs - bounds.startMs) / bounds.totalMs) * 100;
    const widthPct = Math.max(
      0.8,
      ((endMs - startMs) / bounds.totalMs) * 100,
    );
    return { span, leftPct, widthPct, durationMs };
  });
}

export function formatDurationLabel(ms: number | null): string {
  if (ms == null) return "--";
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

export function formatAxisLabel(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}
