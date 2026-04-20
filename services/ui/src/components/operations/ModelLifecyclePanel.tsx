/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A2553F87
 *   DI: DI-425CA252
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A2553F87")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RefreshIcon from "@mui/icons-material/Refresh";
import ConfirmDialog from "@/components/ConfirmDialog";

type ModelStatus =
  | "registered"
  | "offline_validated"
  | "canary"
  | "promoted"
  | "deprecated"
  | "rollback";

interface ModelRecord {
  model_name: string;
  model_version: string;
  artifact_uri: string;
  training_dataset_version: string;
  schema_version: string;
  deid_version: string;
  status: ModelStatus;
  offline_precision: number | null;
  offline_recall: number | null;
  canary_precision: number | null;
  canary_recall: number | null;
  rollback_target_version: string | null;
  registered_at: string;
  promoted_at: string | null;
  notes: string;
}

interface InferenceHealth {
  status: string;
  active_version?: string | null;
  loaded?: boolean;
}

interface StatusResponse {
  active_model: ModelRecord | null;
  inference_service: InferenceHealth;
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function f1(precision: number | null | undefined, recall: number | null | undefined): number | null {
  if (precision === null || precision === undefined || recall === null || recall === undefined) return null;
  const denom = precision + recall;
  if (denom <= 0) return 0;
  return (2 * precision * recall) / denom;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
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

function healthChip(health?: InferenceHealth | null) {
  if (!health) return <Chip size="small" label="Checking" />;
  if (health.status === "ok" && health.loaded) return <Chip size="small" label="OK" color="success" />;
  if (health.status === "unreachable") return <Chip size="small" label="Unreachable" color="error" />;
  return <Chip size="small" label="Degraded" color="warning" />;
}

function statusChip(status: ModelStatus) {
  const map: Record<ModelStatus, { label: string; color: "default" | "success" | "warning" | "info" | "error" }> = {
    promoted: { label: "Live", color: "success" },
    canary: { label: "Being tested", color: "info" },
    offline_validated: { label: "Ready to test", color: "warning" },
    registered: { label: "Registered", color: "default" },
    deprecated: { label: "Retired", color: "error" },
    rollback: { label: "Switched back", color: "warning" },
  };
  const cfg = map[status];
  return <Chip size="small" label={cfg.label} color={cfg.color} />;
}

function rowStatusChip(row: ModelRecord, activeVersion?: string | null) {
  if (activeVersion && row.model_version === activeVersion) {
    return <Chip size="small" label="Live" color="success" />;
  }
  if (row.status === "canary") {
    const hasResult =
      row.canary_precision !== null && row.canary_recall !== null;
    if (hasResult) {
      return <Chip size="small" label="Awaiting decision" color="warning" />;
    }
    return <Chip size="small" label="Test status unknown" color="default" />;
  }
  return statusChip(row.status);
}

export default function ModelLifecyclePanel() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [versions, setVersions] = useState<ModelRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [rollbackConfirmOpen, setRollbackConfirmOpen] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, versionsRes] = await Promise.all([
        fetch("/api/model-registry/status"),
        fetch("/api/model-registry/versions"),
      ]);
      if (!statusRes.ok) {
        const data = await statusRes.json().catch(() => ({}));
        throw new Error(data.detail || `Status load failed (${statusRes.status})`);
      }
      if (!versionsRes.ok) {
        const data = await versionsRes.json().catch(() => ({}));
        throw new Error(data.detail || `Versions load failed (${versionsRes.status})`);
      }
      setStatus(await statusRes.json());
      setVersions((await versionsRes.json()).versions ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not load the AI deployment information. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const active = status?.active_model ?? null;

  async function rollback() {
    setBusyAction("rollback");
    setError(null);
    try {
      const res = await fetch("/api/model-registry/rollback", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`Switched back to version ${data.rolled_back_to}. The AI will use the previous version now.`);
      await loadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not switch back to the previous AI. Please try again.");
    } finally {
      setBusyAction(null);
      setRollbackConfirmOpen(false);
    }
  }

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Box>
          <Typography variant="subtitle1" fontWeight={700} sx={{ lineHeight: 1.3 }}>
            Live deployment
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: 13 }}>
            Check which AI is live, review service health, and switch back if needed.
          </Typography>
        </Box>
        <Button startIcon={<RefreshIcon />} onClick={loadAll} disabled={loading} variant="outlined" size="small">
          Refresh
        </Button>
      </Stack>
      {loading && <LinearProgress />}
      {error && <Alert severity="error" sx={{ py: 0.25 }}>{error}</Alert>}
      {info && <Alert severity="success" sx={{ py: 0.25 }} onClose={() => setInfo(null)}>{info}</Alert>}

      <Card variant="outlined">
        <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "flex-start", md: "center" }}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle2" fontWeight={700} sx={{ fontSize: 13 }}>Live AI</Typography>
              {active ? (
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 0.25 }}>
                  <Typography variant="caption"><strong>Version:</strong> {active.model_version}</Typography>
                  <Typography variant="caption"><strong>Made live:</strong> {fmtDate(active.promoted_at)}</Typography>
                </Stack>
              ) : (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
                  No AI is live yet. Run a safety test and make one live.
                </Typography>
              )}
            </Box>
            <Stack spacing={0.25}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Learning scores</Typography>
              <Typography variant="caption" sx={{ fontWeight: 600 }}>
                Right: {pct(active?.offline_precision)}, Found: {pct(active?.offline_recall)}
              </Typography>
            </Stack>
            <Stack spacing={0.25}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Safety test scores</Typography>
              <Typography variant="caption" sx={{ fontWeight: 600 }}>
                Right: {pct(active?.canary_precision)}, Found: {pct(active?.canary_recall)}
              </Typography>
            </Stack>
            <Stack spacing={0.25}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Is it running?</Typography>
              {healthChip(status?.inference_service)}
              {status?.inference_service?.active_version && (
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>
                  Version: {status.inference_service.active_version}
                </Typography>
              )}
            </Stack>
            {active?.rollback_target_version && (
              <Button
                color="warning"
                variant="outlined"
                size="small"
                onClick={() => setRollbackConfirmOpen(true)}
                disabled={busyAction === "rollback"}
              >
                {busyAction === "rollback" ? <CircularProgress aria-label="Loading" size={14} /> : `Switch back to version ${active.rollback_target_version}`}
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Accordion defaultExpanded={false} disableGutters variant="outlined" sx={{ "&::before": { display: "none" } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.75 } }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ fontSize: 13 }}>Past versions</Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ p: 0 }}>
          {versions.length === 0 ? (
            <Alert severity="info" sx={{ m: 1.5, py: 0.25 }}>No AI versions have been created yet.</Alert>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Version</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Learning: right / found</TableCell>
                  <TableCell>Safety test: right / found</TableCell>
                  <TableCell>Made live</TableCell>
                  <TableCell>Notes</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {versions.map((v) => (
                  <TableRow key={v.model_version}>
                    <TableCell>{v.model_version}</TableCell>
                    <TableCell>{rowStatusChip(v, active?.model_version)}</TableCell>
                    <TableCell>
                      {pct(v.offline_precision)} / {pct(v.offline_recall)}
                    </TableCell>
                    <TableCell>
                      {pct(v.canary_precision)} / {pct(v.canary_recall)}
                    </TableCell>
                    <TableCell>{fmtDate(v.promoted_at)}</TableCell>
                    <TableCell sx={{ maxWidth: 320 }}>
                      <Typography variant="caption" color="text.secondary">
                        {v.notes || "—"}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </AccordionDetails>
      </Accordion>

      {rollbackConfirmOpen && (
        <ConfirmDialog
          title="Switch back to the previous AI?"
          body={`This will switch the live AI back to version ${active?.rollback_target_version}. The change takes effect straight away.`}
          confirmLabel="Switch back"
          variant="danger"
          onConfirm={rollback}
          onCancel={() => setRollbackConfirmOpen(false)}
        />
      )}
    </Stack>
  );
}
