"use client";

import { useCallback, useEffect, useMemo, useState, type JSX, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CircularProgress from "@mui/material/CircularProgress";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Checkbox from "@mui/material/Checkbox";
import IconButton from "@mui/material/IconButton";
import LockIcon from "@mui/icons-material/Lock";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import EditNoteIcon from "@mui/icons-material/EditNote";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer,
} from "recharts";
import { TrainingJob } from "./useConsoleState";
import ConfirmDialog from "@/components/ConfirmDialog";
import { renderNerSpans, themeForTag, type AnnotatedSpan, type TagTheme } from "@/lib/nerAnnotation";
import { FONT_SIZES } from "@/theme/tokens";

interface EvaluateStageProps {
  jobs: TrainingJob[];
  latestJob: TrainingJob | null;
  promotedVersion?: string | null;
}

type ModelStatus =
  | "registered"
  | "offline_validated"
  | "canary"
  | "promoted"
  | "deprecated"
  | "rollback";

interface ModelRecord {
  model_version: string;
  status: ModelStatus;
  offline_precision: number | null;
  offline_recall: number | null;
  canary_precision: number | null;
  canary_recall: number | null;
}

interface CanaryPerLabel {
  label: string;
  precision: number;
  recall: number;
  f1: number;
  tp?: number;
  fp?: number;
  fn?: number;
}

interface CanaryMetrics {
  per_label: CanaryPerLabel[];
}

type CanaryCorpus = "full" | "holdback";

interface CanaryJob {
  job_id: string;
  version: string;
  corpus?: CanaryCorpus;
  status: "accepted" | "running" | "completed" | "failed";
  phase?: string;
  message?: string;
  progress?: number;
  metrics?: CanaryMetrics;
}

interface DryRunEncounterRow {
  encounter_id: string;
  patient_id: string;
  encounter_date: string | null;
  text: string | null;
  match_type?: string | null;
}

interface DryRunEntity {
  text: string;
  start: number;
  end: number;
  label: string;
}

interface DryRunResultRow {
  encounter_id: string;
  patient_id?: string | null;
  encounter_date?: string | null;
  text?: string | null;
  entities: DryRunEntity[];
}

interface EncounterWeight {
  candidate_id: string;
  label_id?: string;
  gold_count: number;
  pred_count: number;
  tp: number;
  fp: number;
  fn: number;
  doc_f1: number;
  error_contribution: number;
}

type DryRunMode = "ner_only" | "full_pipeline";
type ProvenanceStage =
  | "ner"
  | "post_processing_modified"
  | "post_processing_added"
  | "suppressed";

interface PipelineEntity extends DryRunEntity {
  assertion?: string;
  semantic_tag?: string;
  concept_id?: string;
  term?: string;
  score?: number;
  read_code?: string;
  __model_version?: string;
  _provenance_stage: ProvenanceStage;
  _provenance_detail?: string | null;
}

interface LayerTraceSummary {
  layer_id: string;
  name: string;
  status: string;
  before_count: number;
  after_count: number;
  added_count: number;
  removed_count: number;
  updated_count: number;
  duration_ms: number;
}

interface ExtractionModelSummary {
  requested_version: string;
  actual_version: string;
  actual_name?: string;
  version_mismatch: boolean;
}

interface PipelineTraceResultRow {
  encounter_id: string;
  patient_id?: string | null;
  encounter_date?: string | null;
  text?: string | null;
  final_entities: PipelineEntity[];
  suppressed_entities: PipelineEntity[];
  deduplicated_entities?: PipelineEntity[];
  layer_trace: LayerTraceSummary[];
  extraction_model?: ExtractionModelSummary;
  status?: string;
  errors?: string[];
  error?: string;
  failing_step?: string;
  step_count?: number;
  entity_counts?: {
    extraction?: number;
    final?: number;
    suppressed?: number;
    deduplicated?: number;
  };
}

const MODEL_CANARY_MIN_PRECISION = 0.78;
const MODEL_CANARY_MIN_RECALL = 0.72;
const DEFAULT_API_TIMEOUT_MS = 15000;
const DRY_RUN_API_TIMEOUT_MS = 180000;
const DRY_RUN_SEARCH_TIMEOUT_MS = 60000;

async function fetchWithTimeout(
  input: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_API_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException && error.name === "AbortError"
  ) || (
    error instanceof Error && error.name === "AbortError"
  );
}

function canonicalWordType(raw: string): string {
  const normalised = raw.replace(/[\s-]+/g, "_").toUpperCase();
  if (normalised === "OBSERVABLE" || normalised === "OBSERVABLE_ENTITY") {
    return "OBSERVABLE ENTITY";
  }
  return normalised.replace(/_/g, " ");
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

const SEARCH_HIGHLIGHT_STOPWORDS = new Set([
  "and", "or", "the", "a", "an", "of", "for", "to", "in", "on", "with",
  "is", "are", "was", "were", "be", "been", "by", "at", "as", "this",
  "that", "it", "from", "but", "not", "no",
]);

function buildHighlightTokens(
  query: string,
  expandedTerms: string[],
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const add = (raw: string) => {
    const trimmed = raw.trim();
    if (trimmed.length < 3) return;
    const key = trimmed.toLowerCase();
    if (SEARCH_HIGHLIGHT_STOPWORDS.has(key)) return;
    if (seen.has(key)) return;
    seen.add(key);
    out.push(trimmed);
  };
  for (const term of expandedTerms) {
    add(term);
    for (const word of term.split(/\s+/)) add(word);
  }
  for (const word of query.split(/\s+/)) add(word);
  // Sort longest-first so multi-word phrases match before their parts.
  return out.sort((a, b) => b.length - a.length);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderHighlightedText(
  text: string,
  tokens: string[],
): ReactNode {
  if (!text) return text;
  if (!tokens.length) return text;
  const pattern = new RegExp(
    `(${tokens.map(escapeRegExp).join("|")})`,
    "gi",
  );
  const parts = text.split(pattern);
  return parts.map((part, idx) => {
    if (idx % 2 === 1) {
      return (
        <mark
          key={`hl-${idx}`}
          data-testid="encounter-search-highlight"
          style={{
            backgroundColor: "rgba(255, 213, 79, 0.6)",
            color: "inherit",
            padding: "0 1px",
            borderRadius: 2,
          }}
        >
          {part}
        </mark>
      );
    }
    return <span key={`txt-${idx}`}>{part}</span>;
  });
}

function detailToString(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const rendered = detail
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") {
          const obj = entry as { msg?: unknown; loc?: unknown };
          const msg = typeof obj.msg === "string" ? obj.msg : JSON.stringify(entry);
          const loc = Array.isArray(obj.loc) ? obj.loc.join(".") : "";
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(entry);
      })
      .filter(Boolean)
      .join("; ");
    return rendered || null;
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return null;
}

function f1(precision: number | null | undefined, recall: number | null | undefined): number | null {
  if (precision === null || precision === undefined || recall === null || recall === undefined) return null;
  const denom = precision + recall;
  if (denom <= 0) return 0;
  return (2 * precision * recall) / denom;
}

function compareModelVersionsDesc(a: string, b: string): number {
  const an = a.replace(/[^0-9]/g, "");
  const bn = b.replace(/[^0-9]/g, "");
  if (an !== bn) return bn.localeCompare(an);
  return b.localeCompare(a);
}

const LABEL_COLORS: Record<string, { bg: string; fg: string }> = {
  "DISORDER":           { bg: "#FFF3E0", fg: "#E65100" },
  "FINDING":            { bg: "#FFF8E1", fg: "#BF360C" },
  "PROCEDURE":          { bg: "#E3F2FD", fg: "#1565C0" },
  "OBSERVABLE ENTITY":  { bg: "#E8F5E9", fg: "#2E7D32" },
  "SITUATION":          { bg: "#EDE7F6", fg: "#4527A0" },
  "MEDICATION":         { bg: "#FCE4EC", fg: "#880E4F" },
  "BODY SITE":          { bg: "#E0F7FA", fg: "#006064" },
};

function labelColor(label: string): { bg: string; fg: string } {
  const key = label.toUpperCase().replace(/_/g, " ");
  return LABEL_COLORS[key] ?? { bg: "#F5F5F5", fg: "#616161" };
}

function renderAnnotatedText(text: string, entities: DryRunEntity[]): ReactNode {
  const sorted = [...entities]
    .filter((e) => e.start >= 0 && e.end <= text.length && e.start < e.end)
    .sort((a, b) => a.start - b.start);
  if (!sorted.length) {
    return text;
  }

  const merged: AnnotatedSpan[] = [];
  let i = 0;
  while (i < sorted.length) {
    let unionEnd = sorted[i].end;
    const chips: TagTheme[] = [
      {
        ...themeForTag(sorted[i].label),
        label: sorted[i].label,
        entityText: text.slice(sorted[i].start, sorted[i].end),
      },
    ];

    let j = i + 1;
    while (j < sorted.length && sorted[j].start < unionEnd) {
      unionEnd = Math.max(unionEnd, sorted[j].end);
      chips.push({
        ...themeForTag(sorted[j].label),
        label: sorted[j].label,
        entityText: text.slice(sorted[j].start, sorted[j].end),
      });
      j += 1;
    }

    merged.push({ start: sorted[i].start, end: unionEnd, chips });
    i = j;
  }

  return renderNerSpans(text, merged);
}

