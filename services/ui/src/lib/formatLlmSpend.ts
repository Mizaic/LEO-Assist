/**
 * Format LLM spend for admin surfaces (Care document runs, dashboards).
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
export interface LlmUsageSummary {
  cost_usd?: number;
  total_tokens?: number;
  llm_calls?: number;
}

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

export function hasLlmUsage(usage: LlmUsageSummary | null | undefined): boolean {
  if (!usage) return false;
  const cost = Number(usage.cost_usd || 0);
  const tokens = Number(usage.total_tokens || 0);
  const calls = Number(usage.llm_calls || 0);
  return cost > 0 || tokens > 0 || calls > 0;
}
