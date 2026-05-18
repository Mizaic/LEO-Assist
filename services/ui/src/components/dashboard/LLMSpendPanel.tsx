/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import MemoryIcon from "@mui/icons-material/Memory";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/authContext";

// ── Types ────────────────────────────────────────────────────────────────────

interface RunSpend {
  runId: string;
  patientId: string;
  encounterId: string;
  status: string;
  durationMs: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  costUsd: number;
  createdAt: string;
}

interface SpendTotals {
  runCount?: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  costUsd: number;
  cacheHitRate: number;
}

interface RunSpendResponse {
  runs: RunSpend[];
  totals: SpendTotals;
}

interface LLMSpendPanelProps {
  orgId?: string | null;
  from?: string | null;
  to?: string | null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt$(n: number): string {
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(5)}`;
  return `$${n.toFixed(4)}`;
}

function fmtTok(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function CostSummaryRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ py: 0.4 }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="caption" fontWeight={highlight ? 700 : 400}
        color={highlight ? "success.dark" : "text.primary"} sx={{ fontFamily: "monospace" }}>
        {value}
      </Typography>
    </Stack>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function LLMSpendPanel({ orgId, from, to }: LLMSpendPanelProps) {
  const { session } = useAuth();
  const isAdmin = session?.isPlatformAdmin ?? false;
  const usesExternalFilters = typeof from === "string" || typeof to === "string";
  const scopeLabel = isAdmin
    ? (orgId ? "(selected organisation)" : "(all organisations)")
    : "(your organisation)";

  const [period, setPeriod] = useState<"today" | "7d" | "30d">("7d");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<RunSpendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const now = new Date();
      const fromDate = new Date(now);
      let toDate: Date | null = null;

      if (usesExternalFilters) {
        if (from) fromDate.setTime(new Date(from).getTime());
        if (to) {
          toDate = new Date(to);
          toDate.setHours(23, 59, 59, 999);
        }
      } else if (period === "today") {
        fromDate.setHours(0, 0, 0, 0);
      } else if (period === "7d") {
        fromDate.setDate(now.getDate() - 7);
      } else {
        fromDate.setDate(now.getDate() - 30);
      }

      const params = new URLSearchParams({ limit: "200" });
      if (!Number.isNaN(fromDate.getTime())) params.set("from", fromDate.toISOString());
      if (toDate && !Number.isNaN(toDate.getTime())) params.set("to", toDate.toISOString());
      if (orgId) params.set("org_id", orgId);

      const resp = await api.get<RunSpendResponse>(`/api/analytics/llm-spend/runs?${params}`);
      setData(resp);
    } catch {
      setError("LLM spend data unavailable");
    } finally {
      setLoading(false);
    }
  }, [period, from, to, orgId, usesExternalFilters]);

  useEffect(() => { load(); }, [load]);

  const totals = data?.totals;
  const runs   = data?.runs ?? [];

  return (
    <Card>
      <CardContent>
        <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "flex-start", sm: "center" }} sx={{ mb: 1.5 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <MemoryIcon sx={{ fontSize: 20, color: "primary.main" }} />
            <Typography variant="h6" component="h2" sx={{ fontSize: "1rem", fontWeight: 700 }}>
              AI model spend
            </Typography>
            <Typography variant="caption" color="text.disabled">
              {scopeLabel}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            {isAdmin && (
              <Link href="/admin/platform?tab=billing" style={{ textDecoration: "none" }}>
                <Typography variant="caption" color="primary.main" sx={{ fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
                  View all tenants →
                </Typography>
              </Link>
            )}
            {usesExternalFilters ? (
              <Typography variant="caption" color="text.secondary">
                Uses dashboard filters
              </Typography>
            ) : (
              <Select size="small" value={period} onChange={(e) => setPeriod(e.target.value as typeof period)}
                sx={{ fontSize: "0.8rem", height: 30 }}>
                <MenuItem value="today">Today</MenuItem>
                <MenuItem value="7d">Last 7 days</MenuItem>
                <MenuItem value="30d">Last 30 days</MenuItem>
              </Select>
            )}
          </Stack>
        </Stack>

        {loading && <Skeleton variant="rectangular" height={140} />}

        {!loading && error && (
          <Typography variant="body2" color="text.disabled" sx={{ py: 2, textAlign: "center" }}>
            {error}
          </Typography>
        )}

        {!loading && totals && (
          <>
            {/* Summary metrics */}
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 1.5 }}>
              <Card variant="outlined" sx={{ flex: 1, p: 1.25, borderRadius: 2 }}>
                <Typography variant="caption" color="text.secondary" display="block">Total spend</Typography>
                <Typography variant="h5" fontWeight={700} color={totals.costUsd > 0 ? "warning.dark" : "text.disabled"}>
                  {fmt$(totals.costUsd)}
                </Typography>
              </Card>
              <Card variant="outlined" sx={{ flex: 1, p: 1.25, borderRadius: 2 }}>
                <Typography variant="caption" color="text.secondary" display="block">Pipeline runs</Typography>
                <Typography variant="h5" fontWeight={700}>{(totals.runCount ?? runs.length).toLocaleString()}</Typography>
              </Card>
              <Card variant="outlined" sx={{ flex: 1, p: 1.25, borderRadius: 2 }}>
                <Typography variant="caption" color="text.secondary" display="block">Tokens used</Typography>
                <Typography variant="h5" fontWeight={700}>{fmtTok(totals.inputTokens + totals.outputTokens)}</Typography>
              </Card>
              <Card variant="outlined" sx={{ flex: 1, p: 1.25, borderRadius: 2, borderColor: totals.cacheHitRate > 0.5 ? "success.main" : "divider" }}>
                <Typography variant="caption" color="text.secondary" display="block">Cache hit rate</Typography>
                <Typography variant="h5" fontWeight={700} color={totals.cacheHitRate > 0.5 ? "success.dark" : "text.primary"}>
                  {totals.inputTokens > 0 ? `${(totals.cacheHitRate * 100).toFixed(1)}%` : "—"}
                </Typography>
              </Card>
            </Stack>

            {/* Token breakdown */}
            <Box sx={{ bgcolor: "grey.50", borderRadius: 2, p: 1.25, mb: 1.5 }}>
              <CostSummaryRow label="Input tokens (billable)" value={fmtTok(totals.inputTokens - totals.cachedTokens)} />
              <CostSummaryRow label="Input tokens (cached — discounted)" value={fmtTok(totals.cachedTokens)} highlight />
              <CostSummaryRow label="Output tokens" value={fmtTok(totals.outputTokens)} />
              <Divider sx={{ my: 0.5 }} />
              <CostSummaryRow label="Total cost" value={fmt$(totals.costUsd)} highlight />
            </Box>

            {/* Recent run list */}
            {runs.length > 0 && (
              <Box>
                <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                  RECENT RUNS (showing {Math.min(runs.length, 50)} of {totals.runCount ?? runs.length})
                </Typography>
                <Box sx={{ maxHeight: 240, overflow: "auto" }}>
                  {runs.slice(0, 50).map((run) => (
                    <Stack key={run.runId} direction="row" alignItems="center" spacing={1}
                      sx={{ py: 0.5, borderBottom: "1px solid", borderColor: "divider" }}>
                      <Chip size="small" label={run.status}
                        color={run.status === "completed" ? "success" : run.status === "error" ? "error" : "default"}
                        sx={{ height: 18, fontSize: "0.58rem", minWidth: 70 }} />
                      <Typography variant="caption" color="text.secondary" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {run.encounterId || run.patientId}
                      </Typography>
                      <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.65rem", color: "text.secondary" }}>
                        {fmtTok(run.inputTokens)} in · {fmtTok(run.outputTokens)} out
                        {run.cachedTokens > 0 && <span style={{ color: "#2e7d32" }}> · {fmtTok(run.cachedTokens)} cached</span>}
                      </Typography>
                      <Typography variant="caption" fontWeight={700} sx={{ fontFamily: "monospace", fontSize: "0.68rem", color: run.costUsd > 0 ? "warning.dark" : "text.disabled" }}>
                        {fmt$(run.costUsd)}
                      </Typography>
                    </Stack>
                  ))}
                </Box>
              </Box>
            )}

            {runs.length === 0 && totals.costUsd === 0 && (
              <Typography variant="body2" color="text.disabled" sx={{ py: 2, textAlign: "center" }}>
                No pipeline runs with LLM token data in this period.
                Token tracking is recorded once the pipeline processes encounters.
              </Typography>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
