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
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";
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
    canary: { label: "Being tested", color: "info" },
    offline_validated: { label: "Ready to test", color: "warning" },
    registered: { label: "Registered", color: "default" },
    deprecated: { label: "Retired", color: "error" },
    rollback: { label: "Switched back", color: "warning" },
  };
  const cfg = map[status];
  return <Chip size="small" label={cfg.label} color={cfg.color} />;
}

const DEPLOYMENT_STAGES: TabStage[] = [
  {
    id: "md1", num: 1,
    label: "AI trained",
    tooltip: "A new version of the AI has finished learning. It now needs to be tested before it can go live.",
    detailIn: "A completed learning run from the Teach the AI tab",
    detailOut: "A new AI version waiting to be tested",
  },
  {
    id: "md2", num: 2,
    label: "Safety test",
    tooltip: "We test the new AI on real patient examples where we already know the right answers. This checks that it learned correctly.",
    detailIn: "The new AI and a set of checked patient examples",
    detailOut: "Accuracy and completeness scores from the test",
    branches: [
      {
        label: "Test already running",
        description: "You can only run one safety test at a time. Wait for it to finish before starting another",
      },
    ],
  },
  {
    id: "md3", num: 3,
    label: "Check scores",
    tooltip: "We look at the test results. The AI must get at least 78% of answers right and find at least 72% of items to pass.",
    detailIn: "The test scores for each type of medical word",
    detailOut: "A pass or fail result",
    branches: [
      {
        label: "Did not pass",
        description: "If the AI does not meet the required scores, you can reject it. You can still make it live anyway, but this is recorded for audit",
      },
    ],
  },
  {
    id: "md4", num: 4,
    label: "Go live",
    tooltip: "If the AI passes, you make it live. It becomes the main AI used from that moment on.",
    detailIn: "Your decision to make the AI live",
    detailOut: "The new AI is live; the old version is retired",
    branches: [
      {
        label: "Switch back",
        description: "If the live AI has problems, you can switch back to the previous version at any time",
      },
    ],
  },
  {
    id: "md5", num: 5,
    label: "Watch it",
    tooltip: "We keep checking the health of the live AI. If it stops responding or gives strange results, an alert appears here.",
    detailIn: "The live AI running in the pipeline",
    detailOut: "A health status: OK, degraded, or unreachable",
  },
];

