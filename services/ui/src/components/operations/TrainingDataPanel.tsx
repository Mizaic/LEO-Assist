"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
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
  IconButton,
  LinearProgress,
  Paper,
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
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import BlockIcon from "@mui/icons-material/Block";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

const SOURCE_COLORS: Record<string, "primary" | "secondary" | "success" | "warning"> = {
  hitl_approval: "success",
  coding_correction: "primary",
  anchor_mining: "secondary",
  seed: "warning",
};

const SOURCE_LABELS: Record<string, string> = {
  hitl_approval: "HITL approved",
  coding_correction: "Coding correction",
  anchor_mining: "Anchor mining",
  seed: "Seed",
};

const JOB_STATUS_COLORS: Record<string, "default" | "primary" | "warning" | "success" | "error"> = {
  queued: "default",
  running: "primary",
  evaluating: "warning",
  uploading: "warning",
  done: "success",
  failed: "error",
  cancelled: "default",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, minWidth: 120, textAlign: "center" }}>
      <Typography variant="h4" sx={{ fontWeight: 700 }}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      {sub && <Typography variant="caption" display="block" color="text.disabled">{sub}</Typography>}
    </Paper>
  );
}

function EntityPills({ entitiesJson }: { entitiesJson: string }) {
  let entities: { text: string; label: string }[] = [];
  try { entities = JSON.parse(entitiesJson); } catch { /* ignore */ }
  if (!entities.length) return <Typography variant="caption" color="text.disabled">no entities</Typography>;
  return (
    <Stack direction="row" flexWrap="wrap" gap={0.5}>
      {entities.slice(0, 6).map((e, i) => (
        <Chip key={i} label={`${e.text} [${e.label}]`} size="small" variant="outlined" />
      ))}
      {entities.length > 6 && <Chip label={`+${entities.length - 6}`} size="small" />}
    </Stack>
  );
}

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

  const [excludeTarget, setExcludeTarget] = useState<string | null>(null);
  const [excludeReason, setExcludeReason] = useState("");
  const [excludeBusy, setExcludeBusy] = useState(false);

  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [startJobOpen, setStartJobOpen] = useState(false);
  const [jobNotes, setJobNotes] = useState("");
  const [startingJob, setStartingJob] = useState(false);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  const PAGE_SIZE = 30;
  const esRef = useRef<EventSource | null>(null);

  // ------------------------------------------------------------------
  // Data fetching
  // ------------------------------------------------------------------

  const fetchStats = useCallback(async () => {
    try {
      const data = await jsonFetch<LabelStats>("/api/training/labels/stats");
      setStats(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load stats");
    }
  }, []);

  const fetchLabels = useCallback(async () => {
    setLoadingLabels(true);
    try {
      const params = new URLSearchParams({
        page: String(labelPage),
        page_size: String(PAGE_SIZE),
      });
      if (filterSource) params.set("source", filterSource);
      if (filterInclude !== null) params.set("include", String(filterInclude));
      if (searchText) params.set("search", searchText);
      const data = await jsonFetch<{ labels: TrainingLabel[]; total: number }>(
        `/api/training/labels?${params}`
      );
      setLabels(data.labels);
      setLabelTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load labels");
    } finally {
      setLoadingLabels(false);
    }
  }, [labelPage, filterSource, filterInclude, searchText]);

  const fetchJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      const data = await jsonFetch<{ jobs: TrainingJob[] }>("/api/training-worker/jobs");
      setJobs(data.jobs);
    } catch {
      // Training worker may not be running locally; suppress silently
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  const fetchPreview = useCallback(async () => {
    setLoadingPreview(true);
    try {
      const data = await jsonFetch<ExportPreview>("/api/training/export-preview", { method: "POST" });
      setPreview(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load preview");
    } finally {
      setLoadingPreview(false);
    }
  }, []);

  useEffect(() => { fetchStats(); fetchJobs(); fetchPreview(); }, [fetchStats, fetchJobs, fetchPreview]);
  useEffect(() => { fetchLabels(); }, [fetchLabels]);

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

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
      await fetchStats();
      await fetchLabels();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to exclude label");
    } finally {
      setExcludeBusy(false);
    }
  };

  const handleInclude = async (labelId: string) => {
    try {
      await jsonFetch(`/api/training/labels/${labelId}/include`, { method: "POST" });
      await fetchStats();
      await fetchLabels();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to re-include label");
    }
  };

  const handleStartJob = async () => {
    setStartingJob(true);
    try {
      const res = await jsonFetch<{ job_id: string; stream_path: string }>(
        "/api/training-worker/jobs",
        {
          method: "POST",
          body: JSON.stringify({ notes: jobNotes, triggered_by: "ui" }),
        }
      );
      setStartJobOpen(false);
      setJobNotes("");
      setExpandedJob(res.job_id);
      // Subscribe to SSE for this job
      const es = new EventSource(
        `${window.location.origin}/api/training-worker/progress/${res.job_id}`
      );
      esRef.current?.close();
      esRef.current = es;
      es.addEventListener("training_log", () => fetchJobs());
      es.addEventListener("training_done", () => { fetchJobs(); es.close(); });
      es.addEventListener("training_failed", () => { fetchJobs(); es.close(); });
      await fetchJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start training job");
    } finally {
      setStartingJob(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(labelTotal / PAGE_SIZE));

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <Box sx={{ maxWidth: 1200, mx: "auto", px: 3, py: 2 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
        Training Data
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Every approved candidate, HITL resolution, and manual correction is captured here.
        Include or exclude individual records, then trigger a training run to fine-tune the NER model.
      </Typography>

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* ---- Stats ---- */}
      <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ mb: 3 }}>
        <StatCard label="Total labels" value={stats?.total ?? "—"} />
        <StatCard label="Included" value={stats?.included ?? "—"} sub="used in training" />
        <StatCard label="Excluded" value={stats?.excluded ?? "—"} sub="soft-deleted" />
        <StatCard label="HITL approved" value={stats?.by_source.hitl_approval ?? "—"} />
        <StatCard label="Coding corrections" value={stats?.by_source.coding_correction ?? "—"} />
        <StatCard label="Anchor mining" value={stats?.by_source.anchor_mining ?? "—"} />
      </Stack>

      {/* ---- Training readiness ---- */}
      {preview && (
        <Paper variant="outlined" sx={{ p: 2, mb: 3, borderColor: preview.ready_to_train ? "success.main" : "warning.main" }}>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
            <Box>
              <Typography variant="subtitle2">
                {preview.ready_to_train
                  ? `Ready to train — ${preview.exportable_label_count} labels available`
                  : `Not ready — ${preview.exportable_label_count} / ${preview.min_required} labels required`}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Label types: {Object.entries(preview.by_label_type).map(([l, n]) => `${l}: ${n}`).join(" · ")}
              </Typography>
            </Box>
            <Box sx={{ ml: "auto" }}>
              <Button
                variant="contained"
                startIcon={<PlayArrowIcon />}
                disabled={!preview.ready_to_train}
                onClick={() => setStartJobOpen(true)}
              >
                Start training run
              </Button>
            </Box>
          </Stack>
        </Paper>
      )}

      {/* ---- Label library ---- */}
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
        Label Library
      </Typography>

      <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} flexWrap="wrap" alignItems="center">
        <TextField
          size="small"
          placeholder="Search text…"
          value={searchText}
          onChange={(e) => { setSearchText(e.target.value); setLabelPage(1); }}
          sx={{ width: 220 }}
        />
        <ToggleButtonGroup
          size="small"
          exclusive
          value={filterSource}
          onChange={(_, v) => { setFilterSource(v); setLabelPage(1); }}
        >
          <ToggleButton value="">All sources</ToggleButton>
          <ToggleButton value="hitl_approval">HITL</ToggleButton>
          <ToggleButton value="coding_correction">Correction</ToggleButton>
          <ToggleButton value="anchor_mining">Mined</ToggleButton>
          <ToggleButton value="seed">Seed</ToggleButton>
        </ToggleButtonGroup>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={filterInclude === null ? "" : String(filterInclude)}
          onChange={(_, v) => {
            setFilterInclude(v === "" ? null : v === "true");
            setLabelPage(1);
          }}
        >
          <ToggleButton value="">All</ToggleButton>
          <ToggleButton value="true">Included</ToggleButton>
          <ToggleButton value="false">Excluded</ToggleButton>
        </ToggleButtonGroup>
        <IconButton size="small" onClick={fetchLabels}><RefreshIcon fontSize="small" /></IconButton>
      </Stack>

      <TableContainer component={Paper} variant="outlined" sx={{ mb: 1 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Text</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Entities</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Source</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Quality</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {loadingLabels && (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <CircularProgress size={20} />
                </TableCell>
              </TableRow>
            )}
            {!loadingLabels && labels.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography variant="caption" color="text.secondary">No labels found</Typography>
                </TableCell>
              </TableRow>
            )}
            {labels.map((label) => (
              <TableRow
                key={label.label_id}
                sx={{ opacity: label.include ? 1 : 0.5 }}
              >
                <TableCell sx={{ maxWidth: 300 }}>
                  <Typography variant="caption" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                    {label.text.slice(0, 120)}{label.text.length > 120 ? "…" : ""}
                  </Typography>
                </TableCell>
                <TableCell sx={{ minWidth: 200 }}>
                  <EntityPills entitiesJson={label.entities_json} />
                </TableCell>
                <TableCell>
                  <Chip
                    label={SOURCE_LABELS[label.source] ?? label.source}
                    color={SOURCE_COLORS[label.source] ?? "default"}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="caption">
                    {typeof label.quality_score === "number"
                      ? `${Math.round(label.quality_score * 100)}%`
                      : "—"}
                  </Typography>
                </TableCell>
                <TableCell>
                  {label.include ? (
                    <Chip label="Included" color="success" size="small" />
                  ) : (
                    <Tooltip title={label.excluded_reason ?? ""}>
                      <Chip label="Excluded" color="error" size="small" />
                    </Tooltip>
                  )}
                </TableCell>
                <TableCell align="right">
                  {label.include ? (
                    <Tooltip title="Exclude from training">
                      <IconButton
                        size="small"
                        onClick={() => setExcludeTarget(label.label_id)}
                      >
                        <BlockIcon fontSize="small" color="error" />
                      </IconButton>
                    </Tooltip>
                  ) : (
                    <Tooltip title="Re-include in training">
                      <IconButton
                        size="small"
                        onClick={() => handleInclude(label.label_id)}
                      >
                        <CheckCircleOutlineIcon fontSize="small" color="success" />
                      </IconButton>
                    </Tooltip>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 4 }}>
        <Button size="small" disabled={labelPage <= 1} onClick={() => setLabelPage((p) => p - 1)}>
          Previous
        </Button>
        <Typography variant="caption">
          Page {labelPage} of {totalPages} ({labelTotal} labels)
        </Typography>
        <Button size="small" disabled={labelPage >= totalPages} onClick={() => setLabelPage((p) => p + 1)}>
          Next
        </Button>
      </Stack>

      <Divider sx={{ mb: 3 }} />

      {/* ---- Training jobs ---- */}
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          Training Jobs
        </Typography>
        <Button
          size="small"
          variant="contained"
          startIcon={<PlayArrowIcon />}
          disabled={!preview?.ready_to_train}
          onClick={() => setStartJobOpen(true)}
        >
          Start training run
        </Button>
        <IconButton size="small" onClick={fetchJobs}><RefreshIcon fontSize="small" /></IconButton>
      </Stack>

      {loadingJobs && <LinearProgress sx={{ mb: 2 }} />}

      {jobs.length === 0 && !loadingJobs && (
        <Alert severity="info" sx={{ mb: 2 }}>
          No training jobs yet. Click "Start training run" to fine-tune the NER model.
        </Alert>
      )}

      {jobs.map((job) => (
        <Paper key={job.job_id} variant="outlined" sx={{ mb: 1.5, p: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap">
            <Chip
              label={job.status}
              color={JOB_STATUS_COLORS[job.status] ?? "default"}
              size="small"
            />
            {job.phase && (
              <Typography variant="caption" color="text.secondary">
                Phase: {job.phase}
              </Typography>
            )}
            {job.model_version && (
              <Typography variant="caption">
                Version: <strong>{job.model_version}</strong>
              </Typography>
            )}
            {job.elapsed_s != null && (
              <Typography variant="caption" color="text.secondary">
                {job.elapsed_s}s
              </Typography>
            )}
            <Typography variant="caption" color="text.disabled" sx={{ ml: "auto" }}>
              {new Date(job.created_at * 1000).toLocaleString()}
            </Typography>
            <IconButton size="small" onClick={() => setExpandedJob(expandedJob === job.job_id ? null : job.job_id)}>
              {expandedJob === job.job_id ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
            </IconButton>
          </Stack>

          {job.status === "running" || job.status === "evaluating" || job.status === "uploading" ? (
            <LinearProgress sx={{ mt: 1 }} />
          ) : null}

          {job.error && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {job.error}
            </Alert>
          )}

          <Collapse in={expandedJob === job.job_id}>
            <Box sx={{ mt: 1.5 }}>
              {job.notes && (
                <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>
                  Notes: {job.notes}
                </Typography>
              )}
              {/* Metrics */}
              {job.metrics && (job.metrics as any).ner && (
                <Box sx={{ mb: 1 }}>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>Results</Typography>
                  {(() => {
                    const m = (job.metrics as any).ner;
                    return (
                      <Stack direction="row" spacing={2} sx={{ mt: 0.5 }}>
                        <Typography variant="caption">P: {m.precision}</Typography>
                        <Typography variant="caption">R: {m.recall}</Typography>
                        <Typography variant="caption">F1: {m.f1}</Typography>
                        <Chip
                          label={m.passed_gates ? "Gates passed" : "Gates failed"}
                          color={m.passed_gates ? "success" : "error"}
                          size="small"
                        />
                      </Stack>
                    );
                  })()}
                </Box>
              )}
              {/* Log */}
              <Box
                sx={{
                  background: "#111",
                  color: "#cfc",
                  fontFamily: "monospace",
                  fontSize: 11,
                  p: 1,
                  borderRadius: 1,
                  maxHeight: 200,
                  overflowY: "auto",
                }}
              >
                {(job.log_lines ?? []).map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
                {(!job.log_lines || job.log_lines.length === 0) && (
                  <Typography variant="caption" color="inherit" sx={{ opacity: 0.5 }}>
                    No log output yet…
                  </Typography>
                )}
              </Box>
              {job.model_version && (
                <Alert severity="success" sx={{ mt: 1 }}>
                  Version <strong>{job.model_version}</strong> registered —
                  go to the <strong>Model Deployment</strong> tab to validate and promote.
                </Alert>
              )}
            </Box>
          </Collapse>
        </Paper>
      ))}

      {/* ---- Exclude dialog ---- */}
      <Dialog open={!!excludeTarget} onClose={() => setExcludeTarget(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Exclude label from training</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            This record will be excluded from future training runs. It is not deleted and can be re-included at any time.
          </Typography>
          <TextField
            fullWidth
            label="Reason"
            placeholder="e.g. incorrect span, PHI risk, duplicate…"
            value={excludeReason}
            onChange={(e) => setExcludeReason(e.target.value)}
            multiline
            rows={2}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExcludeTarget(null)}>Cancel</Button>
          <Button
            onClick={handleExclude}
            disabled={!excludeReason.trim() || excludeBusy}
            color="error"
            variant="contained"
          >
            {excludeBusy ? "Excluding…" : "Exclude"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ---- Start job dialog ---- */}
      <Dialog open={startJobOpen} onClose={() => setStartJobOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Start training run</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            This will fine-tune the NER head on top of Bio_ClinicalBERT using all{" "}
            <strong>{preview?.exportable_label_count ?? "?"} included labels</strong>. Training
            runs in the background — you can close this dialog and check progress below.
          </Typography>
          <TextField
            fullWidth
            label="Notes (optional)"
            placeholder="e.g. added 20 haemoptysis corrections"
            value={jobNotes}
            onChange={(e) => setJobNotes(e.target.value)}
            multiline
            rows={2}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStartJobOpen(false)}>Cancel</Button>
          <Button
            onClick={handleStartJob}
            disabled={startingJob}
            variant="contained"
            color="primary"
            startIcon={startingJob ? <CircularProgress size={14} /> : <PlayArrowIcon />}
          >
            {startingJob ? "Queuing…" : "Start"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