const PROVENANCE_COLORS: Record<ProvenanceStage, { bg: string; fg: string }> = {
  ner: { bg: "#E3F2FD", fg: "#0D47A1" },
  post_processing_modified: { bg: "#FFF8E1", fg: "#E65100" },
  post_processing_added: { bg: "#E8F5E9", fg: "#1B5E20" },
  suppressed: { bg: "#FFEBEE", fg: "#B71C1C" },
};

function provenanceLabel(stage: ProvenanceStage): string {
  if (stage === "ner") return "NER";
  if (stage === "post_processing_modified") return "Pipeline modified";
  if (stage === "post_processing_added") return "Pipeline added";
  return "Suppressed";
}

function buildProvenanceChip(ent: PipelineEntity, text: string): TagTheme {
  const { bg, fg } = PROVENANCE_COLORS[ent._provenance_stage];
  const detail = ent._provenance_detail ? ` (${ent._provenance_detail})` : "";
  return {
    bg,
    border: fg,
    label: provenanceLabel(ent._provenance_stage),
    entityText: `${text.slice(ent.start, ent.end)} - ${ent.label}${detail}`,
  };
}

function renderProvenanceAnnotatedText(text: string, entities: PipelineEntity[]) {
  const sorted = [...entities]
    .filter((e) => e.start >= 0 && e.end <= text.length && e.start < e.end)
    .sort((a, b) => a.start - b.start);

  const merged: AnnotatedSpan[] = [];
  let i = 0;
  while (i < sorted.length) {
    let unionEnd = sorted[i].end;
    const chips: TagTheme[] = [buildProvenanceChip(sorted[i], text)];

    let j = i + 1;
    while (j < sorted.length && sorted[j].start < unionEnd) {
      unionEnd = Math.max(unionEnd, sorted[j].end);
      chips.push(buildProvenanceChip(sorted[j], text));
      j += 1;
    }

    merged.push({ start: sorted[i].start, end: unionEnd, chips });
    i = j;
  }

  return renderNerSpans(text, merged);
}

