/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-94D87FA7
 *   Also implements: DO-A2553F87
 *   DI: DI-425CA252, DI-54D00E21
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-94D87FA7")
 */
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
  Divider,
  Drawer,
  FormControl,
  IconButton,
  LinearProgress,
  Menu,
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
import MoreVertIcon from "@mui/icons-material/MoreVert";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import HourglassTopIcon from "@mui/icons-material/HourglassTop";
import PauseIcon from "@mui/icons-material/Pause";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";
import AssertionChip from "@/components/AssertionChip";
import ConfirmDialog from "@/components/ConfirmDialog";
import RecordMindMap from "@/components/operations/RecordMindMap";
import {
  coerceEntitySemanticLabel,
  normaliseEntitySemanticRows,
  VALID_ENTITY_SEMANTIC_LABELS as VALID_ENTITY_LABELS,
} from "@/lib/entitySemanticLabels";
import AccountTreeIcon from "@mui/icons-material/AccountTree";

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

interface AuditStatus {
  status: "idle" | "running" | "stopping" | "done" | "failed" | "cancelled";
  mode?: "all" | "hitl_only";
  apply?: boolean;
  no_agentic?: boolean;
  started_at: number | null;
  finished_at: number | null;
  total?: number;
  done?: number;
  passed?: number;
  has_issues?: number;
  errors?: number;
  auto_fixed?: number;
  proposals?: number;
  needs_review?: number;
  second_opinions?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
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
  /** Qualifiers for observable entities */
  numeric_value?: string | number | null;
  unit?: string | null;
  reference_range?: string | null;
  value?: string | number | null;
  [k: string]: unknown;
}

interface ResolvedCandidate {
  snomed_concept_id: string | null;
  snomed_term: string | null;
  semantic_tag: string | null;
  read_code: string | null;
  score: number;
  source: string;
}

const ENTITY_LABEL_DISPLAY: Record<string, string> = {
  disorder: "Health condition",
  finding: "Finding or symptom",
  procedure: "Treatment or procedure",
  observable_entity: "Test or measurement",
  qualifier_value: "Qualifier",
  substance: "Substance",
  medicinal_product: "Medicine",
  clinical_drug: "Drug",
  situation: "Situation",
  event: "Event",
  body_structure: "Body part",
  tumor_staging: "Tumour stage",
  assessment_scale: "Assessment scale",
  staging_scale: "Staging scale",
  regime_therapy: "Therapy plan",
  record_artifact: "Record type",
  physical_object: "Physical object",
  organism: "Organism",
  morphologic_abnormality: "Structural change",
  occupation: "Job or role",
  attribute: "Attribute",
  environment: "Environment",
  product: "Product",
  X_TEMPORAL: "Time or date",
  X_DOSAGE: "Dose",
  X_FREQUENCY: "How often",
  X_ROUTE: "How given",
};

/** Semantic tag colours for entity chips — distinct, accessible palette */
const ENTITY_LABEL_COLORS: Record<string, { bg: string; border: string }> = {
  disorder: { bg: "#FEE2E2", border: "#DC2626" },
  finding: { bg: "#DBEAFE", border: "#2563EB" },
  procedure: { bg: "#D1FAE5", border: "#059669" },
  observable_entity: { bg: "#E0E7FF", border: "#4F46E5" },
  qualifier_value: { bg: "#FEF3C7", border: "#D97706" },
  substance: { bg: "#FCE7F3", border: "#DB2777" },
  medicinal_product: { bg: "#ECFCCB", border: "#65A30D" },
  clinical_drug: { bg: "#D9F99D", border: "#4D7C0F" },
  situation: { bg: "#E0F2FE", border: "#0284C7" },
  event: { bg: "#F3E8FF", border: "#7C3AED" },
  body_structure: { bg: "#FFEDD5", border: "#EA580C" },
  tumor_staging: { bg: "#FECACA", border: "#B91C1C" },
  assessment_scale: { bg: "#BFDBFE", border: "#0d46d6" },
  staging_scale: { bg: "#C4B5FD", border: "#6D28D9" },
  regime_therapy: { bg: "#BBF7D0", border: "#15803D" },
  record_artifact: { bg: "#E5E7EB", border: "#4B5563" },
  physical_object: { bg: "#FDE68A", border: "#B45309" },
  organism: { bg: "#A7F3D0", border: "#047857" },
  morphologic_abnormality: { bg: "#FBCFE8", border: "#BE185D" },
  occupation: { bg: "#DDD6FE", border: "#5B21B6" },
  attribute: { bg: "#FECDD3", border: "#E11D48" },
  environment: { bg: "#CCFBF1", border: "#0D9488" },
  product: { bg: "#D9F99D", border: "#3F6212" },
  X_TEMPORAL: { bg: "#E0F2FE", border: "#0369A1" },
  X_DOSAGE: { bg: "#FEF9C3", border: "#CA8A04" },
  X_FREQUENCY: { bg: "#FEF3C7", border: "#B45309" },
  X_ROUTE: { bg: "#FDE68A", border: "#D97706" },
};

