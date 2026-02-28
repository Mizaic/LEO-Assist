"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RefreshIcon from "@mui/icons-material/Refresh";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

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
  total_versions: number;
}

interface CanaryPerLabel {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  tp: number;
  fp: number;
  fn: number;
}

interface CanaryMetrics {
  overall: {
    precision: number;
    recall: number;
    f1: number;
    tp: number;
    fp: number;
    fn: number;
  };
  per_label: CanaryPerLabel[];
}

interface CanaryJob {
  job_id: string;
  version: string;
  status: "accepted" | "running" | "completed" | "failed";
  phase?: string;
  message?: string;
  progress?: number;
  metrics?: CanaryMetrics;
}

const MODEL_CANARY_MIN_PRECISION = 0.78;
const MODEL_CANARY_MIN_RECALL = 0.72;
const BACKBONE = "emilyalsentzer/Bio_ClinicalBERT";

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
    canary: { label: "Canary", color: "info" },
    offline_validated: { label: "Validated", color: "warning" },
    registered: { label: "Registered", color: "default" },
    deprecated: { label: "Deprecated", color: "error" },
    rollback: { label: "Rolled Back", color: "warning" },
  };
  const cfg = map[status];
  return <Chip size="small" label={cfg.label} color={cfg.color} />;
}

