"use client";

/**
 * RuleHistoryPanel - shows the version history for a guard rule and allows
 * one-click revert to any prior version. History is loaded from
 * GET /api/admin/workbench/guard-rules/:rule_id/history.
 *
 * Each version shows: timestamp, who changed it, pattern before/after.
 * Revert calls PUT /api/admin/workbench/guard-rules/:rule_id with the
 * prior version's fields.
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import HistoryIcon from "@mui/icons-material/History";
import RestoreIcon from "@mui/icons-material/Restore";

export interface RuleVersion {
  version: number;
  changed_at: string;
  changed_by: string;
  pattern: string;
  rule_type: string;
  active: boolean;
  revert_available: boolean;
}

export interface RuleHistoryPanelProps {
  rule_id: string;
  onReverted?: () => void;
}

async function fetchHistory(ruleId: string): Promise<RuleVersion[]> {
  const res = await fetch(
    `/api/admin/workbench/guard-rules/${ruleId}/history`,
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<RuleVersion[]>;
}

async function revertToVersion(
  ruleId: string,
  version: RuleVersion,
): Promise<void> {
  const res = await fetch(`/api/admin/workbench/guard-rules/${ruleId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pattern: version.pattern,
      rule_type: version.rule_type,
      active: version.active,
    }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function RuleHistoryPanel({
  rule_id,
  onReverted,
}: RuleHistoryPanelProps) {
  const [history, setHistory] = useState<RuleVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reverting, setReverting] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHistory(rule_id);
      setHistory(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, [rule_id]);

  useEffect(() => { void load(); }, [load]);

  const handleRevert = async (v: RuleVersion) => {
    setReverting(v.version);
    try {
      await revertToVersion(rule_id, v);
      onReverted?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Revert failed");
    } finally {
      setReverting(null);
    }
  };

  return (
    <Box data-testid="rule-history-panel">
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 1.5 }}>
        <HistoryIcon sx={{ fontSize: 16, color: "text.secondary" }} />
        <Typography variant="subtitle2" fontWeight={600}>
          Version history
        </Typography>
      </Box>

      {loading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 1 }}>
          <CircularProgress size={14} />
          <Typography variant="caption" color="text.secondary">
            Loading history...
          </Typography>
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 1, fontSize: "0.78rem" }}>
          {error}
        </Alert>
      )}

      {!loading && history.length === 0 && !error && (
        <Typography variant="caption" color="text.secondary">
          No previous versions recorded.
        </Typography>
      )}

      {history.map((v, i) => (
        <Paper
          key={v.version}
          variant="outlined"
          sx={{ p: 1.5, mb: 1, borderRadius: 1.5 }}
          data-testid={`rule-version-${v.version}`}
        >
          <Box
            sx={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: 1,
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Box
                sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}
              >
                <Chip
                  label={`v${v.version}`}
                  size="small"
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                {i === 0 && (
                  <Chip
                    label="Current"
                    size="small"
                    color="primary"
                    sx={{ height: 18, fontSize: "0.65rem" }}
                  />
                )}
                <Typography variant="caption" color="text.secondary">
                  {formatTs(v.changed_at)} &mdash; {v.changed_by}
                </Typography>
              </Box>
              <Typography
                variant="caption"
                sx={{
                  fontFamily: "monospace",
                  bgcolor: "#F8FAFC",
                  px: 0.75,
                  py: 0.25,
                  borderRadius: 0.5,
                  display: "block",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {v.pattern}
              </Typography>
            </Box>
            {v.revert_available && i > 0 && (
              <Button
                size="small"
                variant="outlined"
                startIcon={<RestoreIcon />}
                disabled={reverting === v.version}
                onClick={() => void handleRevert(v)}
                data-testid={`revert-to-v${v.version}`}
              >
                {reverting === v.version ? "Reverting..." : "Revert"}
              </Button>
            )}
          </Box>
        </Paper>
      ))}

      {history.length > 1 && <Divider sx={{ mt: 1 }} />}
    </Box>
  );
}