const SOURCE_LABELS: Record<string, string> = {
  hitl_approval: "Reviewed",
  coding_correction: "Corrected",
  anchor_mining: "Auto-found",
  seed: "Starting set",
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

const DEFAULT_ENTITY_COLOR = { bg: "#F3F4F6", border: "#9CA3AF" };

function EntityPills({ entitiesJson, showAll = false }: { entitiesJson: string; showAll?: boolean }) {
  let entities: { text: string; label: string; assertion?: string }[] = [];
  try { entities = JSON.parse(entitiesJson); } catch { /* ignore */ }
  if (!entities.length) return <Typography variant="caption" color="text.disabled">--</Typography>;
  const visible = showAll ? entities : entities.slice(0, 3);
  return (
    <Stack direction="row" flexWrap="wrap" gap={0.4} useFlexGap>
      {visible.map((e, i) => {
        const sem = coerceEntitySemanticLabel(e.label);
        const colors = ENTITY_LABEL_COLORS[sem] ?? DEFAULT_ENTITY_COLOR;
        return (
          <Stack key={i} direction="row" spacing={0.3} alignItems="center">
            <Tooltip title={ENTITY_LABEL_DISPLAY[sem] ?? sem} arrow>
              <Chip
                label={e.text}
                size="small"
                variant="outlined"
                sx={{
                  fontSize: 11,
                  maxWidth: 180,
                  bgcolor: colors.bg,
                  borderColor: colors.border,
                  "& .MuiChip-label": { color: colors.border },
                }}
              />
            </Tooltip>
            {e.assertion && e.assertion !== "present" && (
              <AssertionChip assertion={e.assertion} />
            )}
          </Stack>
        );
      })}
      {!showAll && entities.length > 3 && <Chip label={`+${entities.length - 3}`} size="small" sx={{ fontSize: 10 }} />}
    </Stack>
  );
}

function EntityDetailList({
  entitiesJson,
  resolvedData,
  resolving,
}: {
  entitiesJson: string;
  resolvedData: Record<string, ResolvedCandidate[]>;
  resolving: boolean;
}) {
  let entities: LabelEntity[] = [];
  try { entities = JSON.parse(entitiesJson); } catch { /* ignore */ }
  if (!entities.length) return <Typography variant="caption" color="text.disabled">--</Typography>;
  return (
    <Stack spacing={1.5}>
      {resolving && (
        <Stack direction="row" spacing={0.5} alignItems="center">
          <CircularProgress size={14} />
          <Typography variant="caption" color="text.secondary">Resolving to SNOMED…</Typography>
        </Stack>
      )}
      {entities.map((ent, i) => {
        const sem = coerceEntitySemanticLabel(ent.label);
        const colors = ENTITY_LABEL_COLORS[sem] ?? DEFAULT_ENTITY_COLOR;
        const candidates = resolvedData[ent.text?.trim() ?? ""];
        const top = candidates?.[0];
        const hasQualifiers =
          (ent.numeric_value != null && String(ent.numeric_value).trim() !== "") ||
          (ent.value != null && String(ent.value).trim() !== "") ||
          (ent.unit != null && String(ent.unit).trim() !== "") ||
          (ent.reference_range != null && String(ent.reference_range).trim() !== "");
        return (
          <Paper
            key={i}
            variant="outlined"
            sx={{
              p: 1.25,
              borderRadius: 1,
              borderLeft: "3px solid",
              borderLeftColor: colors.border,
            }}
          >
            <Stack spacing={0.75}>
              <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
                <Chip
                  label={ent.text}
                  size="small"
                  sx={{
                    fontSize: 10.5,
                    fontWeight: 600,
                    bgcolor: colors.bg,
                    borderColor: colors.border,
                    "& .MuiChip-label": { color: colors.border },
                  }}
                  variant="outlined"
                />
                <Chip
                  label={ENTITY_LABEL_DISPLAY[sem] ?? sem}
                  size="small"
                  sx={{
                    height: 18,
                    fontSize: 10,
                    bgcolor: colors.bg,
                    color: colors.border,
                    border: `1px solid ${colors.border}35`,
                    "& .MuiChip-label": { px: 0.75 },
                  }}
                />
                {ent.assertion && ent.assertion !== "present" && (
                  <AssertionChip assertion={ent.assertion} />
                )}
              </Stack>
              {(top?.snomed_concept_id || top?.snomed_term) && (
                <Stack spacing={0.25} sx={{ pl: 0.5 }}>
                  {top.snomed_term && (
                    <Stack direction="row" spacing={1}>
                      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 70 }}>PT</Typography>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>{top.snomed_term}</Typography>
                    </Stack>
                  )}
                  {top.snomed_concept_id && (
                    <Stack direction="row" spacing={1}>
                      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 70 }}>SNOMED</Typography>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>{top.snomed_concept_id}</Typography>
                    </Stack>
                  )}
                </Stack>
              )}
              {hasQualifiers && (
                <Stack spacing={0.25} sx={{ pl: 0.5 }}>
                  {(ent.numeric_value != null && String(ent.numeric_value).trim() !== "") ||
                  (ent.value != null && String(ent.value).trim() !== "") ? (
                    <Stack direction="row" spacing={1}>
                      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 70 }}>Value</Typography>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                        {String(ent.numeric_value ?? ent.value ?? "")}
                      </Typography>
                    </Stack>
                  ) : null}
                  {ent.unit != null && String(ent.unit).trim() !== "" ? (
                    <Stack direction="row" spacing={1}>
                      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 70 }}>Unit</Typography>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>{ent.unit}</Typography>
                    </Stack>
                  ) : null}
                  {ent.reference_range != null && String(ent.reference_range).trim() !== "" ? (
                    <Stack direction="row" spacing={1}>
                      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 70 }}>Ref range</Typography>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>{ent.reference_range}</Typography>
                    </Stack>
                  ) : null}
                </Stack>
              )}
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// How this tab works - stages for the flow diagram
// ---------------------------------------------------------------------------

