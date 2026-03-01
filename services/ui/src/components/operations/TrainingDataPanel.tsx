"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  IconButton,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import BlockIcon from "@mui/icons-material/Block";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import HourglassTopIcon from "@mui/icons-material/HourglassTop";
import PauseIcon from "@mui/icons-material/Pause";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface LabelStats {
  total: number;
  included: number;
  excluded: number;
  by_source: Record<string, number>;
  by_label_type: Record<string, number>;
}

interface TrainingLabel {
  label_id: string;
  encounter_id: string;
  text: string;
  entities_json: string;
  source: string;
  include: boolean;
  excluded_reason: string | null;
  quality_score: number;
  updated_at: string;
}

interface TrainingJob {
  job_id: string;
  status: string;
  phase: string;
  notes: string;
  triggered_by: string;
  log_lines: string[];
  metrics: Record<string, unknown>;
  artifact_uri: string;
  model_version: string;
  error: string;
  created_at: number;
  elapsed_s: number | null;
}

interface ExportPreview {
  exportable_label_count: number;
  ready_to_train: boolean;
  min_required: number;
  by_label_type: Record<string, number>;
}

interface VerificationStatus {
  status: "idle" | "running" | "stopping" | "cancelled" | "done" | "failed";
  started_at: number | null;
  finished_at: number | null;
  total?: number;
  done?: number;
  remaining?: number;
  progress_pct?: number;
  items_per_min?: number;
  eta_seconds?: number | null;
  eta_at?: number | null;
  pending_review: number;
  auto_resolved?: number;
  run_mode?: "all" | "hitl_only";
  reset_pending?: boolean;
  stop_requested?: boolean;
  last_error: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Entity editing constants
// ---------------------------------------------------------------------------

interface LabelEntity {
  text: string;
  label: string;
  start: number;
  end: number;
  assertion?: string;
  confidence?: number;
}

const VALID_ENTITY_LABELS = [
  "disorder",
  "finding",
  "procedure",
  "observable_entity",
  "qualifier_value",
  "substance",
  "medicinal_product",
  "clinical_drug",
  "situation",
  "event",
  "body_structure",
  "tumor_staging",
  "assessment_scale",
  "staging_scale",
  "regime_therapy",
  "record_artifact",
  "physical_object",
  "organism",
  "morphologic_abnormality",
  "occupation",
  "attribute",
  "environment",
  "product",
  "X_TEMPORAL",
  "X_DOSAGE",
  "X_FREQUENCY",
  "X_ROUTE",
] as const;

const SOURCE_LABELS: Record<string, string> = {
  hitl_approval: "HITL",
  coding_correction: "Correction",
  anchor_mining: "Mined",
  seed: "Seed",
};

const SOURCE_COLORS: Record<string, "primary" | "secondary" | "success" | "warning"> = {
  hitl_approval: "success",
  coding_correction: "primary",
  anchor_mining: "secondary",
  seed: "warning",
};

const ACTIVE_STATUSES = new Set(["queued", "running", "evaluating", "uploading"]);

function fmtElapsed(s: number | null) {
  if (s == null) return "";
  if (s < 60) return `${Math.round(s)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

function EntityPills({ entitiesJson, showAll = false }: { entitiesJson: string; showAll?: boolean }) {
  let entities: { text: string; label: string }[] = [];
  try { entities = JSON.parse(entitiesJson); } catch { /* ignore */ }
  if (!entities.length) return <Typography variant="caption" color="text.disabled">—</Typography>;
  const visible = showAll ? entities : entities.slice(0, 5);
  return (
    <Stack direction="row" flexWrap="wrap" gap={0.5}>
      {visible.map((e, i) => (
        <Chip key={i} label={`${e.text} · ${e.label}`} size="small" variant="outlined" sx={{ fontSize: 11 }} />
      ))}
      {!showAll && entities.length > 5 && <Chip label={`+${entities.length - 5} more`} size="small" />}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// How this tab works - stages for the flow diagram
// ---------------------------------------------------------------------------

const TRAINING_STAGES: TabStage[] = [
  {
    id: "td1", num: 1,
    label: "Collect Reviews",
    tooltip: "All the notes that human reviewers have checked and approved are gathered together. These become the teaching examples for the AI.",
    detailIn: "Approved human-reviewed labels from the Label Review and other queues",
    detailOut: "A set of correct examples ready to learn from",
    branches: [
      {
        label: "Not enough examples",
        description: "Training cannot start until there are at least 50 approved examples. Check back after more reviews are done",
      },
    ],
  },
  {
    id: "td2", num: 2,
    label: "Check Examples",
    tooltip: "Each example is inspected and tidied. You can edit or remove examples that look wrong before training starts.",
    detailIn: "The collected training examples",
    detailOut: "A clean, checked set of teaching examples",
    branches: [
      {
        label: "Exclude an example",
        description: "You can remove an example from training if you think it would teach the AI the wrong thing",
      },
    ],
  },
  {
    id: "td3", num: 3,
    label: "AI Learns",
    tooltip: "The AI studies thousands of correct examples so it can learn to spot medical words on its own.",
    detailIn: "The clean training examples",
    detailOut: "A freshly trained AI model",
    branches: [
      {
        label: "Hardware retry",
        description: "If training fails on a fast machine, we try again on slower hardware -- up to 4 attempts",
      },
    ],
  },
  {
    id: "td4", num: 4,
    label: "AI Tested",
    tooltip: "We give the AI a quiz using examples it has never seen before to check it learned well enough.",
    detailIn: "The trained AI and a set of test examples",
    detailOut: "A test score -- it must reach at least 80% precision and 75% recall to pass",
    branches: [
      {
        label: "Failed the test",
        description: "If the AI does not score high enough, training stops here and the new model is not used",
      },
    ],
  },
  {
    id: "td5", num: 5,
    label: "New AI Ready",
    tooltip: "If the AI passes, it is saved and registered. Head to the Model Deployment tab to promote it to live.",
    detailIn: "The tested and approved AI model",
    detailOut: "A new model version ready to be deployed",
  },
];

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export default function TrainingDataPanel() {
  const [stats, setStats] = useState<LabelStats | null>(null);
  const [labels, setLabels] = useState<TrainingLabel[]>([]);
  const [labelTotal, setLabelTotal] = useState(0);
  const [labelPage, setLabelPage] = useState(1);
  const [filterSource, setFilterSource] = useState<string | null>(null);
  const [filterInclude, setFilterInclude] = useState<boolean | null>(null);
  const [searchText, setSearchText] = useState("");
  const [loadingLabels, setLoadingLabels] = useState(false);

  const [selectedLabel, setSelectedLabel] = useState<TrainingLabel | null>(null);
  const [editingEntities, setEditingEntities] = useState(false);
  const [draftEntities, setDraftEntities] = useState<LabelEntity[]>([]);
  const [savingEntities, setSavingEntities] = useState(false);

  const [excludeTarget, setExcludeTarget] = useState<string | null>(null);
  const [excludeReason, setExcludeReason] = useState("");
  const [excludeBusy, setExcludeBusy] = useState(false);

  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [startJobOpen, setStartJobOpen] = useState(false);
  const [jobNotes, setJobNotes] = useState("");
  const [startingJob, setStartingJob] = useState(false);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus | null>(null);
  const [startingVerification, setStartingVerification] = useState(false);

  const PAGE_SIZE = 30;
  const heroLogRef = useRef<HTMLDivElement | null>(null);
  const historyLogRef = useRef<HTMLDivElement | null>(null);
  const [pollingPaused, setPollingPaused] = useState(false);
  const pollingPausedRef = useRef(false);
  const jobsRef = useRef<TrainingJob[]>([]);

  // Auto-scroll both log boxes to bottom whenever log lines change
  useEffect(() => {
    heroLogRef.current?.scrollTo({ top: heroLogRef.current.scrollHeight });
  }, [jobs]);
  useEffect(() => {
    historyLogRef.current?.scrollTo({ top: historyLogRef.current.scrollHeight });
  }, [jobs]);

  // ---------- fetching ----------

  const fetchStats = useCallback(async () => {
    try {
      const data = await jsonFetch<LabelStats>("/api/training/labels/stats");
      setStats(data);
    } catch { /* silently swallow on background poll */ }
  }, []);

  const fetchLabels = useCallback(async () => {
    setLoadingLabels(true);
    try {
      const params = new URLSearchParams({ page: String(labelPage), page_size: String(PAGE_SIZE) });
      if (filterSource) params.set("source", filterSource);
      if (filterInclude !== null) params.set("include", String(filterInclude));
      if (searchText) params.set("search", searchText);
      const data = await jsonFetch<{ labels: TrainingLabel[]; total: number }>(`/api/training/labels?${params}`);
      setLabels(data.labels);
      setLabelTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load labels");
    } finally {
      setLoadingLabels(false);
    }
  }, [labelPage, filterSource, filterInclude, searchText]);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await jsonFetch<{ jobs: TrainingJob[] }>("/api/training-worker/jobs");
      setJobs(data.jobs);
    } catch { /* training worker may be offline */ }
  }, []);

  const fetchPreview = useCallback(async () => {
    try {
      const data = await jsonFetch<ExportPreview>("/api/training/export-preview", { method: "POST" });
      setPreview(data);
    } catch { /* silently swallow */ }
  }, []);

  const fetchVerificationStatus = useCallback(async () => {
    try {
      const data = await jsonFetch<VerificationStatus>("/api/training/labels/verify-all/status");
      setVerificationStatus(data);
    } catch { /* silently swallow */ }
  }, []);

  useEffect(() => { fetchStats(); fetchJobs(); fetchPreview(); fetchVerificationStatus(); }, [fetchStats, fetchJobs, fetchPreview, fetchVerificationStatus]);
  useEffect(() => { fetchLabels(); }, [fetchLabels]);

  // Keep verifier progress reactive without SSE: poll status while running/stopping.
  useEffect(() => {
    const isActive =
      verificationStatus?.status === "running" ||
      verificationStatus?.status === "stopping";
    if (!isActive) return;
    const id = setInterval(() => {
      fetchVerificationStatus();
    }, 5000);
    return () => clearInterval(id);
  }, [verificationStatus?.status, fetchVerificationStatus]);

  // Keep refs in sync so the polling interval can read them without being recreated
  useEffect(() => { jobsRef.current = jobs; }, [jobs]);
  useEffect(() => { pollingPausedRef.current = pollingPaused; }, [pollingPaused]);

  // Single stable interval (12 s). Each tick checks refs before firing.
  // Stops itself when no active job and jobs exist (all finished).
  useEffect(() => {
    const id = setInterval(() => {
      if (pollingPausedRef.current) return;
      const current = jobsRef.current;
      const hasActive = current.some((j) => ACTIVE_STATUSES.has(j.status));
      // Don't poll if all jobs are finished
      if (current.length > 0 && !hasActive) return;
      fetchJobs();
      fetchStats();
    }, 12000);
    return () => clearInterval(id);
  }, [fetchJobs, fetchStats]); // stable — never recreated

  // ---------- actions ----------

  const handleExclude = async () => {
    if (!excludeTarget || !excludeReason.trim()) return;
    setExcludeBusy(true);
    try {
      await jsonFetch(`/api/training/labels/${excludeTarget}/exclude`, {
        method: "POST",
        body: JSON.stringify({ reason: excludeReason }),
      });
      setExcludeTarget(null);
      setExcludeReason("");
      fetchStats();
      fetchLabels();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to exclude");
    } finally {
      setExcludeBusy(false);
    }
  };

  const handleSaveEntities = async () => {
    if (!selectedLabel) return;
    setSavingEntities(true);
    try {
      await jsonFetch(`/api/training/labels/${selectedLabel.label_id}/entities`, {
        method: "PATCH",
        body: JSON.stringify({ entities: draftEntities }),
      });
      const updatedEntitiesJson = JSON.stringify(draftEntities);
      setSelectedLabel({ ...selectedLabel, entities_json: updatedEntitiesJson });
      setLabels((prev) =>
        prev.map((l) =>
          l.label_id === selectedLabel.label_id
            ? { ...l, entities_json: updatedEntitiesJson }
            : l
        )
      );
      setEditingEntities(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save entities");
    } finally {
      setSavingEntities(false);
    }
  };

  const handleInclude = async (id: string) => {
    try {
      await jsonFetch(`/api/training/labels/${id}/include`, { method: "POST" });
      fetchStats();
      fetchLabels();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to re-include");
    }
  };

  const handleStartJob = async () => {
    setStartingJob(true);
    try {
      await jsonFetch<{ job_id: string }>(
        "/api/training-worker/jobs",
        { method: "POST", body: JSON.stringify({ notes: jobNotes, triggered_by: "ui" }) }
      );
      setStartJobOpen(false);
      setJobNotes("");
      fetchJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start training");
    } finally {
      setStartingJob(false);
    }
  };

  const handleVerifyLabels = async (mode: "all" | "hitl_only" | "resume", resetPending = false) => {
    setStartingVerification(true);
    try {
      const apiMode = mode === "resume" ? "hitl_only" : mode;
      await jsonFetch<{ status: string; message: string }>("/api/training/labels/verify-all", {
        method: "POST",
        body: JSON.stringify({ mode: apiMode, reset_pending: resetPending }),
      });
      fetchVerificationStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start label verification");
    } finally {
      setStartingVerification(false);
    }
  };

  const handleStopVerification = async () => {
    try {
      await jsonFetch<{ status: string; message: string }>("/api/training/labels/verify-all/cancel", {
        method: "POST",
      });
      fetchVerificationStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop label verification");
    }
  };

  const totalPages = Math.max(1, Math.ceil(labelTotal / PAGE_SIZE));
  const activeJob = jobs.find((j) => ACTIVE_STATUSES.has(j.status));
  const lastJob = !activeJob ? jobs[0] : undefined;
  const verificationRunning =
    verificationStatus?.status === "running" ||
    verificationStatus?.status === "stopping" ||
    startingVerification;
  const verificationFinishedAt = verificationStatus?.finished_at
    ? new Date(verificationStatus.finished_at * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" })
    : null;

  // ---------- render ----------

  return (
    <Box sx={{ maxWidth: 900, mx: "auto", px: 3, py: 3 }}>

      {/* Page title */}
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>Model training</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Review what's in the training set, then start a run to update the NER model.
      </Typography>

      {/* How this works */}
      <Accordion variant="outlined" disableGutters sx={{ mb: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            How this tab works
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0 }}>
          <TabFlowDiagram
            stages={TRAINING_STAGES}
            color="#7C3AED"
            lightColor="#EDE9FE"
            trackLabel="Training Data"
          />
        </AccordionDetails>
      </Accordion>

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>{error}</Alert>
      )}

      {/* ── Hero: current state ── */}
      <Paper
        variant="outlined"
        sx={{
          p: 3,
          mb: 3,
          borderRadius: 2,
          borderColor: activeJob ? "primary.main"
            : lastJob?.status === "failed" ? "error.light"
            : lastJob?.status === "done" ? "success.light"
            : "divider",
          borderWidth: activeJob ? 2 : 1,
        }}
      >
        {/* Active job */}
        {activeJob && (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <HourglassTopIcon color="primary" />
              <Box flex={1}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Training in progress</Typography>
                <Typography variant="body2" color="text.secondary">
                  Step: {activeJob.phase || "starting up"}
                  {activeJob.elapsed_s != null && ` · ${fmtElapsed(activeJob.elapsed_s)} elapsed`}
                </Typography>
              </Box>
            </Stack>
            <LinearProgress sx={{ borderRadius: 1 }} />
            {activeJob.log_lines?.length > 0 && (
              <Box ref={heroLogRef} sx={{ background: "#0f172a", color: "#86efac", fontFamily: "monospace", fontSize: 11.5, p: 1.5, borderRadius: 1, height: 200, overflowY: "auto" }}>
                {activeJob.log_lines.map((l, i) => <div key={i}>{l}</div>)}
              </Box>
            )}
          </Stack>
        )}

        {/* Last job failed */}
        {!activeJob && lastJob?.status === "failed" && (
          <Stack direction="row" spacing={1.5} alignItems="flex-start">
            <ErrorOutlineIcon color="error" sx={{ mt: 0.3 }} />
            <Box flex={1}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Last run failed</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                {lastJob.error || "An error occurred during training."}
                {lastJob.elapsed_s != null && ` · ran for ${fmtElapsed(lastJob.elapsed_s)}`}
              </Typography>
              <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={() => setStartJobOpen(true)}>
                Try again
              </Button>
              <Button size="small" sx={{ ml: 1 }} onClick={() => setExpandedJob(expandedJob === lastJob.job_id ? null : lastJob.job_id)}>
                {expandedJob === lastJob.job_id ? "Hide log" : "Show log"}
              </Button>
              <Collapse in={expandedJob === lastJob.job_id}>
                <Box sx={{ mt: 1.5, background: "#0f172a", color: "#fca5a5", fontFamily: "monospace", fontSize: 11, p: 1.5, borderRadius: 1, maxHeight: 160, overflowY: "auto" }}>
                  {(lastJob.log_lines ?? []).map((l, i) => <div key={i}>{l}</div>)}
                </Box>
              </Collapse>
            </Box>
          </Stack>
        )}

        {/* Last job done */}
        {!activeJob && lastJob?.status === "done" && (
          <Stack direction="row" spacing={1.5} alignItems="center">
            <CheckCircleIcon color="success" />
            <Box flex={1}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Training complete{lastJob.model_version ? ` — version ${lastJob.model_version}` : ""}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Go to the <strong>Model Deployment</strong> tab to validate and promote.
                {lastJob.elapsed_s != null && ` · took ${fmtElapsed(lastJob.elapsed_s)}`}
              </Typography>
            </Box>
            <Button variant="outlined" startIcon={<PlayArrowIcon />} onClick={() => setStartJobOpen(true)}>
              New run
            </Button>
          </Stack>
        )}

        {/* No jobs yet */}
        {!activeJob && !lastJob && (
          <Stack direction="row" spacing={2} alignItems="center">
            <Box flex={1}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                {preview?.exportable_label_count.toLocaleString() ?? stats?.included.toLocaleString() ?? "…"} records ready
              </Typography>
              <Typography variant="body2" color="text.secondary">
                No training runs yet. Start one to build the NER model.
              </Typography>
            </Box>
            <Button
              variant="contained"
              size="large"
              startIcon={<PlayArrowIcon />}
              disabled={!preview?.ready_to_train}
              onClick={() => setStartJobOpen(true)}
            >
              Start training
            </Button>
          </Stack>
        )}
      </Paper>

      {/* Start button when there's a previous job but no active one */}
      {!activeJob && lastJob && (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 3 }}>
          <Typography variant="body2" color="text.secondary">
            {(preview?.exportable_label_count ?? stats?.included ?? 0).toLocaleString()} records included ·{" "}
            {(stats?.excluded ?? 0).toLocaleString()} excluded
          </Typography>
          <Box flex={1} />
          <Button
            variant="contained"
            startIcon={<PlayArrowIcon />}
            disabled={!preview?.ready_to_train}
            onClick={() => setStartJobOpen(true)}
          >
            Start training
          </Button>
          <IconButton size="small" onClick={() => { fetchJobs(); fetchStats(); fetchPreview(); }}>
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Stack>
      )}

      {/* ── Run history ── */}
      {jobs.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Typography variant="subtitle2" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: 11, flex: 1 }}>
              Run history
            </Typography>
            <Tooltip title={pollingPaused ? "Resume live updates" : "Pause live updates"}>
              <IconButton size="small" onClick={() => setPollingPaused((p) => !p)}>
                {pollingPaused
                  ? <PlayCircleOutlineIcon fontSize="small" color="success" />
                  : <PauseIcon fontSize="small" color="action" />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Refresh now">
              <IconButton size="small" onClick={() => { fetchJobs(); fetchStats(); }}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
          <Stack spacing={1} sx={{ mb: 3 }}>
            {jobs.map((job) => {
              const isActive = ACTIVE_STATUSES.has(job.status);
              // Don't expand active jobs in history — the hero card already shows progress
              const isExpanded = !isActive && expandedJob === job.job_id;
              return (
                <Paper key={job.job_id} variant="outlined" sx={{ p: 1.5, borderRadius: 1.5 }}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Chip
                      label={job.status}
                      color={job.status === "done" ? "success" : job.status === "failed" ? "error" : job.status === "running" || isActive ? "primary" : "default"}
                      size="small"
                      sx={{ minWidth: 70, fontWeight: 600 }}
                    />
                    <Typography variant="body2" sx={{ flex: 1 }}>
                      {job.model_version ? `v${job.model_version}` : isActive ? (job.phase || "running…") : "—"}
                    </Typography>
                    {job.elapsed_s != null && (
                      <Typography variant="caption" color="text.disabled">{fmtElapsed(job.elapsed_s)}</Typography>
                    )}
                    <Typography variant="caption" color="text.disabled">
                      {new Date(job.created_at * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                    </Typography>
                    <IconButton size="small" onClick={() => setExpandedJob(isExpanded ? null : job.job_id)}>
                      {isExpanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                    </IconButton>
                  </Stack>

                  {isActive && <LinearProgress sx={{ mt: 1, borderRadius: 1 }} />}

                  <Collapse in={isExpanded}>
                    <Box sx={{ mt: 1.5 }}>
                      {/* Metrics */}
                      {job.metrics && (job.metrics as any).ner && (() => {
                        const m = (job.metrics as any).ner;
                        return (
                          <Stack direction="row" spacing={2} sx={{ mb: 1.5 }}>
                            <Typography variant="caption">Precision <strong>{m.precision}</strong></Typography>
                            <Typography variant="caption">Recall <strong>{m.recall}</strong></Typography>
                            <Typography variant="caption">F1 <strong>{m.f1}</strong></Typography>
                            <Chip label={m.passed_gates ? "Gates passed" : "Gates failed"} color={m.passed_gates ? "success" : "error"} size="small" />
                          </Stack>
                        );
                      })()}
                      {/* Log */}
                      <Box ref={historyLogRef} sx={{ background: "#0f172a", color: job.status === "failed" ? "#fca5a5" : "#86efac", fontFamily: "monospace", fontSize: 11.5, p: 1.5, borderRadius: 1, height: 200, overflowY: "auto" }}>
                        {(job.log_lines ?? []).length === 0
                          ? <span style={{ opacity: 0.5 }}>No log output yet…</span>
                          : (job.log_lines ?? []).map((l, i) => <div key={i}>{l}</div>)}
                      </Box>
                    </Box>
                  </Collapse>
                </Paper>
              );
            })}
          </Stack>
        </>
      )}

      {/* ── Label library (collapsed) ── */}
      <Accordion disableGutters variant="outlined" sx={{ borderRadius: "8px !important" }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: 2 }}>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ width: "100%" }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Label library</Typography>
            {labelTotal > 0 && (
              <Chip label={`${labelTotal.toLocaleString()} records`} size="small" variant="outlined" />
            )}
            {(stats?.excluded ?? 0) > 0 && (
              <Chip label={`${stats!.excluded} excluded`} size="small" color="warning" variant="outlined" />
            )}
            {verificationStatus?.pending_review ? (
              <Chip
                label={`${verificationStatus.pending_review} HITL pending`}
                size="small"
                color="warning"
                variant="outlined"
              />
            ) : null}
            {(verificationStatus?.auto_resolved ?? 0) > 0 ? (
              <Chip
                label={`${verificationStatus?.auto_resolved ?? 0} auto-resolved`}
                size="small"
                color="success"
                variant="outlined"
              />
            ) : null}
            {verificationRunning ? (
              <Chip label="Verification running" size="small" color="primary" />
            ) : verificationFinishedAt ? (
              <Chip label={`Last verified ${verificationFinishedAt}`} size="small" variant="outlined" />
            ) : null}
          </Stack>
        </AccordionSummary>
        <AccordionDetails sx={{ p: 0 }}>
          {/* Filters */}
          <Stack direction="row" spacing={1} sx={{ px: 2, py: 1.5 }} flexWrap="wrap" alignItems="center">
            <TextField
              size="small"
              placeholder="Search…"
              value={searchText}
              onChange={(e) => { setSearchText(e.target.value); setLabelPage(1); }}
              sx={{ width: 200 }}
            />
            <ToggleButtonGroup size="small" exclusive value={filterSource ?? ""} onChange={(_, v) => { setFilterSource(v || null); setLabelPage(1); }}>
              <ToggleButton value="">All</ToggleButton>
              <ToggleButton value="hitl_approval">HITL</ToggleButton>
              <ToggleButton value="coding_correction">Corrections</ToggleButton>
              <ToggleButton value="anchor_mining">Mined</ToggleButton>
              <ToggleButton value="seed">Seed</ToggleButton>
            </ToggleButtonGroup>
            <ToggleButtonGroup size="small" exclusive value={filterInclude === null ? "" : String(filterInclude)} onChange={(_, v) => { setFilterInclude(v === "" ? null : v === "true"); setLabelPage(1); }}>
              <ToggleButton value="">All</ToggleButton>
              <ToggleButton value="true">Included</ToggleButton>
              <ToggleButton value="false">Excluded</ToggleButton>
            </ToggleButtonGroup>
            <IconButton size="small" onClick={() => { fetchLabels(); fetchVerificationStatus(); }}>
              <RefreshIcon fontSize="small" />
            </IconButton>
            <Box flex={1} />
            <Button
              size="small"
              variant="outlined"
              disabled={verificationRunning}
              onClick={() => handleVerifyLabels("all", false)}
            >
              {startingVerification ? "Starting..." : "Verify labels"}
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="warning"
              disabled={verificationRunning}
              onClick={() => handleVerifyLabels("all", true)}
            >
              Reset + reverify all
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="secondary"
              disabled={verificationRunning}
              onClick={() => handleVerifyLabels("hitl_only", false)}
            >
              Reverify HITL only
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={verificationRunning}
              onClick={() => handleVerifyLabels("resume", false)}
            >
              Resume
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={!verificationRunning}
              onClick={handleStopVerification}
            >
              Stop verify
            </Button>
          </Stack>

          {verificationRunning && (
            <Stack
              direction="row"
              spacing={1}
              sx={{ px: 2, pb: 1.5, flexWrap: "wrap" }}
              alignItems="center"
            >
              <Chip
                label={`${verificationStatus?.done ?? 0}/${verificationStatus?.total ?? 0} labels (${(verificationStatus?.progress_pct ?? 0).toFixed(1)}%)`}
                size="small"
                color="primary"
                variant="outlined"
              />
              <Chip
                label={`${verificationStatus?.remaining ?? 0} labels remaining`}
                size="small"
                color="primary"
                variant="outlined"
              />
              {typeof verificationStatus?.items_per_min === "number" && verificationStatus.items_per_min > 0 ? (
                <Chip
                  label={`${verificationStatus.items_per_min.toFixed(1)} labels/min`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              ) : null}
              {typeof verificationStatus?.eta_seconds === "number" ? (
                <Chip
                  label={`ETA ${fmtElapsed(verificationStatus.eta_seconds)}`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              ) : null}
              {typeof verificationStatus?.eta_at === "number" ? (
                <Chip
                  label={`ETA at ${new Date(verificationStatus.eta_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              ) : null}
            </Stack>
          )}

          {verificationRunning && typeof verificationStatus?.progress_pct === "number" ? (
            <LinearProgress
              variant="determinate"
              value={Math.max(0, Math.min(100, verificationStatus.progress_pct))}
              sx={{ mx: 2, mb: 1.5, borderRadius: 1 }}
            />
          ) : null}

          {/* Table */}
          <TableContainer sx={{ borderTop: "1px solid", borderColor: "divider" }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ background: "action.hover" }}>
                  <TableCell sx={{ fontWeight: 600 }}>Text</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Entities</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Source</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {loadingLabels && (
                  <TableRow><TableCell colSpan={5} align="center"><CircularProgress size={18} /></TableCell></TableRow>
                )}
                {!loadingLabels && labels.length === 0 && (
                  <TableRow><TableCell colSpan={5} align="center"><Typography variant="caption" color="text.disabled">No records found</Typography></TableCell></TableRow>
                )}
                {labels.map((label) => (
                  <TableRow
                    key={label.label_id}
                    hover
                    onClick={() => setSelectedLabel(label)}
                    sx={{
                      opacity: label.include ? 1 : 0.55,
                      cursor: "pointer",
                      "&.Mui-selected, &.Mui-selected:hover": { bgcolor: "action.selected" },
                    }}
                    selected={selectedLabel?.label_id === label.label_id}
                  >
                    <TableCell sx={{ maxWidth: 260 }}>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                        {label.text.slice(0, 100)}{label.text.length > 100 ? "…" : ""}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ minWidth: 180 }}>
                      <EntityPills entitiesJson={label.entities_json} />
                    </TableCell>
                    <TableCell>
                      <Chip label={SOURCE_LABELS[label.source] ?? label.source} color={SOURCE_COLORS[label.source] ?? "default"} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell>
                      {label.include
                        ? <Chip label="In" color="success" size="small" />
                        : <Tooltip title={label.excluded_reason ?? ""}><Chip label="Out" color="default" size="small" /></Tooltip>}
                    </TableCell>
                    <TableCell align="right">
                      {label.include
                        ? <Tooltip title="Remove from training"><IconButton size="small" onClick={(e) => { e.stopPropagation(); setExcludeTarget(label.label_id); }}><BlockIcon fontSize="small" color="error" /></IconButton></Tooltip>
                        : <Tooltip title="Add back to training"><IconButton size="small" onClick={(e) => { e.stopPropagation(); handleInclude(label.label_id); }}><CheckCircleOutlineIcon fontSize="small" color="success" /></IconButton></Tooltip>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Pagination */}
          <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 2, py: 1.5 }}>
            <Button size="small" disabled={labelPage <= 1} onClick={() => setLabelPage((p) => p - 1)}>← Prev</Button>
            <Typography variant="caption" color="text.secondary">
              {labelPage} / {totalPages} ({labelTotal.toLocaleString()} records)
            </Typography>
            <Button size="small" disabled={labelPage >= totalPages} onClick={() => setLabelPage((p) => p + 1)}>Next →</Button>
          </Stack>
        </AccordionDetails>
      </Accordion>

      {/* ── Label detail drawer ── */}
      <Drawer
        anchor="right"
        open={!!selectedLabel}
        onClose={() => { setSelectedLabel(null); setEditingEntities(false); }}
        PaperProps={{ sx: { width: { xs: "100%", sm: 500 }, display: "flex", flexDirection: "column" } }}
      >
        {selectedLabel && (
          <>
            {/* Header */}
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              sx={{ px: 2.5, py: 1.75, borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}
            >
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>Label detail</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                  {selectedLabel.label_id.slice(0, 20)}…
                </Typography>
              </Box>
              <IconButton size="small" onClick={() => { setSelectedLabel(null); setEditingEntities(false); }} edge="end">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>

            {/* Status & action bar */}
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ px: 2.5, py: 1.25, borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}
            >
              <Chip
                label={SOURCE_LABELS[selectedLabel.source] ?? selectedLabel.source}
                color={SOURCE_COLORS[selectedLabel.source] ?? "default"}
                size="small"
                variant="outlined"
              />
              {selectedLabel.include
                ? <Chip label="Included" color="success" size="small" />
                : <Chip label="Excluded" color="default" size="small" />}
              <Box flex={1} />
              {selectedLabel.include
                ? (
                  <Button
                    size="small"
                    color="error"
                    startIcon={<BlockIcon />}
                    onClick={() => {
                      const id = selectedLabel.label_id;
                      setSelectedLabel(null);
                      setExcludeTarget(id);
                    }}
                  >
                    Exclude
                  </Button>
                ) : (
                  <Button
                    size="small"
                    color="success"
                    startIcon={<CheckCircleOutlineIcon />}
                    onClick={() => {
                      handleInclude(selectedLabel.label_id);
                      setSelectedLabel(null);
                    }}
                  >
                    Re-include
                  </Button>
                )}
            </Stack>

            {/* Scrollable body */}
            <Box sx={{ overflowY: "auto", flex: 1 }}>

              {/* Encounter text */}
              <Box sx={{ px: 2.5, pt: 2, pb: 2.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600, fontSize: 10.5 }}>
                  Encounter text
                </Typography>
                <Box
                  sx={{
                    mt: 1,
                    bgcolor: (t) => t.palette.mode === "dark" ? "#1e293b" : "#f8fafc",
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    p: 1.5,
                    fontFamily: "monospace",
                    fontSize: 12.5,
                    lineHeight: 1.85,
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  {selectedLabel.text}
                </Box>
              </Box>

              <Divider />

              {/* Entities */}
              <Box sx={{ px: 2.5, py: 2 }}>
                <Stack direction="row" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600, fontSize: 10.5, flex: 1 }}>
                    Entities
                  </Typography>
                  {!editingEntities ? (
                    <Tooltip title="Edit entities">
                      <IconButton
                        size="small"
                        onClick={() => {
                          let parsed: LabelEntity[] = [];
                          try { parsed = JSON.parse(selectedLabel.entities_json); } catch { /* ignore */ }
                          setDraftEntities(parsed);
                          setEditingEntities(true);
                        }}
                      >
                        <EditOutlinedIcon sx={{ fontSize: 15 }} />
                      </IconButton>
                    </Tooltip>
                  ) : (
                    <Stack direction="row" spacing={0.5}>
                      <Button
                        size="small"
                        onClick={() => setEditingEntities(false)}
                        disabled={savingEntities}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="small"
                        variant="contained"
                        onClick={handleSaveEntities}
                        disabled={savingEntities || draftEntities.length === 0}
                        startIcon={savingEntities ? <CircularProgress size={12} /> : undefined}
                      >
                        {savingEntities ? "Saving…" : "Save"}
                      </Button>
                    </Stack>
                  )}
                </Stack>

                {!editingEntities ? (
                  <EntityPills entitiesJson={selectedLabel.entities_json} showAll />
                ) : (
                  <Stack spacing={1}>
                    {draftEntities.map((ent, idx) => (
                      <Stack key={idx} direction="row" spacing={1} alignItems="center">
                        <TextField
                          size="small"
                          value={ent.text}
                          onChange={(e) => {
                            const newText = e.target.value;
                            setDraftEntities((prev) => {
                              const next = [...prev];
                              const start = selectedLabel.text.indexOf(newText);
                              next[idx] = {
                                ...next[idx],
                                text: newText,
                                start: start >= 0 ? start : next[idx].start,
                                end: start >= 0 ? start + newText.length : next[idx].end,
                              };
                              return next;
                            });
                          }}
                          sx={{ flex: 1, "& input": { fontFamily: "monospace", fontSize: 12 } }}
                          placeholder="Entity span text"
                        />
                        <FormControl size="small" sx={{ minWidth: 160 }}>
                          <Select
                            value={ent.label}
                            onChange={(e) =>
                              setDraftEntities((prev) => {
                                const next = [...prev];
                                next[idx] = { ...next[idx], label: e.target.value };
                                return next;
                              })
                            }
                            sx={{ fontSize: 12 }}
                          >
                            {VALID_ENTITY_LABELS.map((l) => (
                              <MenuItem key={l} value={l} sx={{ fontSize: 12 }}>
                                {l}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                        <Tooltip title="Remove entity">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() =>
                              setDraftEntities((prev) => prev.filter((_, i) => i !== idx))
                            }
                          >
                            <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    ))}
                    <Button
                      size="small"
                      startIcon={<AddIcon />}
                      onClick={() =>
                        setDraftEntities((prev) => [
                          ...prev,
                          { text: "", label: "finding", start: 0, end: 0 },
                        ])
                      }
                      sx={{ alignSelf: "flex-start", mt: 0.5 }}
                    >
                      Add entity
                    </Button>
                  </Stack>
                )}
              </Box>

              <Divider />

              {/* Metadata */}
              <Box sx={{ px: 2.5, py: 2 }}>
                <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600, fontSize: 10.5 }}>
                  Metadata
                </Typography>
                <Stack spacing={1.25} sx={{ mt: 1.5 }}>
                  <Stack direction="row" spacing={1.5}>
                    <Typography variant="caption" color="text.secondary" sx={{ minWidth: 130, flexShrink: 0 }}>Quality score</Typography>
                    <Typography variant="caption">
                      {selectedLabel.quality_score != null ? selectedLabel.quality_score.toFixed(3) : "—"}
                    </Typography>
                  </Stack>
                  <Stack direction="row" spacing={1.5}>
                    <Typography variant="caption" color="text.secondary" sx={{ minWidth: 130, flexShrink: 0 }}>Last updated</Typography>
                    <Typography variant="caption">
                      {new Date(selectedLabel.updated_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
                    </Typography>
                  </Stack>
                  <Stack direction="row" spacing={1.5} alignItems="flex-start">
                    <Typography variant="caption" color="text.secondary" sx={{ minWidth: 130, flexShrink: 0 }}>Encounter ID</Typography>
                    <Typography variant="caption" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                      {selectedLabel.encounter_id}
                    </Typography>
                  </Stack>
                  <Stack direction="row" spacing={1.5} alignItems="flex-start">
                    <Typography variant="caption" color="text.secondary" sx={{ minWidth: 130, flexShrink: 0 }}>Label ID</Typography>
                    <Typography variant="caption" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                      {selectedLabel.label_id}
                    </Typography>
                  </Stack>
                  {!selectedLabel.include && selectedLabel.excluded_reason && (
                    <Stack direction="row" spacing={1.5} alignItems="flex-start">
                      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 130, flexShrink: 0 }}>Excluded reason</Typography>
                      <Typography variant="caption" color="warning.main">
                        {selectedLabel.excluded_reason}
                      </Typography>
                    </Stack>
                  )}
                </Stack>
              </Box>
            </Box>
          </>
        )}
      </Drawer>

      {/* ── Exclude dialog ── */}
      <Dialog open={!!excludeTarget} onClose={() => setExcludeTarget(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Remove this record from training?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            The record won't be used in future training runs. You can add it back at any time.
          </Typography>
          <TextField
            fullWidth autoFocus
            label="Reason"
            placeholder="e.g. wrong entity, contains identifiable information…"
            value={excludeReason}
            onChange={(e) => setExcludeReason(e.target.value)}
            multiline rows={2}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExcludeTarget(null)}>Cancel</Button>
          <Button onClick={handleExclude} disabled={!excludeReason.trim() || excludeBusy} color="error" variant="contained">
            {excludeBusy ? "Removing…" : "Remove"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Start training dialog ── */}
      <Dialog open={startJobOpen} onClose={() => setStartJobOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Start a training run</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            This will train the NER model using{" "}
            <strong>{(preview?.exportable_label_count ?? 0).toLocaleString()} records</strong>.
            Training runs in the background — you can watch progress on this page.
          </Typography>
          <TextField
            fullWidth
            label="Notes (optional)"
            placeholder="e.g. added corrections for haemoptysis"
            value={jobNotes}
            onChange={(e) => setJobNotes(e.target.value)}
            multiline rows={2}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStartJobOpen(false)}>Cancel</Button>
          <Button
            onClick={handleStartJob}
            disabled={startingJob}
            variant="contained"
            startIcon={startingJob ? <CircularProgress size={14} /> : <PlayArrowIcon />}
          >
            {startingJob ? "Starting…" : "Start"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