export function EvaluateStage({ jobs, latestJob, promotedVersion }: EvaluateStageProps) {
  const router = useRouter();
  const [versions, setVersions] = useState<ModelRecord[]>([]);
  const [activeModelVersion, setActiveModelVersion] = useState<string | null>(null);
  const [loadingRegistry, setLoadingRegistry] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [openingGoldEditor, setOpeningGoldEditor] = useState<string | null>(null);
  const [approveTarget, setApproveTarget] = useState<{
    encounterId: string;
    text: string;
    entities: DryRunEntity[];
  } | null>(null);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [perEncounterWeights, setPerEncounterWeights] = useState<
    Record<string, EncounterWeight | null>
  >({});
  const [sortByWeight, setSortByWeight] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [goldJobId, setGoldJobId] = useState<string | null>(null);
  const [goldJob, setGoldJob] = useState<CanaryJob | null>(null);
  const [forcePromoteConfirmOpen, setForcePromoteConfirmOpen] = useState(false);
  const [rejectConfirmVersion, setRejectConfirmVersion] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<string>("");
  const [canaryCorpus, setCanaryCorpus] = useState<CanaryCorpus>("full");
  const [holdbackCount, setHoldbackCount] = useState<number | null>(null);
  const [dryRunQuery, setDryRunQuery] = useState("");
  const [dryRunSearchTerms, setDryRunSearchTerms] = useState<string[]>([]);
  const dryRunHighlightTokens = useMemo(
    () => buildHighlightTokens(dryRunQuery, dryRunSearchTerms),
    [dryRunQuery, dryRunSearchTerms],
  );
  const [dryRunRows, setDryRunRows] = useState<DryRunEncounterRow[]>([]);
  const [selectedDryRun, setSelectedDryRun] = useState<Record<string, DryRunEncounterRow>>({});
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [dryRunRunning, setDryRunRunning] = useState(false);
  const [dryRunMode, setDryRunMode] = useState<DryRunMode>("ner_only");
  const [dryRunResults, setDryRunResults] = useState<DryRunResultRow[]>([]);
  const [pipelineTraceResults, setPipelineTraceResults] = useState<PipelineTraceResultRow[]>([]);
  const [dryRunDialogOpen, setDryRunDialogOpen] = useState(false);

  const doneJob = latestJob?.status === "done" ? latestJob : null;
  const targetVersion = doneJob?.model_version ?? null;

  const loadRegistry = useCallback(async () => {
    setLoadingRegistry(true);
    setError(null);
    try {
      const [versionsRes, statusRes] = await Promise.all([
        fetchWithTimeout("/api/model-registry/versions"),
        fetchWithTimeout("/api/model-registry/status"),
      ]);
      if (!versionsRes.ok) {
        const data = await versionsRes.json().catch(() => ({}));
        throw new Error(data.detail || `Could not load versions (${versionsRes.status})`);
      }
      if (!statusRes.ok) {
        const data = await statusRes.json().catch(() => ({}));
        throw new Error(data.detail || `Could not load status (${statusRes.status})`);
      }
      const versionsData = await versionsRes.json();
      const statusData = await statusRes.json();
      const sortedVersions = [...(versionsData.versions ?? [])].sort((a, b) =>
        compareModelVersionsDesc(
          String(a?.model_version ?? ""),
          String(b?.model_version ?? ""),
        ),
      );
      setVersions(sortedVersions);
      setActiveModelVersion(statusData.active_model?.model_version ?? null);
      try {
        const holdbackRes = await fetchWithTimeout(
          "/api/training/gold-labels/golden-set/stats",
        );
        if (holdbackRes.ok) {
          const holdbackData = await holdbackRes.json();
          setHoldbackCount(Number(holdbackData.total ?? 0));
        }
      } catch {
        setHoldbackCount(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not load model state.");
    } finally {
      setLoadingRegistry(false);
    }
  }, []);

  useEffect(() => {
    loadRegistry();
  }, [loadRegistry]);

  useEffect(() => {
    const preferredVersion = targetVersion ?? "";
    if (preferredVersion && versions.some((v) => v.model_version === preferredVersion)) {
      setSelectedVersion(preferredVersion);
      return;
    }
    if (!selectedVersion && versions.length > 0) {
      setSelectedVersion(versions[0].model_version);
    }
  }, [targetVersion, versions, selectedVersion]);

  useEffect(() => {
    if (!goldJobId) return;
    const timer = window.setInterval(async () => {
      try {
        const res = await fetchWithTimeout(
          `/api/model-registry/canary-jobs/${goldJobId}`,
        );
        if (!res.ok) return;
        const data = (await res.json()) as CanaryJob;
        setGoldJob(data);
        if (data.status === "completed" || data.status === "failed") {
          window.clearInterval(timer);
          setGoldJobId(null);
          await loadRegistry();
        }
      } catch {
        // ignore transient poll failures
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [goldJobId, loadRegistry]);

  const selectedRecord = useMemo(
    () => versions.find((v) => v.model_version === selectedVersion) ?? null,
    [selectedVersion, versions],
  );

  const canaryRecord = useMemo(() => {
    if (selectedRecord) return selectedRecord;
    if (!targetVersion) return null;
    return (
      versions.find((v) => v.model_version === targetVersion) ??
      versions.find((v) => v.status === "canary")
    );
  }, [selectedRecord, targetVersion, versions]);

  const canaryPass =
    (canaryRecord?.canary_precision ?? 0) >= MODEL_CANARY_MIN_PRECISION &&
    (canaryRecord?.canary_recall ?? 0) >= MODEL_CANARY_MIN_RECALL;

  const canRunSafetyTest =
    !!selectedRecord &&
    (selectedRecord.status === "offline_validated" || selectedRecord.status === "canary");
  const selectedNeedsTrainingGate =
    selectedRecord?.status === "registered" || selectedRecord?.status === "deprecated";
  const isSafetyTestRunning =
    !!goldJobId &&
    goldJob?.version === selectedVersion &&
    (goldJob.status === "accepted" || goldJob.status === "running");
  const safetyTestFailureMessage =
    goldJob?.version === selectedVersion && goldJob.status === "failed"
      ? (goldJob.message?.trim() || "The safety test stopped before it could finish.")
      : null;
  const hasHoldbackSet = holdbackCount == null ? true : holdbackCount > 0;

  const dryRunAllLabels = useMemo(
    () =>
      Array.from(
        new Set(dryRunResults.flatMap((r) => r.entities.map((e) => e.label))),
      ).sort(),
    [dryRunResults],
  );
  const nerOnlyTotalEntities = useMemo(
    () => dryRunResults.reduce((sum, row) => sum + row.entities.length, 0),
    [dryRunResults],
  );
  const pipelineStageCounts = useMemo(() => {
    const counts: Record<ProvenanceStage, number> = {
      ner: 0,
      post_processing_modified: 0,
      post_processing_added: 0,
      suppressed: 0,
    };
    for (const row of pipelineTraceResults) {
      for (const ent of row.final_entities) {
        counts[ent._provenance_stage] += 1;
      }
      counts.suppressed += row.suppressed_entities.length;
    }
    return counts;
  }, [pipelineTraceResults]);
  const pipelineDeduplicatedCount = useMemo(
    () =>
      pipelineTraceResults.reduce(
        (sum, row) => sum + (row.deduplicated_entities?.length ?? 0),
        0,
      ),
    [pipelineTraceResults],
  );

  const hasPerEncounterWeights = useMemo(
    () => Object.values(perEncounterWeights).some((w) => w !== null),
    [perEncounterWeights],
  );

  const sortedDryRunResults = useMemo(() => {
    if (!sortByWeight) return dryRunResults;
    return [...dryRunResults].sort((a, b) => {
      const wa = perEncounterWeights[a.encounter_id]?.error_contribution ?? -1;
      const wb = perEncounterWeights[b.encounter_id]?.error_contribution ?? -1;
      return wb - wa;
    });
  }, [dryRunResults, perEncounterWeights, sortByWeight]);

  const sortedPipelineTraceResults = useMemo(() => {
    if (!sortByWeight) return pipelineTraceResults;
    return [...pipelineTraceResults].sort((a, b) => {
      const wa = perEncounterWeights[a.encounter_id]?.error_contribution ?? -1;
      const wb = perEncounterWeights[b.encounter_id]?.error_contribution ?? -1;
      return wb - wa;
    });
  }, [pipelineTraceResults, perEncounterWeights, sortByWeight]);

  const canaryPerLabelRows = useMemo(() => {
    const rows = goldJob?.metrics?.per_label ?? [];
    const grouped = new Map<string, {
      tp: number;
      fp: number;
      fn: number;
      precisionSum: number;
      recallSum: number;
      f1Sum: number;
      count: number;
      hasCounts: boolean;
    }>();
    for (const row of rows) {
      const key = canonicalWordType(row.label);
      const current = grouped.get(key) ?? {
        tp: 0,
        fp: 0,
        fn: 0,
        precisionSum: 0,
        recallSum: 0,
        f1Sum: 0,
        count: 0,
        hasCounts: false,
      };
      if (row.tp != null && row.fp != null && row.fn != null) {
        current.tp += row.tp;
        current.fp += row.fp;
        current.fn += row.fn;
        current.hasCounts = true;
      }
      current.precisionSum += row.precision;
      current.recallSum += row.recall;
      current.f1Sum += row.f1;
      current.count += 1;
      grouped.set(key, current);
    }
    const merged = Array.from(grouped.entries()).map(([label, counts]) => {
      const precision = counts.hasCounts
        ? (counts.tp + counts.fp > 0 ? counts.tp / (counts.tp + counts.fp) : 0)
        : counts.precisionSum / Math.max(counts.count, 1);
      const recall = counts.hasCounts
        ? (counts.tp + counts.fn > 0 ? counts.tp / (counts.tp + counts.fn) : 0)
        : counts.recallSum / Math.max(counts.count, 1);
      const score = counts.hasCounts
        ? (f1(precision, recall) ?? 0)
        : counts.f1Sum / Math.max(counts.count, 1);
      return { label, precision, recall, f1: score };
    });
    return merged.sort((a, b) => b.f1 - a.f1 || a.label.localeCompare(b.label));
  }, [goldJob]);

  const runGoldTest = useCallback(async (version: string, corpus: CanaryCorpus) => {
    if (corpus === "holdback" && !hasHoldbackSet) {
      setError("No holdback gold labels found. Freeze labels in Training Data first.");
      return;
    }
    setBusyAction(`run-gold:${version}`);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `/api/model-registry/versions/${version}/canary/run-gold`,
        {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corpus }),
        },
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(
        `Safety test started for version ${version} (${corpus === "holdback" ? "holdback set" : "full set"}).`,
      );
      setGoldJobId(data.job_id);
      setGoldJob({
        job_id: data.job_id,
        version,
        corpus,
        status: "accepted",
        phase: "queued",
        message: "Queued",
      });
      await loadRegistry();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not start the safety test.");
    } finally {
      setBusyAction(null);
    }
  }, [hasHoldbackSet, loadRegistry]);

  const searchDryRunEncounters = useCallback(async () => {
    const q = dryRunQuery.trim();
    if (!q) {
      setDryRunRows([]);
      setSelectedDryRun({});
      setDryRunSearchTerms([]);
      return;
    }
    setDryRunLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        q,
        page: "1",
        page_size: "20",
        max_results: "100",
        min_combined_score: "0",
        require_keyword_anchor: "false",
      });
      const res = await fetchWithTimeout(
        `/api/proxy/analytics/mission-control/encounters?${params.toString()}`,
        undefined,
        DRY_RUN_SEARCH_TIMEOUT_MS,
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailToString(data.detail) || `Failed (${res.status})`);
      const items = Array.isArray(data.items) ? data.items : [];
      const rows: DryRunEncounterRow[] = items.map((item: DryRunEncounterRow) => ({
        encounter_id: item.encounter_id,
        patient_id: item.patient_id,
        encounter_date: item.encounter_date,
        text: item.text,
        match_type: item.match_type ?? null,
      }));
      const diagnostics = (data?.query_diagnostics ?? {}) as Record<string, unknown>;
      const expanded = Array.isArray(diagnostics.expanded_terms)
        ? (diagnostics.expanded_terms as unknown[]).map(String).filter(Boolean)
        : [];
      const synonyms = Array.isArray(diagnostics.clinical_synonyms)
        ? (diagnostics.clinical_synonyms as unknown[]).map(String).filter(Boolean)
        : [];
      const allTerms = [...expanded, ...synonyms];
      setDryRunSearchTerms(allTerms.length > 0 ? allTerms : [q]);
      setDryRunRows(rows);
      setSelectedDryRun({});
      setDryRunResults([]);
      setPipelineTraceResults([]);
      if (rows.length > 0) setDryRunDialogOpen(true);
    } catch (e: unknown) {
      if (isAbortError(e)) {
        setError("Search took too long and timed out. Try a more specific query or run search again.");
        return;
      }
      setError(e instanceof Error ? e.message : "Could not search encounters.");
    } finally {
      setDryRunLoading(false);
    }
  }, [dryRunQuery]);

  const runDryRun = useCallback(async () => {
    const picks = Object.values(selectedDryRun).slice(0, 20);
    if (!selectedVersion || picks.length === 0) return;
    const usablePicks = picks.filter((row) => (row.text ?? "").trim().length > 0);
    if (usablePicks.length === 0) {
      setError("The selected encounters have no text available for preview. Choose encounters with visible text content.");
      return;
    }
    setDryRunRunning(true);
    setError(null);
    setInfo(null);
    setDryRunResults([]);
    setPipelineTraceResults([]);
    try {
      const endpoint = dryRunMode === "full_pipeline" ? "worker-trace" : "dry-run";
      const res = await fetchWithTimeout(
        `/api/model-registry/versions/${selectedVersion}/canary/${endpoint}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            encounters: usablePicks.map((row) => ({
              encounter_id: row.encounter_id,
              patient_id: row.patient_id,
              encounter_date: row.encounter_date,
              text: row.text ?? "",
            })),
          }),
        },
        DRY_RUN_API_TIMEOUT_MS,
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailToString(data.detail) || `Failed (${res.status})`);
      if (dryRunMode === "full_pipeline") {
        setPipelineTraceResults(Array.isArray(data.encounters) ? data.encounters : []);
      } else {
        setDryRunResults(Array.isArray(data.encounters) ? data.encounters : []);
      }
      const count = Array.isArray(data.encounters) ? data.encounters.length : 0;
      setInfo(`${dryRunMode === "full_pipeline" ? "Full pipeline trace" : "NER preview"} finished for ${count} encounter${count === 1 ? "" : "s"}.`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not run dry run.");
    } finally {
      setDryRunRunning(false);
    }
  }, [dryRunMode, selectedDryRun, selectedVersion]);

  const openInGoldEditor = useCallback(
    async (encounterId: string, text: string, entities: DryRunEntity[]) => {
      if (!encounterId || !text.trim()) {
        setError("This encounter has no text to send to the gold editor.");
        return;
      }
      setOpeningGoldEditor(encounterId);
      setError(null);
      try {
        const res = await fetchWithTimeout(
          "/api/training/candidates/from-dry-run",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              encounter_text: text,
              entities,
              source_hint: `dry_run:${encounterId.slice(0, 12)}`,
            }),
          },
        );
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(detailToString(data.detail) || `Failed (${res.status})`);
        }
        const labelId = typeof data.label_id === "string" ? data.label_id : "";
        if (!labelId) {
          throw new Error("Gold editor did not return a label id.");
        }
        const editorUrl =
          `/admin/gold-dataset?labelId=${encodeURIComponent(labelId)}&from=dry_run`;
        const opened = window.open(editorUrl, "_blank", "noopener,noreferrer");
        if (!opened) {
          // Pop-up blocker prevented opening - fall back to in-place navigation
          // so the user still gets to the editor instead of seeing nothing.
          router.push(editorUrl);
          return;
        }
        setInfo(
          "Opened this encounter in the gold editor in a new tab. Your dry-run results are still here.",
        );
      } catch (e: unknown) {
        setError(
          e instanceof Error
            ? e.message
            : "Could not open this encounter in the gold editor.",
        );
      } finally {
        setOpeningGoldEditor(null);
      }
    },
    [router],
  );

  useEffect(() => {
    const rowsForLookup: Array<{ encounter_id: string; text: string }> = [];
    const seen = new Set<string>();
    const collect = (encounterId: string, text?: string | null) => {
      const trimmed = (text ?? "").trim();
      if (!encounterId || !trimmed || seen.has(encounterId)) return;
      seen.add(encounterId);
      rowsForLookup.push({ encounter_id: encounterId, text: trimmed });
    };
    for (const row of dryRunResults) {
      collect(
        row.encounter_id,
        row.text ?? selectedDryRun[row.encounter_id]?.text,
      );
    }
    for (const row of pipelineTraceResults) {
      collect(
        row.encounter_id,
        row.text ?? selectedDryRun[row.encounter_id]?.text,
      );
    }
    if (rowsForLookup.length === 0) {
      setPerEncounterWeights({});
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchWithTimeout(
          "/api/training/per-encounter-weights/lookup",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              encounters: rowsForLookup,
              version: selectedVersion || null,
            }),
          },
        );
        if (!res.ok) return;
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;
        const weights = (data?.weights ?? {}) as Record<string, EncounterWeight | null>;
        setPerEncounterWeights(weights);
      } catch {
        // Soft-fail: weights are an enhancement, not required.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dryRunResults, pipelineTraceResults, selectedDryRun, selectedVersion]);

  const requestApproveAsGold = useCallback(
    (encounterId: string, text: string, entities: DryRunEntity[]) => {
      if (!encounterId || !text.trim()) {
        setError("This encounter has no text to approve as gold.");
        return;
      }
      if (!entities.length) {
        setError("No entities to approve. Open in editor to add labels first.");
        return;
      }
      setApproveError(null);
      setApproveTarget({ encounterId, text, entities });
    },
    [],
  );

  const cancelApproveAsGold = useCallback(() => {
    setApproveTarget(null);
    setApproveError(null);
  }, []);

  const confirmApproveAsGold = useCallback(async () => {
    if (!approveTarget) return;
    const { encounterId, text, entities } = approveTarget;
    setApproving(true);
    setApproveError(null);
    try {
      const res = await fetchWithTimeout(
        "/api/training/gold-labels/approve-from-dry-run",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            encounter_text: text,
            entities,
            expected_entity_count: entities.length,
            source_hint: `dry_run:${encounterId.slice(0, 12)}`,
          }),
        },
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          detailToString(data.detail) ||
          `Could not approve as gold (${res.status}).`;
        if (res.status === 409) {
          throw new Error(
            `${msg} Use the pencil button to open this row in the editor.`,
          );
        }
        throw new Error(msg);
      }
      setApproveTarget(null);
      const count =
        typeof data.entity_count === "number" ? data.entity_count : entities.length;
      setInfo(
        `Approved ${count} ${count === 1 ? "entity" : "entities"} as gold for encounter ${encounterId.slice(0, 8)}...`,
      );
    } catch (e: unknown) {
      setApproveError(
        e instanceof Error
          ? e.message
          : "Could not approve this encounter as gold.",
      );
    } finally {
      setApproving(false);
    }
  }, [approveTarget]);

  const promote = useCallback(async (version: string, force = false) => {
    setBusyAction(`promote:${version}`);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `/api/model-registry/versions/${version}/promote`,
        {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rollback_target_version: activeModelVersion,
          force,
          force_reason: force ? "Manual override from Evaluate stage." : "",
        }),
        },
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`Version ${version} is now live.`);
      setForcePromoteConfirmOpen(false);
      await loadRegistry();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not make this AI live.");
    } finally {
      setBusyAction(null);
    }
  }, [activeModelVersion, loadRegistry]);

  const reject = useCallback(async (version: string) => {
    setRejectConfirmVersion(null);
    setBusyAction(`reject:${version}`);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `/api/model-registry/versions/${version}/reject`,
        {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Rejected after safety test in Evaluate stage" }),
        },
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Failed (${res.status})`);
      setInfo(`Version ${version} has been rejected.`);
      await loadRegistry();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not reject this version.");
    } finally {
      setBusyAction(null);
    }
  }, [loadRegistry]);

  return (
    <Box sx={{ pt: 2, display: "flex", flexDirection: "column", gap: 2 }}>
      {loadingRegistry && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}
      {info && (
        <Alert severity="success" onClose={() => setInfo(null)}>
          {info}
        </Alert>
      )}

      {/* Section 1 -- Training scores */}
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        1) Check learning scores
      </Typography>
      {doneJob && (
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
          <ScoreCard label="Precision" value={doneJob.precision} pass={(doneJob.precision ?? 0) >= 0.8} />
          <ScoreCard label="Recall" value={doneJob.recall} pass={(doneJob.recall ?? 0) >= 0.75} />
          <ScoreCard label="F1" value={doneJob.f1} pass={(doneJob.f1 ?? 0) >= 0.77} />
          {doneJob.golden_f1 != null && (
            <ScoreCard
              label="Golden F1"
              value={doneJob.golden_f1}
              pass={doneJob.golden_passed ?? false}
              locked
            />
          )}
        </Box>
      )}
      {!doneJob && (
        <Alert severity="info">
          Finish a training run first. Then this page will show learning scores and next steps.
        </Alert>
      )}

      {doneJob?.per_label_f1 && Object.keys(doneJob.per_label_f1).length > 0 && (
        <PerLabelChart perLabel={doneJob.per_label_f1} />
      )}
      {jobs.length > 1 && <RegressionTable jobs={jobs} />}

      {/* Section 2 -- Safety test */}
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        2) Run safety test
      </Typography>
      {versions.length > 0 && (
        <FormControl size="small" sx={{ minWidth: 260, maxWidth: 360 }}>
          <InputLabel id="evaluate-version-label">Choose version</InputLabel>
          <Select
            labelId="evaluate-version-label"
            value={selectedVersion}
            label="Choose version"
            onChange={(e) => setSelectedVersion(e.target.value)}
          >
            {versions.map((v) => (
              <MenuItem key={v.model_version} value={v.model_version}>
                {v.model_version}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}
      {!doneJob && (
        <Alert severity="info">No training result yet to test.</Alert>
      )}
      {selectedNeedsTrainingGate && (
        <Alert severity="warning">
          This version is not ready for safety testing yet. Complete and validate training first.
        </Alert>
      )}
      {canRunSafetyTest && selectedVersion && (
        <Card variant="outlined">
          <Box sx={{ p: 1.5 }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
              Version <strong>{selectedVersion}</strong>
            </Typography>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <FormControl size="small" sx={{ minWidth: 190 }}>
                <InputLabel id="safety-corpus-label">Safety test scope</InputLabel>
                <Select
                  labelId="safety-corpus-label"
                  value={canaryCorpus}
                  label="Safety test scope"
                  onChange={(e) => setCanaryCorpus(e.target.value as CanaryCorpus)}
                  disabled={isSafetyTestRunning}
                >
                  <MenuItem value="full">Full gold dataset</MenuItem>
                  <MenuItem value="holdback" disabled={!hasHoldbackSet}>
                    {hasHoldbackSet
                      ? `Holdback set only${holdbackCount != null ? ` (${holdbackCount})` : ""}`
                      : "Holdback set only (none available)"}
                  </MenuItem>
                </Select>
              </FormControl>
              <Button
                variant="contained"
                onClick={() => runGoldTest(selectedVersion, canaryCorpus)}
                disabled={busyAction === `run-gold:${selectedVersion}` || isSafetyTestRunning}
              >
                {busyAction === `run-gold:${selectedVersion}`
                  ? <CircularProgress aria-label="Loading" size={16} />
                  : "Run safety test"}
              </Button>
            </Box>
            {!hasHoldbackSet && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                Holdback testing is unavailable until at least one label is frozen in Training Data.
              </Typography>
            )}
            {isSafetyTestRunning && (
              <Box sx={{ mt: 1.5 }}>
                <Typography variant="body2" sx={{ mb: 0.5 }}>
                  {goldJob?.phase === "downloading_model"
                    ? "Getting the AI ready..."
                    : goldJob?.phase === "loading_gold_data"
                      ? "Loading checked patient records..."
                      : goldJob?.phase === "scoring"
                        ? `Testing now${goldJob.progress != null ? ` - ${Math.round(goldJob.progress * 100)}% done` : "..."}`
                        : goldJob?.message ?? "Running safety test..."}
                </Typography>
                <LinearProgress
                  variant={goldJob?.progress != null ? "determinate" : "indeterminate"}
                  value={(goldJob?.progress ?? 0) * 100}
                  aria-label="Safety test progress"
                />
              </Box>
            )}
            {!isSafetyTestRunning && canaryRecord?.canary_precision === null && canaryRecord?.status === "canary" && (
              <Alert severity={safetyTestFailureMessage ? "error" : "warning"} sx={{ mt: 1.5 }}>
                {safetyTestFailureMessage
                  ? `Safety test failed: ${safetyTestFailureMessage}`
                  : "The previous safety test may have stopped early. Run it again."}
              </Alert>
            )}
          </Box>
        </Card>
      )}

      {/* Section 2b -- Dry run preview */}
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        2b) Dry run on real encounters
      </Typography>
      <Card variant="outlined">
        <Box sx={{ p: 1.5, display: "flex", flexDirection: "column", gap: 1.25 }}>
          <Typography variant="body2" color="text.secondary">
            Search for real patient encounters, read the full text, select the ones you want to test, then run the model.
          </Typography>

          {/* Search row */}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <TextField
              size="small"
              label="Search encounter text"
              value={dryRunQuery}
              onChange={(e) => setDryRunQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void searchDryRunEncounters();
                }
              }}
              fullWidth
            />
            <Button
              variant="outlined"
              onClick={() => void searchDryRunEncounters()}
              disabled={dryRunLoading}
              sx={{ whiteSpace: "nowrap" }}
            >
              {dryRunLoading ? <CircularProgress aria-label="Loading" size={16} /> : "Search"}
            </Button>
          </Stack>

          {/* Selection summary + run button */}
          {Object.keys(selectedDryRun).length > 0 && (
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ xs: "flex-start", sm: "center" }}>
              <Typography variant="body2">
                {Object.keys(selectedDryRun).length} encounter{Object.keys(selectedDryRun).length !== 1 ? "s" : ""} selected
              </Typography>
              <Button size="small" onClick={() => setDryRunDialogOpen(true)}>Change</Button>
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel id="dry-run-mode-label">Preview mode</InputLabel>
                <Select
                  labelId="dry-run-mode-label"
                  value={dryRunMode}
                  label="Preview mode"
                  onChange={(e) => setDryRunMode(e.target.value as DryRunMode)}
                  disabled={dryRunRunning}
                >
                  <MenuItem value="ner_only">NER only</MenuItem>
                  <MenuItem value="full_pipeline">Full pipeline trace</MenuItem>
                </Select>
              </FormControl>
              <Button
                variant="contained"
                size="small"
                onClick={() => void runDryRun()}
                disabled={dryRunRunning || !selectedVersion}
              >
                {dryRunRunning
                  ? <CircularProgress aria-label="Loading" size={14} />
                  : dryRunMode === "full_pipeline"
                    ? "Run full pipeline"
                    : "Run NER preview"}
              </Button>
            </Stack>
          )}

          {dryRunMode === "ner_only" && dryRunResults.length > 0 && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              {nerOnlyTotalEntities === 0 && (
                <Alert severity="warning">
                  No entities were found in NER-only preview. Re-run this encounter in Full pipeline trace to verify model version and extraction path.
                </Alert>
              )}
              {/* Legend */}
              {dryRunAllLabels.length > 0 && (
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, alignItems: "center" }}>
                  <Typography variant="caption" color="text.secondary" sx={{ mr: 0.25 }}>
                    Entity types:
                  </Typography>
                  {dryRunAllLabels.map((lbl) => {
                    const { bg, fg } = labelColor(lbl);
                    return (
                      <Box
                        key={lbl}
                        sx={{ backgroundColor: bg, color: fg, border: `1px solid ${fg}55`, borderRadius: 1, px: 0.75, py: 0.25, fontSize: 11, fontWeight: 600 }}
                      >
                        {lbl}
                      </Box>
                    );
                  })}
                </Box>
              )}

              {/* Sort by error impact (only when canary weights are available) */}
              {hasPerEncounterWeights && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    Sort:
                  </Typography>
                  <Button
                    size="small"
                    variant={sortByWeight ? "contained" : "outlined"}
                    onClick={() => setSortByWeight((v) => !v)}
                    aria-pressed={sortByWeight}
                    aria-label="Sort dry-run rows by error impact on the latest canary"
                  >
                    {sortByWeight ? "By error impact (on)" : "By error impact"}
                  </Button>
                </Box>
              )}

              {/* Per-encounter annotated text (de-identified server-side) */}
              {sortedDryRunResults.map((row) => {
                const originalRow = selectedDryRun[row.encounter_id];
                const text = (row.text ?? originalRow?.text ?? "");
                const weight = perEncounterWeights[row.encounter_id] ?? null;
                const entityCountByLabel = row.entities.reduce<Record<string, number>>((acc, e) => {
                  acc[e.label] = (acc[e.label] ?? 0) + 1;
                  return acc;
                }, {});
                return (
                  <Paper key={row.encounter_id} variant="outlined" sx={{ p: 1.5 }}>
                    {/* Encounter header */}
                    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
                      <Box sx={{ display: "flex", gap: 1, alignItems: "baseline", flexWrap: "wrap" }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, fontFamily: "monospace", fontSize: 11 }}>
                          {row.encounter_id.slice(0, 8)}&hellip;
                        </Typography>
                        {row.encounter_date && (
                          <Typography variant="caption" color="text.secondary">{row.encounter_date}</Typography>
                        )}
                        {row.patient_id && (
                          <Typography variant="caption" color="text.secondary">Patient {row.patient_id}</Typography>
                        )}
                      </Box>
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        {weight && (
                          <Tooltip
                            title={`Latest canary: ${weight.tp} correct, ${weight.fp} extra, ${weight.fn} missed. Fixing this row contributes ${(weight.error_contribution * 100).toFixed(1)}% of the model's measured errors.`}
                          >
                            <Chip
                              size="small"
                              data-testid="encounter-weight-chip"
                              label={`error weight ${(weight.error_contribution * 100).toFixed(1)}%`}
                              color={weight.error_contribution >= 0.05 ? "warning" : "default"}
                              sx={{ height: 18, fontSize: "0.65rem" }}
                            />
                          </Tooltip>
                        )}
                        <Typography variant="caption" color={row.entities.length > 0 ? "success.main" : "text.disabled"} sx={{ whiteSpace: "nowrap" }}>
                          {row.entities.length} {row.entities.length === 1 ? "entity" : "entities"}
                        </Typography>
                        <Tooltip title="Open this encounter in the gold editor in a new tab so you can fix labels without losing your dry-run results.">
                          <span>
                            <IconButton
                              size="small"
                              aria-label="Open in gold editor (new tab)"
                              disabled={!text.trim() || openingGoldEditor === row.encounter_id}
                              onClick={() =>
                                openInGoldEditor(row.encounter_id, text, row.entities)
                              }
                            >
                              {openingGoldEditor === row.encounter_id ? (
                                <CircularProgress size={16} aria-label="Loading" />
                              ) : (
                                <EditNoteIcon fontSize="small" />
                              )}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Approve this extraction as gold training data without opening the editor. A confirmation dialog will show every entity first.">
                          <span>
                            <IconButton
                              size="small"
                              color="success"
                              aria-label="Approve dry-run extraction as gold"
                              disabled={
                                !text.trim() ||
                                row.entities.length === 0 ||
                                approving ||
                                approveTarget?.encounterId === row.encounter_id
                              }
                              onClick={() =>
                                requestApproveAsGold(row.encounter_id, text, row.entities)
                              }
                            >
                              <CheckCircleIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    </Box>

                    {/* Annotated text or fallback */}
                    {row.entities.length === 0 ? (
                      <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
                        No entities found in this encounter.
                      </Typography>
                    ) : text ? (
                      <Typography
                        component="p"
                        variant="body2"
                        sx={{ lineHeight: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                      >
                        {renderAnnotatedText(text, row.entities)}
                      </Typography>
                    ) : (
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                        {row.entities.map((ent, idx) => {
                          const { bg, fg } = labelColor(ent.label);
                          return (
                            <Chip
                              key={`${row.encounter_id}-${idx}`}
                              size="small"
                              label={`${ent.text} (${ent.label})`}
                              sx={{ bgcolor: bg, color: fg }}
                            />
                          );
                        })}
                      </Box>
                    )}

                    {/* Per-label count summary */}
                    {row.entities.length > 0 && (
                      <Box sx={{ mt: 1.25, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                        {Object.entries(entityCountByLabel).map(([lbl, count]) => {
                          const { bg, fg } = labelColor(lbl);
                          return (
                            <Box
                              key={lbl}
                              sx={{ backgroundColor: bg, color: fg, border: `1px solid ${fg}55`, borderRadius: 1, px: 0.75, py: 0.25, fontSize: 11 }}
                            >
                              {count} {lbl}
                            </Box>
                          );
                        })}
                      </Box>
                    )}
                    {row.entities.length > 0 && (
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                          Extracted entities:
                        </Typography>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                          {row.entities.map((ent, idx) => (
                            <Chip
                              key={`${row.encounter_id}-raw-${idx}`}
                              size="small"
                              label={`${ent.text} (${ent.label})`}
                              variant="outlined"
                            />
                          ))}
                        </Box>
                      </Box>
                    )}
                  </Paper>
                );
              })}
            </Box>
          )}
          {dryRunMode === "full_pipeline" && pipelineTraceResults.length > 0 && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, alignItems: "center" }}>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.25 }}>
                  Stage tags:
                </Typography>
                {(Object.keys(PROVENANCE_COLORS) as ProvenanceStage[]).map((stage) => {
                  const { bg, fg } = PROVENANCE_COLORS[stage];
                  return (
                    <Box
                      key={stage}
                      sx={{ backgroundColor: bg, color: fg, border: `1px solid ${fg}55`, borderRadius: 1, px: 0.75, py: 0.25, fontSize: 11, fontWeight: 600 }}
                    >
                      {provenanceLabel(stage)} ({pipelineStageCounts[stage]})
                    </Box>
                  );
                })}
                {pipelineDeduplicatedCount > 0 && (
                  <Box
                    sx={{
                      backgroundColor: "#ECEFF1",
                      color: "#37474F",
                      border: "1px solid #90A4AE55",
                      borderRadius: 1,
                      px: 0.75,
                      py: 0.25,
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  >
                    Deduplicated ({pipelineDeduplicatedCount})
                  </Box>
                )}
              </Box>
              {sortedPipelineTraceResults.map((row) => {
                const originalRow = selectedDryRun[row.encounter_id];
                const text = (row.text ?? originalRow?.text ?? "");
                const weight = perEncounterWeights[row.encounter_id] ?? null;
                const terminologyResolved = row.final_entities.filter((e) => !!e.concept_id).length;
                const extractedVersions = Array.from(
                  new Set(
                    row.final_entities
                      .map((e) => String(e.__model_version ?? "").trim())
                      .filter((v) => v.length > 0),
                  ),
                );
                const requestedModelVersion =
                  row.extraction_model?.requested_version?.trim() || selectedVersion;
                const extractedModelVersion =
                  row.extraction_model?.actual_version?.trim() || extractedVersions.join(", ");
                const extractedModelName = row.extraction_model?.actual_name?.trim() || "";
                const modelVersionMismatch = !!row.extraction_model?.version_mismatch;
                const stageCounts = row.final_entities.reduce<Record<string, number>>((acc, ent) => {
                  const key = ent._provenance_stage;
                  acc[key] = (acc[key] ?? 0) + 1;
                  return acc;
                }, {});
                return (
                  <Paper key={row.encounter_id} variant="outlined" sx={{ p: 1.5 }}>
                    {(row.error || (Array.isArray(row.errors) && row.errors.length > 0)) && (
                      <Alert severity="warning" sx={{ mb: 1 }}>
                        {row.error || row.errors?.join("; ")}
                        {(row.failing_step || row.step_count != null) && (
                          <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
                            {row.failing_step ? `Failed step: ${row.failing_step}. ` : ""}
                            {row.step_count != null ? `Steps executed: ${row.step_count}.` : ""}
                          </Typography>
                        )}
                      </Alert>
                    )}
                    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
                      <Box sx={{ display: "flex", gap: 1, alignItems: "baseline", flexWrap: "wrap" }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, fontFamily: "monospace", fontSize: 11 }}>
                          {row.encounter_id.slice(0, 8)}&hellip;
                        </Typography>
                        {row.encounter_date && (
                          <Typography variant="caption" color="text.secondary">{row.encounter_date}</Typography>
                        )}
                        {row.patient_id && (
                          <Typography variant="caption" color="text.secondary">Patient {row.patient_id}</Typography>
                        )}
                      </Box>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        {weight && (
                          <Tooltip
                            title={`Latest canary: ${weight.tp} correct, ${weight.fp} extra, ${weight.fn} missed. Fixing this row contributes ${(weight.error_contribution * 100).toFixed(1)}% of the model's measured errors.`}
                          >
                            <Chip
                              size="small"
                              data-testid="encounter-weight-chip"
                              label={`error weight ${(weight.error_contribution * 100).toFixed(1)}%`}
                              color={weight.error_contribution >= 0.05 ? "warning" : "default"}
                              sx={{ height: 18, fontSize: "0.65rem" }}
                            />
                          </Tooltip>
                        )}
                        <Chip
                          size="small"
                          color="info"
                          label={`${row.final_entities.length} final entities`}
                        />
                        <Chip
                          size="small"
                          color="success"
                          label={`${terminologyResolved} SNOMED resolved`}
                        />
                        <Tooltip title="Open this encounter in the gold editor in a new tab so you can fix labels without losing your dry-run results.">
                          <span>
                            <IconButton
                              size="small"
                              aria-label="Open in gold editor (new tab)"
                              disabled={!text.trim() || openingGoldEditor === row.encounter_id}
                              onClick={() =>
                                openInGoldEditor(
                                  row.encounter_id,
                                  text,
                                  row.final_entities,
                                )
                              }
                            >
                              {openingGoldEditor === row.encounter_id ? (
                                <CircularProgress size={16} aria-label="Loading" />
                              ) : (
                                <EditNoteIcon fontSize="small" />
                              )}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Approve this extraction as gold training data without opening the editor. A confirmation dialog will show every entity first.">
                          <span>
                            <IconButton
                              size="small"
                              color="success"
                              aria-label="Approve dry-run extraction as gold"
                              disabled={
                                !text.trim() ||
                                row.final_entities.length === 0 ||
                                approving ||
                                approveTarget?.encounterId === row.encounter_id
                              }
                              onClick={() =>
                                requestApproveAsGold(
                                  row.encounter_id,
                                  text,
                                  row.final_entities,
                                )
                              }
                            >
                              <CheckCircleIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    </Box>
                    {(requestedModelVersion || extractedModelVersion) && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                        Requested model: {requestedModelVersion || "unknown"} - Extracted with: {extractedModelVersion || "unknown"}
                        {extractedModelName ? ` (${extractedModelName})` : ""}
                      </Typography>
                    )}
                    {modelVersionMismatch && (
                      <Alert severity="error" sx={{ mb: 0.75 }}>
                        Model version mismatch: requested {requestedModelVersion || "unknown"} but extraction used {extractedModelVersion || "unknown"}.
                      </Alert>
                    )}
                    {row.entity_counts && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                        Entity counts - extraction: {row.entity_counts.extraction ?? 0}, final: {row.entity_counts.final ?? 0}, suppressed: {row.entity_counts.suppressed ?? 0}, deduplicated: {row.entity_counts.deduplicated ?? 0}
                      </Typography>
                    )}

                    {row.final_entities.length === 0 ? (
                      <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
                        No entities remained after pipeline processing.
                      </Typography>
                    ) : text ? (
                      <Typography
                        component="p"
                        variant="body2"
                        sx={{ lineHeight: 2, fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                      >
                        {renderProvenanceAnnotatedText(text, row.final_entities)}
                      </Typography>
                    ) : (
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                        {row.final_entities.map((ent, idx) => {
                          const { bg, fg } = PROVENANCE_COLORS[ent._provenance_stage];
                          return (
                            <Chip
                              key={`${row.encounter_id}-${idx}`}
                              size="small"
                              label={`${ent.text} (${ent.label})`}
                              sx={{ bgcolor: bg, color: fg }}
                            />
                          );
                        })}
                      </Box>
                    )}

                    <Box sx={{ mt: 1.25, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                      {(Object.keys(stageCounts) as ProvenanceStage[]).map((stage) => {
                        const { bg, fg } = PROVENANCE_COLORS[stage];
                        return (
                          <Box
                            key={stage}
                            sx={{ backgroundColor: bg, color: fg, border: `1px solid ${fg}55`, borderRadius: 1, px: 0.75, py: 0.25, fontSize: 11 }}
                          >
                            {stageCounts[stage]} {provenanceLabel(stage)}
                          </Box>
                        );
                      })}
                    </Box>
                    {row.final_entities.length > 0 && (
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                          Final entities:
                        </Typography>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                          {row.final_entities.map((ent, idx) => (
                            <Chip
                              key={`${row.encounter_id}-final-${idx}`}
                              size="small"
                              variant="outlined"
                              label={ent.concept_id
                                ? `${ent.text} (${ent.label}) - ${ent.concept_id}`
                                : `${ent.text} (${ent.label})`}
                            />
                          ))}
                        </Box>
                      </Box>
                    )}

                    {row.suppressed_entities.length > 0 && (
                      <Alert severity="warning" sx={{ mt: 1.25 }}>
                        <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
                          Suppressed by pipeline ({row.suppressed_entities.length}):
                        </Typography>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                          {row.suppressed_entities.map((ent, idx) => (
                            <Chip
                              key={`${row.encounter_id}-supp-${idx}`}
                              size="small"
                              label={`${ent.text} (${ent.label})`}
                              color="error"
                              variant="outlined"
                            />
                          ))}
                        </Box>
                      </Alert>
                    )}
                    {!!(row.deduplicated_entities && row.deduplicated_entities.length > 0) && (
                      <Alert severity="info" sx={{ mt: 1.25 }}>
                        <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
                          Removed as duplicates ({row.deduplicated_entities?.length ?? 0}):
                        </Typography>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                          {(row.deduplicated_entities ?? []).map((ent, idx) => (
                            <Chip
                              key={`${row.encounter_id}-dedupe-${idx}`}
                              size="small"
                              label={`${ent.text} (${ent.label})`}
                              variant="outlined"
                            />
                          ))}
                        </Box>
                      </Alert>
                    )}

                    {row.layer_trace.length > 0 && (
                      <Accordion sx={{ mt: 1.25 }} disableGutters>
                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            Stage-by-stage pipeline trace
                          </Typography>
                        </AccordionSummary>
                        <AccordionDetails>
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>Stage</TableCell>
                                <TableCell align="right">Added</TableCell>
                                <TableCell align="right">Removed</TableCell>
                                <TableCell align="right">Modified</TableCell>
                                <TableCell align="right">Time (ms)</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {row.layer_trace.map((step) => {
                                const hasChanges = step.added_count > 0 || step.removed_count > 0 || step.updated_count > 0;
                                return (
                                  <TableRow key={`${row.encounter_id}-${step.layer_id}`} sx={hasChanges ? { backgroundColor: "action.hover" } : undefined}>
                                    <TableCell>{step.name || step.layer_id}</TableCell>
                                    <TableCell align="right">{step.added_count}</TableCell>
                                    <TableCell align="right">{step.removed_count}</TableCell>
                                    <TableCell align="right">{step.updated_count}</TableCell>
                                    <TableCell align="right">{step.duration_ms}</TableCell>
                                  </TableRow>
                                );
                              })}
                            </TableBody>
                          </Table>
                        </AccordionDetails>
                      </Accordion>
                    )}
                  </Paper>
                );
              })}
            </Box>
          )}
        </Box>
      </Card>

      {/* Encounter picker dialog */}
      <Dialog
        open={dryRunDialogOpen}
        onClose={() => setDryRunDialogOpen(false)}
        maxWidth="md"
        fullWidth
        scroll="paper"
      >
        <DialogTitle>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Choose encounters to test</span>
            {dryRunRows.length > 0 && (
              <Typography variant="caption" color="text.secondary">
                {Object.keys(selectedDryRun).length} of {dryRunRows.length} selected
              </Typography>
            )}
          </Box>
          {dryRunQuery && (
            <Stack
              direction="row"
              spacing={0.75}
              alignItems="center"
              flexWrap="wrap"
              sx={{ rowGap: 0.5 }}
            >
              <Typography variant="caption" color="text.secondary">
                Results for &ldquo;{dryRunQuery}&rdquo; (keyword + meaning).
                Rows tagged &ldquo;semantic match&rdquo; matched by meaning,
                not wording.
              </Typography>
              {dryRunHighlightTokens.length > 0 && (
                <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" sx={{ rowGap: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">
                    Highlighting matches for:
                  </Typography>
                  {dryRunHighlightTokens.slice(0, 12).map((term) => (
                    <Chip
                      key={`hl-chip-${term}`}
                      size="small"
                      label={term}
                      sx={{
                        height: 18,
                        fontSize: "0.65rem",
                        bgcolor: "rgba(255, 213, 79, 0.6)",
                      }}
                    />
                  ))}
                  {dryRunHighlightTokens.length > 12 && (
                    <Typography variant="caption" color="text.secondary">
                      +{dryRunHighlightTokens.length - 12} more
                    </Typography>
                  )}
                </Stack>
              )}
            </Stack>
          )}
        </DialogTitle>
        <DialogContent dividers sx={{ p: 0 }}>
          {dryRunRows.length === 0 ? (
            <Box sx={{ p: 4, textAlign: "center" }}>
              <Typography color="text.secondary">No results. Search for encounters first.</Typography>
            </Box>
          ) : (
            <Box>
              {dryRunRows.map((row, idx) => {
                const selected = !!selectedDryRun[row.encounter_id];
                const toggleRow = () => setSelectedDryRun((prev) => {
                  const next = { ...prev };
                  if (next[row.encounter_id]) { delete next[row.encounter_id]; } else { next[row.encounter_id] = row; }
                  return next;
                });
                return (
                  <Box key={row.encounter_id}>
                    {idx > 0 && <Divider />}
                    <Box
                      onClick={toggleRow}
                      sx={{
                        p: 2,
                        display: "flex",
                        gap: 1.5,
                        alignItems: "flex-start",
                        cursor: "pointer",
                        backgroundColor: selected ? "rgba(25, 118, 210, 0.06)" : "transparent",
                        "&:hover": { backgroundColor: selected ? "rgba(25, 118, 210, 0.10)" : "action.hover" },
                      }}
                    >
                      <Checkbox
                        checked={selected}
                        onClick={(e) => e.stopPropagation()}
                        onChange={toggleRow}
                        sx={{ mt: -0.25 }}
                      />
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Stack direction="row" spacing={1.5} mb={0.75} alignItems="baseline" flexWrap="wrap">
                          <Typography variant="caption" sx={{ fontFamily: "monospace", fontWeight: 700 }}>
                            {row.encounter_id.slice(0, 8)}&hellip;
                          </Typography>
                          {row.encounter_date && (
                            <Typography variant="caption" color="text.secondary">{row.encounter_date}</Typography>
                          )}
                          <Typography variant="caption" color="text.secondary">Patient {row.patient_id}</Typography>
                          {row.match_type === "semantic" && (
                            <Tooltip title="This row matched by meaning, not by wording. The yellow highlights below show the closest related phrases we know about for your search.">
                              <Chip
                                size="small"
                                data-testid="encounter-match-type-chip"
                                label="semantic match"
                                color="info"
                                variant="outlined"
                                sx={{ height: 18, fontSize: "0.65rem" }}
                              />
                            </Tooltip>
                          )}
                          {row.match_type === "hybrid" && (
                            <Tooltip title="This row matched both your wording and the broader meaning of your search.">
                              <Chip
                                size="small"
                                data-testid="encounter-match-type-chip"
                                label="keyword + meaning"
                                color="success"
                                variant="outlined"
                                sx={{ height: 18, fontSize: "0.65rem" }}
                              />
                            </Tooltip>
                          )}
                        </Stack>
                        <Typography
                          variant="body2"
                          component="div"
                          sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.65, color: "text.primary" }}
                        >
                          {renderHighlightedText(row.text ?? "", dryRunHighlightTokens)}
                        </Typography>
                      </Box>
                    </Box>
                  </Box>
                );
              })}
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 2, py: 1.5 }}>
          <Button
            size="small"
            onClick={() => {
              if (Object.keys(selectedDryRun).length === dryRunRows.length) {
                setSelectedDryRun({});
              } else {
                const next: Record<string, DryRunEncounterRow> = {};
                dryRunRows.forEach((r) => { next[r.encounter_id] = r; });
                setSelectedDryRun(next);
              }
            }}
          >
            {Object.keys(selectedDryRun).length === dryRunRows.length ? "Deselect all" : "Select all"}
          </Button>
          <Box sx={{ flex: 1 }} />
          <Button onClick={() => setDryRunDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={Object.keys(selectedDryRun).length === 0}
            onClick={() => setDryRunDialogOpen(false)}
          >
            {Object.keys(selectedDryRun).length > 0
              ? `Confirm (${Object.keys(selectedDryRun).length})`
              : "Confirm"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Section 3 -- Results and decision */}
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        3) Decide what to do
      </Typography>
      {!canaryRecord || canaryRecord.canary_precision === null ? (
        <Typography variant="body2" color="text.secondary">
          Safety test results will appear here after the test finishes.
        </Typography>
      ) : (
        <Card variant="outlined">
          <Box sx={{ p: 1.5 }}>
            <Stack direction="row" spacing={1.5} mb={1} flexWrap="wrap" useFlexGap>
              <Paper variant="outlined" sx={{ p: 1, minWidth: 120, flex: "1 1 120px" }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>
                  Right answers
                </Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  {pct(canaryRecord.canary_precision)}
                </Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1, minWidth: 120, flex: "1 1 120px" }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>
                  Items found
                </Typography>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  {pct(canaryRecord.canary_recall)}
                </Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1, minWidth: 120, flex: "1 1 120px" }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10.5 }}>
                  Result
                </Typography>
                <Typography
                  variant="subtitle1"
                  sx={{ fontWeight: 700 }}
                  color={canaryPass ? "success.main" : "error.main"}
                >
                  {canaryPass ? "Passed" : "Did not pass"}
                </Typography>
              </Paper>
            </Stack>

            {canaryPass ? (
              <Alert severity="success" sx={{ mb: 1.5 }}>
                This model passed. You can make it live now.
              </Alert>
            ) : (
              <Alert severity="error" sx={{ mb: 1.5 }}>
                Action needed: this model did not pass. Reject it and retrain, or override with audit record.
              </Alert>
            )}

            {goldJob?.status === "completed" && canaryPerLabelRows.length ? (
              <Accordion disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="body2" fontWeight={600}>
                    Scores for each word type
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Word type</TableCell>
                        <TableCell>Right answers</TableCell>
                        <TableCell>Items found</TableCell>
                        <TableCell>Overall</TableCell>
                        <TableCell>Change from training</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {canaryPerLabelRows.map((row) => {
                        const trainF1 = f1(canaryRecord.offline_precision, canaryRecord.offline_recall) ?? 0;
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
                Detailed scores for each word type appear after a safety test run completes.
              </Typography>
            )}

            <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap">
              <Tooltip title={canaryPass ? "" : "This model did not pass safety thresholds"}>
                <span>
                  <Button
                    variant="contained"
                    color="success"
                    disabled={!canaryPass || busyAction === `promote:${canaryRecord.model_version}`}
                    onClick={() => promote(canaryRecord.model_version)}
                  >
                    {busyAction === `promote:${canaryRecord.model_version}`
                      ? <CircularProgress aria-label="Loading" size={16} />
                      : "Make this AI live"}
                  </Button>
                </span>
              </Tooltip>
              {!canaryPass && (
                <Button
                  variant="outlined"
                  color="warning"
                  onClick={() => setForcePromoteConfirmOpen(true)}
                  disabled={!!busyAction}
                >
                  Go live anyway
                </Button>
              )}
              <Button
                variant="outlined"
                color="error"
                onClick={() => setRejectConfirmVersion(canaryRecord.model_version)}
                disabled={busyAction === `reject:${canaryRecord.model_version}`}
              >
                {busyAction === `reject:${canaryRecord.model_version}`
                  ? <CircularProgress aria-label="Loading" size={16} />
                  : "Reject this version"}
              </Button>
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              To pass: right answers at least {(MODEL_CANARY_MIN_PRECISION * 100).toFixed(0)}%, items found at least {(MODEL_CANARY_MIN_RECALL * 100).toFixed(0)}%.
            </Typography>
          </Box>
        </Card>
      )}

      {promotedVersion && (
        <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary" }}>
          Live now: {promotedVersion}
        </Typography>
      )}

      {forcePromoteConfirmOpen && (
        <ConfirmDialog
          title="Go live anyway?"
          body={`This model did not pass. Scores were right answers ${pct(canaryRecord?.canary_precision)} and items found ${pct(canaryRecord?.canary_recall)}. This override will be recorded for audit.`}
          confirmLabel={busyAction === `promote:${canaryRecord?.model_version}` ? "Working..." : "Go live anyway"}
          variant="danger"
          onConfirm={() => canaryRecord && promote(canaryRecord.model_version, true)}
          onCancel={() => setForcePromoteConfirmOpen(false)}
        />
      )}

      {!!rejectConfirmVersion && (
        <ConfirmDialog
          title="Reject this AI version?"
          body={`Version ${rejectConfirmVersion} will be retired and cannot be made live.`}
          confirmLabel="Reject"
          variant="danger"
          onConfirm={() => rejectConfirmVersion && reject(rejectConfirmVersion)}
          onCancel={() => setRejectConfirmVersion(null)}
        />
      )}

      <Dialog
        open={!!approveTarget}
        onClose={approving ? undefined : cancelApproveAsGold}
        maxWidth="sm"
        fullWidth
        aria-labelledby="approve-as-gold-title"
      >
        <DialogTitle id="approve-as-gold-title">
          Approve as gold training data?
        </DialogTitle>
        <DialogContent>
          {approveTarget && (
            <Stack spacing={1.5}>
              <Typography variant="body2">
                You are adding{" "}
                <strong>
                  {approveTarget.entities.length}{" "}
                  {approveTarget.entities.length === 1 ? "entity" : "entities"}
                </strong>{" "}
                from encounter <code>{approveTarget.encounterId.slice(0, 12)}</code>
                {" "}to the gold dataset as <strong>verified</strong>. This will be
                used for model training and evaluation.
              </Typography>
              <Alert severity="info" sx={{ py: 0.5 }}>
                The text shown above has already been de-identified
                (names, dates and other patient details replaced with
                placeholders). What you approve is exactly what will be
                stored.
              </Alert>
              <Alert severity="info" sx={{ py: 0.5 }}>
                If any entity is wrong, missing, or off by a few characters,
                cancel and use the pencil icon to open the editor instead.
              </Alert>
              {approveError && (
                <Alert
                  severity="error"
                  sx={{ py: 0.5 }}
                  data-testid="approve-as-gold-error"
                >
                  {approveError}
                </Alert>
              )}
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  Entities being approved:
                </Typography>
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                  {approveTarget.entities.map((ent, idx) => {
                    const { bg, fg } = labelColor(ent.label);
                    return (
                      <Chip
                        key={`approve-ent-${idx}`}
                        size="small"
                        label={`${ent.text} (${ent.label})`}
                        sx={{ bgcolor: bg, color: fg }}
                      />
                    );
                  })}
                </Box>
              </Box>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={cancelApproveAsGold} disabled={approving}>
            Cancel
          </Button>
          <Button
            onClick={() => void confirmApproveAsGold()}
            variant="contained"
            color="success"
            disabled={approving}
            startIcon={
              approving ? (
                <CircularProgress size={14} aria-label="Loading" />
              ) : (
                <CheckCircleIcon fontSize="small" />
              )
            }
          >
            {approving
              ? "Approving..."
              : `Approve ${approveTarget?.entities.length ?? 0} as gold`}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// -- Score card --------------------------------------------------------------

function ScoreCard({
  label,
  value,
  pass,
  locked = false,
}: {
  label: string;
  value: number | null | undefined;
  pass: boolean;
  locked?: boolean;
}) {
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: pass ? "success.main" : "error.main",
        borderRadius: 1.5,
        px: 1.5,
        py: 0.75,
        minWidth: 80,
        textAlign: "center",
        bgcolor: pass ? "success.50" : "error.50",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 0.5 }}>
        <Typography sx={{ fontSize: FONT_SIZES.label, color: "text.secondary" }}>{label}</Typography>
        {locked && <LockIcon sx={{ fontSize: 12, color: "text.disabled" }} />}
      </Box>
      <Typography sx={{ fontWeight: 700, fontSize: FONT_SIZES.heading, color: pass ? "success.dark" : "error.main" }}>
        {value != null ? `${(value * 100).toFixed(1)}%` : "—"}
      </Typography>
    </Box>
  );
}