const TRAINING_STAGES: TabStage[] = [
  {
    id: "td1", num: 1,
    label: "Gather examples",
    tooltip: "All the records that people have checked and approved are gathered together. These become the teaching examples for the AI.",
    detailIn: "Approved records from the review queue",
    detailOut: "A set of correct examples ready to learn from",
    branches: [
      {
        label: "Not enough examples",
        description: "The AI needs at least 50 approved examples before it can start learning. Check back after more reviews are done",
      },
    ],
  },
  {
    id: "td2", num: 2,
    label: "Check examples",
    tooltip: "Each example is checked and tidied up. You can edit or remove examples that look wrong before the AI starts learning.",
    detailIn: "The collected teaching examples",
    detailOut: "A clean, checked set of teaching examples",
    branches: [
      {
        label: "Remove an example",
        description: "You can take out an example if you think it would teach the AI the wrong thing",
      },
    ],
  },
  {
    id: "td3", num: 3,
    label: "AI learns",
    tooltip: "The AI studies thousands of correct examples so it can learn to spot medical words on its own.",
    detailIn: "The clean teaching examples",
    detailOut: "A freshly trained AI",
    branches: [
      {
        label: "Hardware retry",
        description: "If learning fails on a fast machine, we try again on slower hardware -- up to 4 attempts",
      },
    ],
  },
  {
    id: "td4", num: 4,
    label: "AI tested",
    tooltip: "We give the AI a quiz using examples it has never seen before to check it learned well enough.",
    detailIn: "The trained AI and a set of test examples",
    detailOut: "A test score -- it must get at least 80% of answers right and find at least 75% of items",
    branches: [
      {
        label: "Did not pass",
        description: "If the AI does not score high enough, learning stops here and the new AI is not used",
      },
    ],
  },
  {
    id: "td5", num: 5,
    label: "New AI ready",
    tooltip: "If the AI passes, it is saved. Go to the Make the AI Live tab to put it into use.",
    detailIn: "The tested and approved AI",
    detailOut: "A new AI version ready to go live",
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
  const [showMap, setShowMap] = useState(false);
  const [editingEntities, setEditingEntities] = useState(false);
  const [draftEntities, setDraftEntities] = useState<LabelEntity[]>([]);
  const [savingEntities, setSavingEntities] = useState(false);
  const [entityResolvedData, setEntityResolvedData] = useState<Record<string, ResolvedCandidate[]>>({});
  const [resolvingEntities, setResolvingEntities] = useState(false);

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
  const [verifyMenuAnchor, setVerifyMenuAnchor] = useState<HTMLElement | null>(null);
  const [auditStatus, setAuditStatus] = useState<AuditStatus | null>(null);
  const [startingAudit, setStartingAudit] = useState(false);
  const [confirmExclude, setConfirmExclude] = useState(false);

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
      const list = [...(data.jobs ?? [])].sort((a, b) => b.created_at - a.created_at);
      setJobs(list);
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

  const fetchAuditStatus = useCallback(async () => {
    try {
      const data = await jsonFetch<AuditStatus>("/api/training/labels/agentic-audit/status");
      setAuditStatus(data);
    } catch { /* silently swallow */ }
  }, []);

  useEffect(() => { fetchStats(); fetchJobs(); fetchPreview(); fetchVerificationStatus(); fetchAuditStatus(); }, [fetchStats, fetchJobs, fetchPreview, fetchVerificationStatus, fetchAuditStatus]);
  useEffect(() => { fetchLabels(); }, [fetchLabels]);

  // Resolve entities to SNOMED when detail panel opens
  useEffect(() => {
    if (!selectedLabel || editingEntities) {
      setEntityResolvedData({});
      return;
    }
    let entities: LabelEntity[] = [];
    try { entities = JSON.parse(selectedLabel.entities_json); } catch { /* ignore */ }
    const terms = [...new Set(entities.map((e) => e.text?.trim()).filter(Boolean))];
    if (terms.length === 0) {
      setEntityResolvedData({});
      return;
    }
    setResolvingEntities(true);
    const labelToSnomedTag: Record<string, string> = {
      disorder: "disorder", finding: "finding", procedure: "procedure",
      observable_entity: "observable entity", qualifier_value: "qualifier value",
      substance: "substance", medicinal_product: "medicinal product", clinical_drug: "clinical drug",
      situation: "situation", event: "event", body_structure: "body structure",
      tumor_staging: "tumor staging", assessment_scale: "assessment scale", staging_scale: "staging scale",
      regime_therapy: "regime/therapy", record_artifact: "record artifact", physical_object: "physical object",
      organism: "organism", morphologic_abnormality: "morphologic abnormality", occupation: "occupation",
      attribute: "attribute", environment: "environment", product: "product",
    };
    jsonFetch<{ results: Record<string, ResolvedCandidate[]> }>("/api/terminology/resolve", {
      method: "POST",
      body: JSON.stringify({
        terms,
        expected_tags: Object.fromEntries(
          entities
            .map((e) => [e.text?.trim(), labelToSnomedTag[e.label] ?? e.label])
            .filter(([t]) => t) as [string, string][]
        ),
      }),
    })
      .then((data) => setEntityResolvedData(data.results ?? {}))
      .catch(() => setEntityResolvedData({}))
      .finally(() => setResolvingEntities(false));
  }, [selectedLabel?.label_id, selectedLabel?.entities_json, editingEntities]);

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

  // Poll Agentic Auditor status while running/stopping.
  useEffect(() => {
    const isActive =
      auditStatus?.status === "running" ||
      auditStatus?.status === "stopping" ||
      startingAudit;
    if (!isActive) return;
    const id = setInterval(() => {
      fetchAuditStatus();
    }, 5000);
    return () => clearInterval(id);
  }, [auditStatus?.status, startingAudit, fetchAuditStatus]);

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
    if (!excludeTarget) return;
    setExcludeBusy(true);
    try {
      await jsonFetch(`/api/training/labels/${excludeTarget}/exclude`, {
        method: "POST",
        body: JSON.stringify({ reason: excludeReason.trim() || "Removed by reviewer" }),
      });
      setExcludeTarget(null);
      setExcludeReason("");
      setConfirmExclude(false);
      fetchStats();
      fetchLabels();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove this record. Please try again.");
    } finally {
      setExcludeBusy(false);
    }
  };

  const handleSaveEntities = async () => {
    if (!selectedLabel) return;
    setSavingEntities(true);
    try {
      const entitiesPayload = normaliseEntitySemanticRows(draftEntities);
      await jsonFetch(`/api/training/labels/${selectedLabel.label_id}/entities`, {
        method: "PATCH",
        body: JSON.stringify({ entities: entitiesPayload }),
      });
      const updatedEntitiesJson = JSON.stringify(entitiesPayload);
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
        { method: "POST", body: JSON.stringify({ notes: jobNotes || "Started from operations UI", triggered_by: "ui" }) }
      );
      setStartJobOpen(false);
      setJobNotes("");
      fetchJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the learning run. Please try again.");
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

  const handleStartAudit = async (
    mode: "all" | "hitl_only",
    apply: boolean,
    no_agentic: boolean,
  ) => {
    setStartingAudit(true);
    try {
      await jsonFetch<{ status: string; message: string }>("/api/training/labels/agentic-audit", {
        method: "POST",
        body: JSON.stringify({ mode, apply, no_agentic }),
      });
      fetchAuditStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start Agentic Auditor");
    } finally {
      setStartingAudit(false);
    }
  };

  const handleStopAudit = async () => {
    try {
      await jsonFetch<{ status: string; message: string }>("/api/training/labels/agentic-audit/cancel", {
        method: "POST",
      });
      fetchAuditStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop Agentic Auditor");
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
  const auditRunning =
    auditStatus?.status === "running" ||
    auditStatus?.status === "stopping" ||
    startingAudit;
  const auditDone   = auditStatus?.status === "done" || auditStatus?.status === "cancelled";
  const auditPct    = auditStatus?.total && auditStatus.total > 0
    ? Math.round(((auditStatus.done ?? 0) / auditStatus.total) * 100)
    : 0;

  // ---------- render ----------

  return (
    <Stack spacing={1.5}>

      {/* Page title */}
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>Teach the AI</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: 13 }}>
          Check the teaching examples, then start a run so the AI can learn from them.
        </Typography>
      </Box>

      {/* How this works */}
      <Accordion variant="outlined" disableGutters sx={{ "&::before": { display: "none" } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.75 } }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
            How this tab works
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0, pb: 1.5 }}>
          <TabFlowDiagram
            stages={TRAINING_STAGES}
            color="#7C3AED"
            lightColor="#EDE9FE"
            trackLabel="Teach the AI"
          />
        </AccordionDetails>
      </Accordion>

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ py: 0.25 }}>{error}</Alert>
      )}

      {/* ── Hero: current state ── */}
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          borderRadius: 1.5,
          borderColor: activeJob ? "primary.main"
            : lastJob?.status === "failed" ? "error.light"
            : lastJob?.status === "done" ? "success.light"
            : "divider",
          borderWidth: activeJob ? 2 : 1,
        }}
      >
        {/* Active job */}
        {activeJob && (
          <Stack spacing={1}>
            <Stack direction="row" spacing={1} alignItems="center">
              <HourglassTopIcon color="primary" fontSize="small" />
              <Box flex={1}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>The AI is learning</Typography>
                <Typography variant="caption" color="text.secondary">
                  Step: {activeJob.phase || "starting up"}
                  {activeJob.elapsed_s != null && ` · ${fmtElapsed(activeJob.elapsed_s)} so far`}
                </Typography>
              </Box>
            </Stack>
            <LinearProgress sx={{ borderRadius: 1 }} />
            {activeJob.log_lines?.length > 0 && (
              <Box ref={heroLogRef} sx={{ background: "#0f172a", color: "#86efac", fontFamily: "monospace", fontSize: 11, p: 1, borderRadius: 1, height: 160, overflowY: "auto" }}>
                {activeJob.log_lines.map((l, i) => <div key={i}>{l}</div>)}
              </Box>
            )}
          </Stack>
        )}

        {/* Last job failed */}
        {!activeJob && lastJob?.status === "failed" && (
          <Stack direction="row" spacing={1} alignItems="flex-start">
            <ErrorOutlineIcon color="error" fontSize="small" sx={{ mt: 0.25 }} />
            <Box flex={1}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>The last run did not finish</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                {lastJob.error || "Something went wrong while the AI was learning."}
                {lastJob.elapsed_s != null && ` · ran for ${fmtElapsed(lastJob.elapsed_s)}`}
              </Typography>
              <Stack direction="row" spacing={1}>
                <Button size="small" variant="contained" startIcon={<PlayArrowIcon />} onClick={() => setStartJobOpen(true)}>
                  Try again
                </Button>
                <Button size="small" onClick={() => setExpandedJob(expandedJob === lastJob.job_id ? null : lastJob.job_id)}>
                  {expandedJob === lastJob.job_id ? "Hide log" : "Show log"}
                </Button>
              </Stack>
              <Collapse in={expandedJob === lastJob.job_id}>
                <Box sx={{ mt: 1, background: "#0f172a", color: "#fca5a5", fontFamily: "monospace", fontSize: 11, p: 1, borderRadius: 1, maxHeight: 140, overflowY: "auto" }}>
                  {(lastJob.log_lines ?? []).map((l, i) => <div key={i}>{l}</div>)}
                </Box>
              </Collapse>
            </Box>
          </Stack>
        )}

        {!activeJob && lastJob?.status === "done" && (
          <Stack direction="row" spacing={1} alignItems="center">
            <CheckCircleIcon color="success" fontSize="small" />
            <Box flex={1}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                The AI has finished learning{lastJob.model_version ? ` — version ${lastJob.model_version}` : ""}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Go to the <strong>Make the AI Live</strong> tab to test and put it into use.
                {lastJob.elapsed_s != null && ` · took ${fmtElapsed(lastJob.elapsed_s)}`}
              </Typography>
            </Box>
            <Button size="small" variant="outlined" startIcon={<PlayArrowIcon />} onClick={() => setStartJobOpen(true)}>
              New run
            </Button>
          </Stack>
        )}

        {!activeJob && !lastJob && (
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Box flex={1}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {preview?.exportable_label_count.toLocaleString() ?? stats?.included.toLocaleString() ?? "…"} records ready
              </Typography>
              <Typography variant="caption" color="text.secondary">
                No learning runs yet. Start one so the AI can learn from these examples.
              </Typography>
            </Box>
            <Button
              variant="contained"
              startIcon={<PlayArrowIcon />}
              disabled={!preview?.ready_to_train}
              onClick={() => setStartJobOpen(true)}
            >
              Start learning
            </Button>
          </Stack>
        )}
      </Paper>

      {/* Start button when there's a previous job but no active one */}
      {!activeJob && lastJob && (
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            {(preview?.exportable_label_count ?? stats?.included ?? 0).toLocaleString()} included · {(stats?.excluded ?? 0).toLocaleString()} excluded
          </Typography>
          <Box flex={1} />
          <Button
            size="small"
            variant="contained"
            startIcon={<PlayArrowIcon />}
            disabled={!preview?.ready_to_train}
            onClick={() => setStartJobOpen(true)}
          >
            Start learning
          </Button>
          <IconButton aria-label="Refresh teaching records" size="small" onClick={() => { fetchJobs(); fetchStats(); fetchPreview(); }}>
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Stack>
      )}

      {/* ── Run history ── */}
      {jobs.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: 0.5, fontSize: 10, fontWeight: 600, flex: 1 }}>
              Past runs
            </Typography>
            <Tooltip title={pollingPaused ? "Resume live updates" : "Pause live updates"}>
              <IconButton aria-label={pollingPaused ? "Resume live updates" : "Pause live updates"} size="small" onClick={() => setPollingPaused((p) => !p)}>
                {pollingPaused
                  ? <PlayCircleOutlineIcon fontSize="small" color="success" />
                  : <PauseIcon fontSize="small" color="action" />}
              </IconButton>
            </Tooltip>
            <Tooltip title="Refresh now">
              <IconButton aria-label="Refresh now" size="small" onClick={() => { fetchJobs(); fetchStats(); }}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
          <Stack spacing={0.75}>
            {jobs.map((job) => {
              const isActive = ACTIVE_STATUSES.has(job.status);
              const isExpanded = !isActive && expandedJob === job.job_id;
              return (
                <Paper key={job.job_id} variant="outlined" sx={{ p: 1, px: 1.5, borderRadius: 1 }}>
                  <Stack direction="row" spacing={1} alignItems="center">
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
                    <IconButton aria-label={isExpanded ? "Collapse job" : "Expand job"} size="small" onClick={() => setExpandedJob(isExpanded ? null : job.job_id)}>
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
                            <Typography variant="caption">Correct answers <strong>{m.precision}</strong></Typography>
                            <Typography variant="caption">Found answers <strong>{m.recall}</strong></Typography>
                            <Typography variant="caption">Overall score <strong>{m.f1}</strong></Typography>
                            <Chip label={m.passed_gates ? "Quality check passed" : "Quality check failed"} color={m.passed_gates ? "success" : "error"} size="small" />
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
      <Accordion disableGutters variant="outlined" sx={{ borderRadius: "6px !important", "&::before": { display: "none" } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: 1.5, minHeight: 40, "& .MuiAccordionSummary-content": { my: 0.5 } }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ width: "100%" }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, fontSize: 13 }}>Teaching records</Typography>
            {labelTotal > 0 && (
              <Chip label={`${labelTotal.toLocaleString()} records`} size="small" variant="outlined" />
            )}
            {(stats?.excluded ?? 0) > 0 && (
              <Chip label={`${stats!.excluded} excluded`} size="small" color="warning" variant="outlined" />
            )}
            {verificationStatus?.pending_review ? (
              <Chip
                label={`${verificationStatus.pending_review} waiting for you`}
                size="small"
                color="warning"
                variant="outlined"
              />
            ) : null}
            {(verificationStatus?.auto_resolved ?? 0) > 0 ? (
              <Chip
                label={`${verificationStatus?.auto_resolved ?? 0} fixed automatically`}
                size="small"
                color="success"
                variant="outlined"
              />
            ) : null}
            {verificationRunning ? (
              <Chip label="Checking labels" size="small" color="primary" />
            ) : verificationFinishedAt ? (
              <Chip label={`Last checked ${verificationFinishedAt}`} size="small" variant="outlined" />
            ) : null}
            {auditRunning ? (
              <Chip label="Agentic audit running…" size="small" color="secondary" />
            ) : null}
            {!auditRunning && (auditStatus?.auto_fixed ?? 0) > 0 ? (
              <Chip
                label={`${auditStatus!.auto_fixed} Opus-fixed`}
                size="small"
                color="success"
                variant="outlined"
              />
            ) : null}
            {!auditRunning && (auditStatus?.proposals ?? 0) > 0 ? (
              <Chip
                label={`${auditStatus!.proposals} proposals`}
                size="small"
                color="info"
                variant="outlined"
              />
            ) : null}
          </Stack>
        </AccordionSummary>
        <AccordionDetails sx={{ p: 0 }}>
          {/* Filters */}
          <Stack direction="row" spacing={0.75} sx={{ px: 1.5, py: 1 }} flexWrap="wrap" alignItems="center" useFlexGap>
            <TextField
              size="small"
              placeholder="Search…"
              value={searchText}
              onChange={(e) => { setSearchText(e.target.value); setLabelPage(1); }}
              sx={{ width: 160 }}
              inputProps={{ sx: { py: 0.5, fontSize: 13 } }}
            />
            <ToggleButtonGroup size="small" exclusive value={filterSource ?? ""} onChange={(_, v) => { setFilterSource(v || null); setLabelPage(1); }} role="group" aria-label="Filter by source">
              <ToggleButton value="">All</ToggleButton>
              <ToggleButton value="hitl_approval">Reviewed</ToggleButton>
              <ToggleButton value="coding_correction">Corrected</ToggleButton>
              <ToggleButton value="anchor_mining">Auto-found</ToggleButton>
              <ToggleButton value="seed">Starting set</ToggleButton>
            </ToggleButtonGroup>
            <ToggleButtonGroup size="small" exclusive value={filterInclude === null ? "" : String(filterInclude)} onChange={(_, v) => { setFilterInclude(v === "" ? null : v === "true"); setLabelPage(1); }}>
              <ToggleButton value="">All</ToggleButton>
              <ToggleButton value="true">Included</ToggleButton>
              <ToggleButton value="false">Excluded</ToggleButton>
            </ToggleButtonGroup>
            <IconButton aria-label="Refresh teaching records" size="small" onClick={() => { fetchLabels(); fetchVerificationStatus(); }}>
              <RefreshIcon fontSize="small" />
            </IconButton>
            <Box flex={1} />
            {auditRunning && (
              <Button
                size="small"
                variant="outlined"
                color="secondary"
                onClick={handleStopAudit}
                sx={{ mr: 0.5 }}
              >
                Stop audit
              </Button>
            )}
            {verificationRunning ? (
              <Button
                size="small"
                variant="outlined"
                color="error"
                onClick={handleStopVerification}
              >
                Stop checking
              </Button>
            ) : (
              <Button
                size="small"
                variant="contained"
                disabled={startingVerification}
                onClick={() => handleVerifyLabels("all", false)}
              >
                {startingVerification ? "Starting..." : "Check labels"}
              </Button>
            )}
            <IconButton
              aria-label="More label actions"
              size="small"
              onClick={(e) => setVerifyMenuAnchor(e.currentTarget)}
            >
              <MoreVertIcon fontSize="small" />
            </IconButton>
            <Menu
              anchorEl={verifyMenuAnchor}
              open={Boolean(verifyMenuAnchor)}
              onClose={() => setVerifyMenuAnchor(null)}
            >
              <MenuItem
                disabled={verificationRunning}
                onClick={() => { setVerifyMenuAnchor(null); handleVerifyLabels("all", true); }}
              >
                Reset and recheck all
              </MenuItem>
              <MenuItem
                disabled={verificationRunning}
                onClick={() => { setVerifyMenuAnchor(null); handleVerifyLabels("hitl_only", false); }}
              >
                Recheck reviewed labels only
              </MenuItem>
              <MenuItem
                disabled={verificationRunning}
                onClick={() => { setVerifyMenuAnchor(null); handleVerifyLabels("resume", false); }}
              >
                Resume checking
              </MenuItem>
              <Divider />
              <MenuItem
                disabled={auditRunning}
                onClick={() => { setVerifyMenuAnchor(null); handleStartAudit("all", false, false); }}
              >
                Agentic audit — find &amp; flag issues
              </MenuItem>
              <MenuItem
                disabled={auditRunning}
                onClick={() => { setVerifyMenuAnchor(null); handleStartAudit("all", true, false); }}
              >
                Agentic audit — apply safe fixes
              </MenuItem>
              <MenuItem
                disabled={auditRunning}
                onClick={() => { setVerifyMenuAnchor(null); handleStartAudit("hitl_only", true, false); }}
              >
                Agentic audit — HITL queue only
              </MenuItem>
              <MenuItem
                disabled={auditRunning}
                onClick={() => { setVerifyMenuAnchor(null); handleStartAudit("all", false, true); }}
              >
                Agentic audit — quick (no terminology tools)
              </MenuItem>
            </Menu>
          </Stack>

          {verificationRunning && (
            <Stack
              direction="row"
              spacing={0.75}
              sx={{ px: 1.5, pb: 1, flexWrap: "wrap" }}
              alignItems="center"
              useFlexGap
            >
              <Chip
                label={`${verificationStatus?.done ?? 0} of ${verificationStatus?.total ?? 0} checked (${(verificationStatus?.progress_pct ?? 0).toFixed(1)}%)`}
                size="small"
                color="primary"
                variant="outlined"
              />
              <Chip
                label={`${verificationStatus?.remaining ?? 0} left`}
                size="small"
                color="primary"
                variant="outlined"
              />
              {typeof verificationStatus?.items_per_min === "number" && verificationStatus.items_per_min > 0 ? (
                <Chip
                  label={`${verificationStatus.items_per_min.toFixed(1)} per minute`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              ) : null}
              {typeof verificationStatus?.eta_seconds === "number" ? (
                <Chip
                  label={`About ${fmtElapsed(verificationStatus.eta_seconds)} left`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              ) : null}
              {typeof verificationStatus?.eta_at === "number" ? (
                <Chip
                  label={`Should finish by ${new Date(verificationStatus.eta_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
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
              sx={{ mx: 1.5, mb: 1, borderRadius: 1 }}
            />
          ) : null}

          {/* Agentic audit progress */}
          {auditRunning && (
            <Stack
              direction="row"
              spacing={0.75}
              sx={{ px: 1.5, pb: 1, flexWrap: "wrap" }}
              alignItems="center"
              useFlexGap
            >
              <Chip
                label={`Opus: ${auditStatus?.done ?? 0} of ${auditStatus?.total ?? "?"} audited${auditStatus?.total ? ` (${auditPct}%)` : ""}`}
                size="small"
                color="secondary"
              />
              {(auditStatus?.auto_fixed ?? 0) > 0 && (
                <Chip label={`${auditStatus!.auto_fixed} fixed`} size="small" color="success" variant="outlined" />
              )}
              {(auditStatus?.proposals ?? 0) > 0 && (
                <Chip label={`${auditStatus!.proposals} proposals`} size="small" color="info" variant="outlined" />
              )}
              {(auditStatus?.needs_review ?? 0) > 0 && (
                <Chip label={`${auditStatus!.needs_review} needs review`} size="small" color="warning" variant="outlined" />
              )}
              {(auditStatus?.second_opinions ?? 0) > 0 && (
                <Chip label={`${auditStatus!.second_opinions} 2nd opinions`} size="small" variant="outlined" />
              )}
              {typeof auditStatus?.estimated_cost_usd === "number" && (
                <Chip
                  label={`~$${auditStatus.estimated_cost_usd.toFixed(2)} est. cost`}
                  size="small"
                  variant="outlined"
                />
              )}
            </Stack>
          )}
          {auditRunning && auditStatus?.total && auditStatus.total > 0 ? (
            <LinearProgress
              variant="determinate"
              value={auditPct}
              color="secondary"
              sx={{ mx: 1.5, mb: 1, borderRadius: 1 }}
            />
          ) : null}

          {/* Agentic audit completed summary */}
          {auditDone && !auditRunning && (auditStatus?.done ?? 0) > 0 && (
            <Stack
              direction="row"
              spacing={0.75}
              sx={{ px: 1.5, pb: 1, flexWrap: "wrap" }}
              alignItems="center"
              useFlexGap
            >
              <Chip
                label={`Agentic audited ${auditStatus!.done} records`}
                size="small"
                color="secondary"
                variant="outlined"
              />
              {(auditStatus?.auto_fixed ?? 0) > 0 && (
                <Chip label={`${auditStatus!.auto_fixed} auto-fixed`} size="small" color="success" variant="outlined" />
              )}
              {(auditStatus?.proposals ?? 0) > 0 && (
                <Chip label={`${auditStatus!.proposals} proposals`} size="small" color="info" variant="outlined" />
              )}
              {typeof auditStatus?.estimated_cost_usd === "number" && (
                <Chip
                  label={`$${auditStatus.estimated_cost_usd.toFixed(2)} total cost`}
                  size="small"
                  variant="outlined"
                />
              )}
              {(auditStatus?.second_opinions ?? 0) > 0 && (
                <Chip label={`${auditStatus!.second_opinions} independent opinions`} size="small" variant="outlined" />
              )}
            </Stack>
          )}

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
                  <TableRow><TableCell colSpan={5} align="center"><CircularProgress aria-label="Loading" size={18} /></TableCell></TableRow>
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
                    <TableCell sx={{ maxWidth: 260, py: 0.75 }}>
                      <Typography variant="caption" sx={{ fontSize: 12, lineHeight: 1.4 }}>
                        {label.text.slice(0, 90)}{label.text.length > 90 ? "…" : ""}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ minWidth: 140 }}>
                      <EntityPills entitiesJson={label.entities_json} />
                    </TableCell>
                    <TableCell>
                      <Chip label={SOURCE_LABELS[label.source] ?? label.source} color={SOURCE_COLORS[label.source] ?? "default"} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell>
                      {label.include
                        ? <Chip label="Included" color="success" size="small" variant="outlined" />
                        : <Tooltip title={label.excluded_reason ?? ""}><Chip label="Excluded" color="default" size="small" variant="outlined" /></Tooltip>}
                    </TableCell>
                    <TableCell align="right">
                      {label.include
                        ? <Tooltip title="Remove from training"><IconButton aria-label="Remove from training" size="small" onClick={(e) => { e.stopPropagation(); setExcludeTarget(label.label_id); }}><BlockIcon fontSize="small" color="error" /></IconButton></Tooltip>
                        : <Tooltip title="Add back to training"><IconButton aria-label="Add back to training" size="small" onClick={(e) => { e.stopPropagation(); handleInclude(label.label_id); }}><CheckCircleOutlineIcon fontSize="small" color="success" /></IconButton></Tooltip>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Pagination */}
          <Stack direction="row" spacing={0.75} alignItems="center" sx={{ px: 1.5, py: 0.75 }}>
            <Button size="small" disabled={labelPage <= 1} onClick={() => setLabelPage((p) => p - 1)}>← Prev</Button>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: 11 }}>
              {labelPage} / {totalPages} ({labelTotal.toLocaleString()})
            </Typography>
            <Button size="small" disabled={labelPage >= totalPages} onClick={() => setLabelPage((p) => p + 1)}>Next →</Button>
          </Stack>
        </AccordionDetails>
      </Accordion>

      {/* ── Label detail drawer ── */}
      <Drawer
        anchor="right"
        open={!!selectedLabel}
        onClose={() => { setSelectedLabel(null); setEditingEntities(false); setShowMap(false); }}
        PaperProps={{ sx: { width: { xs: "100%", sm: 440 }, display: "flex", flexDirection: "column" } }}
      >
        {selectedLabel && (
          <>
            {/* Header */}
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              sx={{ px: 2, py: 1.25, borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}
            >
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>Record detail</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>
                  {selectedLabel.label_id.slice(0, 20)}…
                </Typography>
              </Box>
              <Tooltip title="View as entity map">
                <IconButton
                  aria-label="View as entity map"
                  size="small"
                  onClick={() => setShowMap(true)}
                  sx={{ mr: 0.25 }}
                >
                  <AccountTreeIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <IconButton aria-label="Close record detail" size="small" onClick={() => { setSelectedLabel(null); setEditingEntities(false); }} edge="end">
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
                        aria-label="Edit entities"
                        size="small"
                        onClick={() => {
                          let parsed: LabelEntity[] = [];
                          try { parsed = JSON.parse(selectedLabel.entities_json); } catch { /* ignore */ }
                          setDraftEntities(normaliseEntitySemanticRows(parsed));
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
                        startIcon={savingEntities ? <CircularProgress aria-label="Loading" size={12} /> : undefined}
                      >
                        {savingEntities ? "Saving…" : "Save"}
                      </Button>
                    </Stack>
                  )}
                </Stack>

                {!editingEntities ? (
                  <EntityDetailList
                    entitiesJson={selectedLabel.entities_json}
                    resolvedData={entityResolvedData}
                    resolving={resolvingEntities}
                  />
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
                            value={coerceEntitySemanticLabel(ent.label)}
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
                                {ENTITY_LABEL_DISPLAY[l] ?? l}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                        <Tooltip title="Remove entity">
                          <IconButton
                            aria-label="Remove entity"
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

      {/* ── Entity mind-map modal ── */}
      {selectedLabel && (
        <RecordMindMap
          open={showMap}
          onClose={() => setShowMap(false)}
          text={selectedLabel.text}
          entitiesJson={selectedLabel.entities_json}
          resolvedData={entityResolvedData}
          resolving={resolvingEntities}
          included={selectedLabel.include}
          currentIndex={labels.findIndex((l) => l.label_id === selectedLabel.label_id)}
          totalCount={labels.length}
          onNext={() => {
            const idx = labels.findIndex((l) => l.label_id === selectedLabel.label_id);
            if (idx >= 0 && idx < labels.length - 1) setSelectedLabel(labels[idx + 1]);
          }}
          onPrev={() => {
            const idx = labels.findIndex((l) => l.label_id === selectedLabel.label_id);
            if (idx > 0) setSelectedLabel(labels[idx - 1]);
          }}
          onInclude={() => {
            handleInclude(selectedLabel.label_id);
            setSelectedLabel({ ...selectedLabel, include: true });
          }}
          onExclude={() => {
            setExcludeTarget(selectedLabel.label_id);
          }}
        />
      )}

      {/* ── Remove from teaching dialog ── */}
      {!!excludeTarget && (
        <ConfirmDialog
          title="Remove this record from teaching?"
          body="The AI will not learn from this record in future. You can add it back at any time."
          confirmLabel={excludeBusy ? "Removing…" : "Remove"}
          variant="danger"
          onConfirm={handleExclude}
          onCancel={() => { setExcludeTarget(null); setExcludeReason(""); setConfirmExclude(false); }}
        />
      )}

      {/* ── Start learning dialog ── */}
      {startJobOpen && (
        <ConfirmDialog
          title="Start a learning run?"
          body={`The AI will learn from ${(preview?.exportable_label_count ?? 0).toLocaleString()} records. This runs in the background — you can watch progress on this page.`}
          confirmLabel={startingJob ? "Starting…" : "Start"}
          onConfirm={handleStartJob}
          onCancel={() => setStartJobOpen(false)}
        />
      )}
    </Stack>
  );
}
