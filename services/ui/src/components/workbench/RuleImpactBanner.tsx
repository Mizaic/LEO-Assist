"use client";

/**
 * RuleImpactBanner - shows how many encounters a guard rule pattern would match.
 * Calls /api/admin/workbench/rule-impact-preview with the current pattern.
 * Renders a lightweight info strip so admins can gauge impact before saving.
 */

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

export interface RuleImpactBannerProps {
  rule_id?: string;
  pattern: string;
  family?: string;
}

interface ImpactResult {
  match_count: number;
  encounter_sample: string[];
  message: string;
}

async function fetchImpactPreview(
  pattern: string,
  family?: string,
  ruleId?: string,
): Promise<ImpactResult> {
  const body: Record<string, string> = { pattern };
  if (family) body.family = family;
  if (ruleId) body.rule_id = ruleId;
  const res = await fetch("/api/admin/workbench/rule-impact-preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<ImpactResult>;
}

function useDebouncedPattern(pattern: string, delay = 600): string {
  const [debounced, setDebounced] = useState(pattern);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(pattern), delay);
    return () => clearTimeout(id);
  }, [pattern, delay]);
  return debounced;
}

export default function RuleImpactBanner({
  rule_id,
  pattern,
  family,
}: RuleImpactBannerProps) {
  const debounced = useDebouncedPattern(pattern);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImpactResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!debounced.trim()) {
      setResult(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchImpactPreview(debounced, family, rule_id)
      .then((r) => { if (!cancelled) { setResult(r); setLoading(false); } })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Preview failed");
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [debounced, family, rule_id]);

  if (!debounced.trim()) return null;

  if (loading) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5 }}>
        <CircularProgress size={14} />
        <Typography variant="caption" color="text.secondary">
          Checking impact...
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="warning" sx={{ py: 0.5, fontSize: "0.78rem" }}>
        Could not preview impact: {error}
      </Alert>
    );
  }

  if (!result) return null;

  const severity = result.match_count === 0
    ? "info"
    : result.match_count < 10
      ? "success"
      : "warning";

  return (
    <Alert
      severity={severity}
      data-testid="rule-impact-banner"
      sx={{ py: 0.5, fontSize: "0.78rem" }}
    >
      {result.message ||
        `This pattern would match ${result.match_count} encounter${result.match_count !== 1 ? "s" : ""}.`}
    </Alert>
  );
}