export default function ModelLifecyclePanel() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [versions, setVersions] = useState<ModelRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [rollbackConfirmOpen, setRollbackConfirmOpen] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const [goldJobId, setGoldJobId] = useState<string | null>(null);
  const [goldJob, setGoldJob] = useState<CanaryJob | null>(null);

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
      setError(e instanceof Error ? e.message : "Failed to load model deployment data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!goldJobId) return;
    const timer = window.setInterval(async () => {
      try {
        const res = await fetch(`/api/model-registry/canary-jobs/${goldJobId}`);
        if (!res.ok) return;
        const data = (await res.json()) as CanaryJob;
        setGoldJob(data);
        if (data.status === "completed" || data.status === "failed") {
          window.clearInterval(timer);
          setGoldJobId(null);
          await loadAll();
        }
      } catch {
        // ignore transient polling failures
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [goldJobId, loadAll]);

  const active = status?.active_model ?? null;
  const ready = useMemo(
    () => versions.find((v) => v.status === "offline_validated"),
    [versions],
  );

  const canaryVersion = useMemo(
    () =>
      versions.find((v) => v.status === "canary") ??
      (goldJob?.version ? versions.find((v) => v.model_version === goldJob.version) : undefined),
    [goldJob?.version, versions],
  );

  const canaryPass =
    (canaryVersion?.canary_precision ?? 0) >= MODEL_CANARY_MIN_PRECISION &&
    (canaryVersion?.canary_recall ?? 0) >= MODEL_CANARY_MIN_RECALL;

  async function runGoldTest(version: string) {
    setBusyAction(`run-gold:${version}`);
    setError(null);
    try {
      const res = await fetch(`/api/model-registry/versions/${version}/canary/run-gold`, {
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`Gold test started for v${version}.`);
      setGoldJobId(data.job_id);
      setGoldJob({
        job_id: data.job_id,
        version,
        status: "accepted",
        phase: "queued",
        message: "Queued",
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start gold test");
    } finally {
      setBusyAction(null);
    }
  }

  async function promote(version: string) {
    setBusyAction(`promote:${version}`);
    setError(null);
    try {
      const res = await fetch(`/api/model-registry/versions/${version}/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rollback_target_version: active?.model_version ?? null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`v${version} promoted and inference hot-reload triggered.`);
      await loadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Promote failed");
    } finally {
      setBusyAction(null);
    }
  }

  async function reject(version: string) {
    if (!window.confirm(`Reject v${version}? This marks the version deprecated.`)) return;
    setBusyAction(`reject:${version}`);
    setError(null);
    try {
      const res = await fetch(`/api/model-registry/versions/${version}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Rejected after gold patient review" }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`v${version} rejected and deprecated.`);
      setGoldJob(null);
      await loadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Reject failed");
    } finally {
      setBusyAction(null);
    }
  }

  async function rollback() {
    setBusyAction("rollback");
    setError(null);
    try {
      const res = await fetch("/api/model-registry/rollback", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`Rolled back to v${data.rolled_back_to}.`);
      await loadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Rollback failed");
    } finally {
      setBusyAction(null);
      setRollbackConfirmOpen(false);
    }
  }

  return (
    <Box sx={{ maxWidth: 1280, mx: "auto", px: 2 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" mb={2}>
        <Box>
          <Typography variant="h6" fontWeight={700}>
            Model Deployment
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Review metrics, run automated gold patient test, then promote or reject.
          </Typography>
        </Box>
        <Button startIcon={<RefreshIcon />} onClick={loadAll} disabled={loading} variant="outlined" size="small">
          Refresh
        </Button>
      </Stack>

      {loading && <LinearProgress sx={{ mb: 2 }} />}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {info && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setInfo(null)}>{info}</Alert>}

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ xs: "flex-start", md: "center" }}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle2" fontWeight={700}>Live model</Typography>
              {active ? (
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mt: 0.5 }}>
                  <Typography variant="body2"><strong>Version:</strong> v{active.model_version}</Typography>
                  <Typography variant="body2"><strong>Promoted:</strong> {fmtDate(active.promoted_at)}</Typography>
                  <Typography variant="body2"><strong>Backbone:</strong> {BACKBONE}</Typography>
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  No model promoted yet.
                </Typography>
              )}
            </Box>
            <Stack spacing={0.5}>
              <Typography variant="caption" color="text.secondary">Training P/R/F1</Typography>
              <Typography variant="body2">
                {pct(active?.offline_precision)} / {pct(active?.offline_recall)} / {pct(f1(active?.offline_precision, active?.offline_recall))}
              </Typography>
            </Stack>
            <Stack spacing={0.5}>
              <Typography variant="caption" color="text.secondary">Gold P/R/F1</Typography>
              <Typography variant="body2">
                {pct(active?.canary_precision)} / {pct(active?.canary_recall)} / {pct(f1(active?.canary_precision, active?.canary_recall))}
              </Typography>
            </Stack>
            <Stack spacing={0.5}>
              <Typography variant="caption" color="text.secondary">Inference health</Typography>
              {healthChip(status?.inference_service)}
              <Typography variant="caption" color="text.secondary">
                Active in memory: {status?.inference_service?.active_version || "none"}
              </Typography>
            </Stack>
            {active?.rollback_target_version && (
              <Button
                color="warning"
                variant="contained"
                onClick={() => setRollbackConfirmOpen(true)}
                disabled={busyAction === "rollback"}
              >
                {busyAction === "rollback" ? <CircularProgress size={16} /> : `Rollback to v${active.rollback_target_version}`}
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Stack direction={{ xs: "column", lg: "row" }} spacing={2} sx={{ mb: 2 }}>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={0.5}>Ready for testing</Typography>
            {!ready ? (
              <Alert severity="info">
                No offline-validated model is waiting for gold test. Complete a training run in the Training Data tab.
              </Alert>
            ) : (
              <>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} mb={1}>
                  <Typography variant="body2"><strong>Version:</strong> v{ready.model_version}</Typography>
                  <Typography variant="body2"><strong>Trained:</strong> {fmtDate(ready.registered_at)}</Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  Training metrics
                </Typography>
                <Typography variant="body2" sx={{ mb: 1.5 }}>
                  P {pct(ready.offline_precision)} | R {pct(ready.offline_recall)} | F1 {pct(f1(ready.offline_precision, ready.offline_recall))}
                </Typography>
                {ready.notes && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
                    Notes: {ready.notes}
                  </Typography>
                )}
                {goldJobId && goldJob?.version === ready.model_version && (
                  <Box sx={{ mb: 1.5 }}>
                    <Typography variant="body2" sx={{ mb: 0.5 }}>
                      {goldJob.message || "Running gold test..."}
                    </Typography>
                    {(goldJob.status === "accepted" || goldJob.status === "running") && <LinearProgress />}
                  </Box>
                )}
                <Button
                  variant="contained"
                  onClick={() => runGoldTest(ready.model_version)}
                  disabled={busyAction === `run-gold:${ready.model_version}` || !!goldJobId}
                >
                  {busyAction === `run-gold:${ready.model_version}` ? <CircularProgress size={16} /> : "Run gold patient test"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={0.5}>Gold test results</Typography>
            {!canaryVersion ? (
              <Typography variant="body2" color="text.secondary">
                Results appear here after the automated gold test completes.
              </Typography>
            ) : (
              <>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  v{canaryVersion.model_version} | Training F1 {pct(f1(canaryVersion.offline_precision, canaryVersion.offline_recall))}
                  {" "}→ Gold F1 {pct(f1(canaryVersion.canary_precision, canaryVersion.canary_recall))}
                </Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} mb={1}>
                  <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
                    <Typography variant="caption" color="text.secondary">Gold Precision</Typography>
                    <Typography variant="h6">{pct(canaryVersion.canary_precision)}</Typography>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
                    <Typography variant="caption" color="text.secondary">Gold Recall</Typography>
                    <Typography variant="h6">{pct(canaryVersion.canary_recall)}</Typography>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1.5, minWidth: 180 }}>
                    <Typography variant="caption" color="text.secondary">Threshold Gate</Typography>
                    <Typography variant="h6" color={canaryPass ? "success.main" : "error.main"}>
                      {canaryPass ? "PASS" : "FAIL"}
                    </Typography>
                  </Paper>
                </Stack>
                {goldJob?.status === "completed" && goldJob.metrics?.per_label?.length ? (
                  <Accordion disableGutters>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="body2" fontWeight={600}>Per-label gold metrics</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Label</TableCell>
                            <TableCell>Gold P</TableCell>
                            <TableCell>Gold R</TableCell>
                            <TableCell>Gold F1</TableCell>
                            <TableCell>Delta vs training F1</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {goldJob.metrics.per_label.map((row) => {
                            const trainF1 = f1(canaryVersion.offline_precision, canaryVersion.offline_recall) ?? 0;
                            const delta = row.f1 - trainF1;
                            return (
                              <TableRow key={row.label}>
                                <TableCell>{row.label}</TableCell>
                                <TableCell>{pct(row.precision)}</TableCell>
                                <TableCell>{pct(row.recall)}</TableCell>
                                <TableCell>{pct(row.f1)}</TableCell>
                                <TableCell sx={{ color: delta >= 0 ? "success.main" : "error.main" }}>
                                  {(delta * 100).toFixed(1)}%
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </AccordionDetails>
                  </Accordion>
                ) : (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                    Per-label detail is shown for the latest completed gold run in this session.
                  </Typography>
                )}
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Tooltip title={canaryPass ? "" : "Canary thresholds not met"}>
                    <span>
                      <Button
                        variant="contained"
                        color="success"
                        disabled={!canaryPass || busyAction === `promote:${canaryVersion.model_version}`}
                        onClick={() => promote(canaryVersion.model_version)}
                      >
                        {busyAction === `promote:${canaryVersion.model_version}` ? <CircularProgress size={16} /> : "Promote to live"}
                      </Button>
                    </span>
                  </Tooltip>
                  <Button
                    variant="outlined"
                    color="error"
                    onClick={() => reject(canaryVersion.model_version)}
                    disabled={busyAction === `reject:${canaryVersion.model_version}`}
                  >
                    {busyAction === `reject:${canaryVersion.model_version}` ? <CircularProgress size={16} /> : "Reject this version"}
                  </Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                  Gate: precision ≥ {(MODEL_CANARY_MIN_PRECISION * 100).toFixed(0)}%, recall ≥ {(MODEL_CANARY_MIN_RECALL * 100).toFixed(0)}%
                </Typography>
              </>
            )}
          </CardContent>
        </Card>
      </Stack>

      <Accordion defaultExpanded={false}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle1" fontWeight={700}>Version history</Typography>
        </AccordionSummary>
        <AccordionDetails>
          {versions.length === 0 ? (
            <Alert severity="info">No model versions found yet.</Alert>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Version</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Training P/R/F1</TableCell>
                  <TableCell>Gold P/R/F1</TableCell>
                  <TableCell>Promoted</TableCell>
                  <TableCell>Notes</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {versions.map((v) => (
                  <TableRow key={v.model_version}>
                    <TableCell>v{v.model_version}</TableCell>
                    <TableCell>{statusChip(v.status)}</TableCell>
                    <TableCell>
                      {pct(v.offline_precision)} / {pct(v.offline_recall)} / {pct(f1(v.offline_precision, v.offline_recall))}
                    </TableCell>
                    <TableCell>
                      {pct(v.canary_precision)} / {pct(v.canary_recall)} / {pct(f1(v.canary_precision, v.canary_recall))}
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

      <Divider sx={{ my: 3 }} />
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" fontWeight={700}>Training corpus source</Typography>
        <Typography variant="body2" color="text.secondary">
          Training labels are managed in the Training Data tab. Training worker handles register, upload, and offline validation automatically.
        </Typography>
      </Paper>

      <Dialog open={rollbackConfirmOpen} onClose={() => setRollbackConfirmOpen(false)}>
        <DialogTitle>Confirm rollback</DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={1} alignItems="center">
            <WarningAmberIcon color="warning" />
            <Typography variant="body2">
              Roll back live model to v{active?.rollback_target_version}? Inference service hot-reload will be triggered immediately.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRollbackConfirmOpen(false)}>Cancel</Button>
          <Button color="warning" variant="contained" onClick={rollback}>
            Confirm rollback
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