// -- Per-label bar chart -----------------------------------------------------

function PerLabelChart({ perLabel }: { perLabel: Record<string, { f1: number }> }) {
  const data = Object.entries(perLabel)
    .map(([label, s]) => ({ label, f1: s.f1 }))
    .sort((a, b) => b.f1 - a.f1);

  return (
    <Box>
      <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
        Per-entity F1
      </Typography>
      <ResponsiveContainer width="100%" height={Math.max(100, data.length * 26)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 8, top: 2, bottom: 2 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
          <XAxis
            type="number"
            domain={[0, 1]}
            tick={{ fontSize: 11 }}
            tickFormatter={(v) => `${((typeof v === "number" ? v : 0) * 100).toFixed(0)}%`}
          />
          <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={130} />
          <RTooltip
            formatter={(v) => `${((typeof v === "number" ? v : 0) * 100).toFixed(1)}%`}
          />
          <Bar dataKey="f1" maxBarSize={16} radius={[0, 3, 3, 0]}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.f1 >= 0.8 ? "#2e7d32" : d.f1 >= 0.6 ? "#ed6c02" : "#d32f2f"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}

// -- Regression history table ------------------------------------------------

function RegressionTable({ jobs }: { jobs: TrainingJob[] }) {
  const doneJobs = jobs.filter((j) => j.status === "done").slice(0, 8);
  if (doneJobs.length < 2) return null;

  return (
    <Box>
      <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
        Regression history
      </Typography>
      <Box sx={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: FONT_SIZES.label }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #e0e0e0" }}>
              {["Version", "F1", "P", "R", "Golden F1", "Gates"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontWeight: 600, fontSize: FONT_SIZES.label }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {doneJobs.map((j, i) => {
              const prevF1 = doneJobs[i + 1]?.f1;
              const delta = j.f1 != null && prevF1 != null ? j.f1 - prevF1 : null;
              return (
                <tr key={j.job_id} style={{ borderBottom: "1px solid #f5f5f5" }}>
                  <td style={{ padding: "4px 8px" }}>{j.model_version ?? j.job_id.slice(0, 8)}</td>
                  <td style={{ padding: "4px 8px", fontWeight: 600 }}>
                    {j.f1 != null ? `${(j.f1 * 100).toFixed(1)}%` : "—"}
                    {delta != null && (
                      <span style={{ color: delta >= 0 ? "#2e7d32" : "#d32f2f", marginLeft: 4, fontSize: "0.65rem" }}>
                        {delta >= 0 ? "+" : ""}{(delta * 100).toFixed(1)}%
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "4px 8px" }}>{j.precision != null ? `${(j.precision * 100).toFixed(1)}%` : "—"}</td>
                  <td style={{ padding: "4px 8px" }}>{j.recall != null ? `${(j.recall * 100).toFixed(1)}%` : "—"}</td>
                  <td style={{ padding: "4px 8px" }}>
                    {j.golden_f1 != null ? `${(j.golden_f1 * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "4px 8px" }}>
                    <Chip
                      size="small"
                      label={j.passed_gates ? "Pass" : "Fail"}
                      color={j.passed_gates ? "success" : "error"}
                      sx={{ height: 16, fontSize: "0.62rem" }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Box>
    </Box>
  );
}