export default function ModelLifecyclePanel() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [versions, setVersions] = useState<ModelRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [rollbackConfirmOpen, setRollbackConfirmOpen] = useState(false);
  const [forcePromoteConfirmOpen, setForcePromoteConfirmOpen] = useState(false);
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
      setError(e instanceof Error ? e.message : "Could not load the AI deployment information. Please try again.");
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
      setInfo(`Safety test started for version ${version}.`);
      setGoldJobId(data.job_id);
      setGoldJob({
        job_id: data.job_id,
        version,
        status: "accepted",
        phase: "queued",
        message: "Queued",
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not start the safety test. Please try again.");
    } finally {
      setBusyAction(null);
    }
  }

  async function promote(version: string, force = false) {
    setBusyAction(`promote:${version}`);
    setError(null);
    try {
      const res = await fetch(`/api/model-registry/versions/${version}/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rollback_target_version: active?.model_version ?? null,
          force,
          force_reason: force ? "Manual override — recall gate failed; labels to be improved and model retrained." : "",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`Version ${version} is now live${force ? " (quality check was overridden)" : ""}. The AI will start using it straight away.`);
      setForcePromoteConfirmOpen(false);
      await loadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not make the AI live. Please try again.");
    } finally {
      setBusyAction(null);
    }
  }

  const [rejectConfirmVersion, setRejectConfirmVersion] = useState<string | null>(null);

  function requestReject(version: string) {
    setRejectConfirmVersion(version);
  }

  async function reject(version: string) {
    setRejectConfirmVersion(null);
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
      setInfo(`Version ${version} has been rejected and retired.`);
      setGoldJob(null);
      await loadAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not reject this version. Please try again.");
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
            Make the AI live
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: 13 }}>
            Check the scores, run a safety test, then make the AI live or reject it.
          </Typography>
        </Box>
        <Button startIcon={<RefreshIcon />} onClick={loadAll} disabled={loading} variant="outlined" size="small">
          Refresh
        </Button>
      </Stack>

      {/* How this works */}
      <Accordion variant="outlined" disableGutters sx={{ "&::before": { display: "none" } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.75 } }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
            How this tab works
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0, pb: 1.5 }}>
          <TabFlowDiagram
            stages={DEPLOYMENT_STAGES}
            color="#059669"
            lightColor="#D1FAE5"
            trackLabel="Make the AI live"
          />
        </AccordionDetails>
      </Accordion>

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
                  <Typography variant="caption"><strong>Base model:</strong> {BACKBONE}</Typography>
                </Stack>
              ) : (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
                  No AI is live yet. Run a safety test and make one live.
                </Typography>
              )}
            </Box>
            <Stack spacing={0.25}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Training score</Typography>
              <Typography variant="caption" sx={{ fontWeight: 600 }}>
                {pct(active?.offline_precision)} / {pct(active?.offline_recall)} / {pct(f1(active?.offline_precision, active?.offline_recall))}
              </Typography>
            </Stack>
            <Stack spacing={0.25}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Safety test score</Typography>
              <Typography variant="caption" sx={{ fontWeight: 600 }}>
                {pct(active?.canary_precision)} / {pct(active?.canary_recall)} / {pct(f1(active?.canary_precision, active?.canary_recall))}
              </Typography>
            </Stack>
            <Stack spacing={0.25}>
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>AI service status</Typography>
              {healthChip(status?.inference_service)}
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>
                Running: {status?.inference_service?.active_version || "none"}
              </Typography>
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

      <Stack direction={{ xs: "column", lg: "row" }} spacing={1.5}>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
            <Typography variant="subtitle2" fontWeight={700} mb={0.5}>Ready for safety test</Typography>
            {!ready ? (
              <Alert severity="info" sx={{ py: 0.25 }}>
                No AI is waiting to be tested. Complete a learning run in the Teach the AI tab first.
              </Alert>
            ) : (
              <>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} mb={0.75}>
                  <Typography variant="caption"><strong>Version:</strong> {ready.model_version}</Typography>
                  <Typography variant="caption"><strong>Finished learning:</strong> {fmtDate(ready.registered_at)}</Typography>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.25 }}>
                  Training scores
                </Typography>
                <Typography variant="caption" sx={{ display: "block", mb: 1, fontWeight: 600 }}>
                  Accuracy {pct(ready.offline_precision)} | Completeness {pct(ready.offline_recall)} | Overall {pct(f1(ready.offline_precision, ready.offline_recall))}
                </Typography>
                {ready.notes && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                    Notes: {ready.notes}
                  </Typography>
                )}
                {goldJobId && goldJob?.version === ready.model_version && (
                  <Box sx={{ mb: 1.5 }}>
                    <Typography variant="body2" sx={{ mb: 0.5 }}>
                      {goldJob.message || "Running safety test..."}
                    </Typography>
                    {(goldJob.status === "accepted" || goldJob.status === "running") && <LinearProgress />}
                  </Box>
                )}
                <Button
                  variant="contained"
                  onClick={() => runGoldTest(ready.model_version)}
                  disabled={busyAction === `run-gold:${ready.model_version}` || !!goldJobId}
                >
                  {busyAction === `run-gold:${ready.model_version}` ? <CircularProgress aria-label="Loading" size={16} /> : "Run safety test"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={700} mb={0.5}>Safety test results</Typography>
            {!canaryVersion ? (
              <Typography variant="body2" color="text.secondary">
                Results appear here after the safety test finishes.
              </Typography>
            ) : (
              <>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  Version {canaryVersion.model_version} | Training score {pct(f1(canaryVersion.offline_precision, canaryVersion.offline_recall))}
                  {" "}→ Safety test score {pct(f1(canaryVersion.canary_precision, canaryVersion.canary_recall))}
                </Typography>
                <Stack direction="row" spacing={1.5} mb={1} flexWrap="wrap" useFlexGap>
                  <Paper variant="outlined" sx={{ p: 1, minWidth: 120, flex: "1 1 120px" }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Accuracy</Typography>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{pct(canaryVersion.canary_precision)}</Typography>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1, minWidth: 120, flex: "1 1 120px" }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Completeness</Typography>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{pct(canaryVersion.canary_recall)}</Typography>
                  </Paper>
                  <Paper variant="outlined" sx={{ p: 1, minWidth: 120, flex: "1 1 120px" }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>Quality check</Typography>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }} color={canaryPass ? "success.main" : "error.main"}>
                      {canaryPass ? "PASSED" : "DID NOT PASS"}
                    </Typography>
                  </Paper>
                </Stack>
                {/* Error from a failed gold run */}
                {goldJob?.version === canaryVersion.model_version &&
                  goldJob.status === "failed" && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      Safety test did not finish: {goldJob.message}
                    </Alert>
                  )}

                {/* Progress bar while a gold run is active for this version */}
                {goldJobId &&
                  goldJob?.version === canaryVersion.model_version &&
                  (goldJob.status === "accepted" || goldJob.status === "running") && (
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="body2" sx={{ mb: 0.75 }}>
                        {goldJob.phase === "downloading_model"
                          ? "Getting the AI ready..."
                          : goldJob.phase === "loading_gold_data"
                            ? "Loading test patient records..."
                            : goldJob.phase === "scoring"
                              ? `Testing the AI${goldJob.progress != null ? ` -- ${Math.round(goldJob.progress * 100)}% done` : "..."}`
                              : goldJob.message ?? "Running safety test..."}
                      </Typography>
                      <LinearProgress
                        variant={goldJob.progress != null ? "determinate" : "indeterminate"}
                        value={(goldJob.progress ?? 0) * 100}
                        aria-label="Safety test progress"
                      />
                    </Box>
                  )}

                {goldJob?.status === "completed" && goldJob.metrics?.per_label?.length ? (
                  <Accordion disableGutters>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="body2" fontWeight={600}>Scores for each type of medical word</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Word type</TableCell>
                            <TableCell>Accuracy</TableCell>
                            <TableCell>Completeness</TableCell>
                            <TableCell>Overall</TableCell>
                            <TableCell>Change from training</TableCell>
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
                    Detailed scores for each word type appear after the safety test finishes.
                  </Typography>
                )}
                <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap">
                  <Tooltip title={canaryPass ? "" : "The AI did not pass the quality check"}>
                    <span>
                      <Button
                        variant="contained"
                        color="success"
                        disabled={!canaryPass || busyAction === `promote:${canaryVersion.model_version}`}
                        onClick={() => promote(canaryVersion.model_version)}
                      >
                        {busyAction === `promote:${canaryVersion.model_version}` ? <CircularProgress aria-label="Loading" size={16} /> : "Make this AI live"}
                      </Button>
                    </span>
                  </Tooltip>
                  {!canaryPass && canaryVersion.canary_precision !== null && (
                    <Tooltip title="Go live anyway even though the AI did not pass — this will be recorded for audit">
                      <Button
                        variant="outlined"
                        color="warning"
                        onClick={() => setForcePromoteConfirmOpen(true)}
                        disabled={!!busyAction}
                      >
                        Go live anyway
                      </Button>
                    </Tooltip>
                  )}
                  {canaryVersion.canary_precision === null && (
                    <Button
                      variant="contained"
                      color="primary"
                      onClick={() => runGoldTest(canaryVersion.model_version)}
                      disabled={busyAction === `run-gold:${canaryVersion.model_version}` || !!goldJobId}
                    >
                      {busyAction === `run-gold:${canaryVersion.model_version}` ? <CircularProgress aria-label="Loading" size={16} /> : "Run safety test again"}
                    </Button>
                  )}
                  <Button
                    variant="outlined"
                    color="error"
                    onClick={() => requestReject(canaryVersion.model_version)}
                    disabled={busyAction === `reject:${canaryVersion.model_version}`}
                  >
                    {busyAction === `reject:${canaryVersion.model_version}` ? <CircularProgress aria-label="Loading" size={16} /> : "Reject this version"}
                  </Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                  The AI must get at least {(MODEL_CANARY_MIN_PRECISION * 100).toFixed(0)}% of answers right and find at least {(MODEL_CANARY_MIN_RECALL * 100).toFixed(0)}% of items to pass.
                </Typography>
              </>
            )}
          </CardContent>
        </Card>
      </Stack>

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
                  <TableCell>Training score</TableCell>
                  <TableCell>Safety test score</TableCell>
                  <TableCell>Made live</TableCell>
                  <TableCell>Notes</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {versions.map((v) => (
                  <TableRow key={v.model_version}>
                    <TableCell>{v.model_version}</TableCell>
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
        <Typography variant="subtitle1" fontWeight={700}>Where the teaching examples come from</Typography>
        <Typography variant="body2" color="text.secondary">
          Teaching records are managed in the Teach the AI tab. The system handles uploading and checking automatically.
        </Typography>
      </Paper>

      {forcePromoteConfirmOpen && (
        <ConfirmDialog
          title="Go live anyway? The AI did not pass the safety test"
          body={`The AI did not meet the required scores (accuracy at least ${(MODEL_CANARY_MIN_PRECISION * 100).toFixed(0)}%, completeness at least ${(MODEL_CANARY_MIN_RECALL * 100).toFixed(0)}%). Current results: accuracy ${pct(canaryVersion?.canary_precision)}, completeness ${pct(canaryVersion?.canary_recall)}. Making it live will be flagged for audit. Only do this if you plan to retrain soon.`}
          confirmLabel={busyAction === `promote:${canaryVersion?.model_version}` ? "Working..." : "Go live anyway"}
          variant="danger"
          onConfirm={() => canaryVersion && promote(canaryVersion.model_version, true)}
          onCancel={() => setForcePromoteConfirmOpen(false)}
        />
      )}

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

      {!!rejectConfirmVersion && (
        <ConfirmDialog
          title="Reject this AI version?"
          body={`Version ${rejectConfirmVersion} will be marked as retired and cannot be made live. This cannot be undone.`}
          confirmLabel="Reject"
          variant="danger"
          onConfirm={() => rejectConfirmVersion && reject(rejectConfirmVersion)}
          onCancel={() => setRejectConfirmVersion(null)}
        />
      )}
    </Stack>
  );
}
