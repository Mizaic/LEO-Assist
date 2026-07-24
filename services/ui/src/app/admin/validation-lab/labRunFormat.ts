/**
 * Format helpers for Validation Lab run spend and stage labels.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-020F98AE, DI-12D40786, DI-2289D095, DI-43E908C6, DI-62175179, DI-9138BAC9, DI-A898556B, DI-FE423B8D
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */

import type { LabRunLlmUsage } from "./labApi";

export function formatUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "Cost n/a";
  if (n < 0.01) return `$${n.toFixed(5)}`;
  return `$${n.toFixed(4)}`;
}

export function formatTokens(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function usageFromRunOutputs(
  usage: LabRunLlmUsage | null | undefined,
): LabRunLlmUsage | null {
  if (!usage) return null;
  const cost = Number(usage.cost_usd || 0);
  const tokens = Number(usage.total_tokens || 0);
  const calls = Number(usage.llm_calls || 0);
  if (cost <= 0 && tokens <= 0 && calls <= 0) return null;
  return usage;
}

/** Sum known per-case costs for a batch run sheet (ignores missing telemetry). */
export function sumBatchCostUsd(
  items: ReadonlyArray<{ costUsd?: number | null }>,
): number | null {
  let total = 0;
  let seen = 0;
  for (const item of items) {
    const n = Number(item.costUsd);
    if (!Number.isFinite(n) || n <= 0) continue;
    total += n;
    seen += 1;
  }
  return seen > 0 ? total : null;
}

/** Human label for a durable step id (act-ref-extract -> extract). */
export function formatStageLabel(stepId: string): string {
  const trimmed = (stepId || "")
    .replace(/^act-ref-/, "")
    .replace(/^durable-ref-/, "")
    .replace(/-/g, " ")
    .trim();
  return trimmed || stepId || "stage";
}

/** Short host/replica prefix from lease_owner / completed_by. */
export function formatStageWorkerShort(workerId: string): string {
  const raw = (workerId || "").trim();
  if (!raw) return "";
  const host = raw.split(":")[0] || raw;
  return host.length > 28 ? `${host.slice(0, 26)}...` : host;
}
