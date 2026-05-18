/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B6E80BEE
 *   DI: DI-B8674FBF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B6E80BEE")
 */
"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Checkbox from "@mui/material/Checkbox";
import InputAdornment from "@mui/material/InputAdornment";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import SearchIcon from "@mui/icons-material/Search";
import { api } from "@/lib/api";
import ConfirmDialog from "@/components/ConfirmDialog";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface Pipeline {
  id: string;
  name: string;
  description?: string;
  status: string;
}

// Clinical pipeline scope: one patient, one encounter, or a guarded bulk run
type ClinicalScope = "patient" | "encounter" | "all_patients";

// Gold training scope: all pending candidates or specific ones
type GoldScope = "all_pending" | "specific";

interface CandidateStats {
  total: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

interface Candidate {
  candidate_id: string;
  text: string;
  status: string;
  source?: string;
}

interface RunEvent {
  type: string;
  message?: string;
  encounter_id?: string;
  [key: string]: unknown;
}

const GOLD_PIPELINE_ID = "pd-gold-training-audit";
const BULK_CONFIRM_TEXT = "RESET AND REPROCESS ALL PATIENTS";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

function openStream(
  url: string,
  onEvent: (ev: RunEvent) => void,
  onDone: () => void,
  onError: (msg: string) => void,
): () => void {
  const ctrl = new AbortController();
  (async () => {
    try {
      const res = await fetch(url, {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "text/event-stream" },
        signal: ctrl.signal,
      });
      if (!res.body) throw new Error("No response from server.");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          try {
            const ev: RunEvent = JSON.parse(line.slice(5).trim());
            if (ev.type === "heartbeat") continue;
            onEvent(ev);
            if (["run_completed", "pipeline_done", "extraction_done"].includes(ev.type)) {
              onDone(); return;
            }
            if (["pipeline_error", "run_error"].includes(ev.type)) {
              onError(ev.message ?? "Something went wrong."); return;
            }
          } catch { /* skip */ }
        }
      }
      onDone();
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        onError(e instanceof Error ? e.message : "Lost connection to server.");
      }
    }
  })();
  return () => ctrl.abort();
}

// ─────────────────────────────────────────────────────────────────────────────
// SelectionCard — reusable tile
// ─────────────────────────────────────────────────────────────────────────────

function SelectionCard({
  selected, title, desc, badge, onClick,
}: {
  selected: boolean; title: string; desc: string; badge?: string; onClick: () => void;
}) {
  return (
    <Paper variant="outlined" onClick={onClick}
      sx={{
        p: 1.75, cursor: "pointer", flex: 1, position: "relative",
        borderColor: selected ? "primary.main" : "divider",
        borderWidth: selected ? 2 : 1,
        bgcolor: selected ? "primary.50" : "background.paper",
      }}>
      {badge && (
        <Chip label={badge} size="small" color="success" variant="outlined"
          sx={{ position: "absolute", top: 8, right: 8, height: 18, fontSize: "0.6rem" }} />
      )}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        {selected
          ? <CheckCircleIcon fontSize="small" color="primary" />
          : <RadioButtonUncheckedIcon fontSize="small" sx={{ color: "text.disabled" }} />}
        <Typography variant="body2" fontWeight={700}>{title}</Typography>
      </Stack>
      <Typography variant="caption" color="text.secondary">{desc}</Typography>
    </Paper>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// EventLog
// ─────────────────────────────────────────────────────────────────────────────

function EventLog({ events }: { events: RunEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [events]);
  if (events.length === 0) return null;
  return (
    <Box sx={{
      mt: 2, p: 1.5, bgcolor: "#0d1117", borderRadius: 1,
      maxHeight: 240, overflowY: "auto", fontFamily: "monospace", fontSize: "0.72rem",
    }}>
      {events.map((ev, i) => {
        const isError = ev.type?.includes("error");
        const isDone  = ev.type?.includes("completed") || ev.type?.includes("done");
        const color   = isError ? "#ff6b6b" : isDone ? "#69db7c" : ev.type === "warning" ? "#ffa94d" : "#c9d1d9";
        const text    = ev.message ?? (ev.encounter_id ? `encounter ${ev.encounter_id}` : ev.type);
        return (
          <Box key={i} sx={{ color, mb: 0.25 }}>
            <Box component="span" sx={{ color: "#6e7681", mr: 1 }}>[{ev.type}]</Box>
            {text}
          </Box>
        );
      })}
      <div ref={endRef} />
    </Box>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// GoldScopePanel — searchable multi-select for TrainingCandidates
// ─────────────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

function GoldScopePanel({
  goldScope, setGoldScope, selectedIds, setSelectedIds, dryRun, setDryRun,
}: {
  goldScope: GoldScope;
  setGoldScope: (s: GoldScope) => void;
  selectedIds: Set<string>;
  setSelectedIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  dryRun: boolean;
  setDryRun: (v: boolean) => void;
}) {
  const [stats,        setStats]        = useState<CandidateStats | null>(null);
  const [candidates,   setCandidates]   = useState<Candidate[]>([]);
  const [total,        setTotal]        = useState(0);
  const [page,         setPage]         = useState(1);
  const [search,       setSearch]       = useState("");
  const [debouncedQ,   setDebouncedQ]   = useState("");
  const [loading,      setLoading]      = useState(false);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => { setDebouncedQ(search); setPage(1); }, 350);
    return () => clearTimeout(t);
  }, [search]);

  // Load stats once
  useEffect(() => {
    getJson<CandidateStats>("/api/pipeline/gold-training/stats")
      .then(setStats).catch(() => null);
  }, []);

  // Load candidates whenever query/page changes (specific mode only)
  useEffect(() => {
    if (goldScope !== "specific") return;
    setLoading(true);
    const params = new URLSearchParams({
      status: "pending",
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    if (debouncedQ) params.set("search", debouncedQ);
    getJson<{ items: Candidate[]; total: number }>(`/api/training/candidates?${params}`)
      .then((r) => { setCandidates(r.items); setTotal(r.total); })
      .catch(() => { setCandidates([]); setTotal(0); })
      .finally(() => setLoading(false));
  }, [goldScope, debouncedQ, page]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const allPageSelected = candidates.length > 0 && candidates.every((c) => selectedIds.has(c.candidate_id));
  const somePageSelected = candidates.some((c) => selectedIds.has(c.candidate_id));

  const toggleOne = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const togglePage = () =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allPageSelected) candidates.forEach((c) => next.delete(c.candidate_id));
      else candidates.forEach((c) => next.add(c.candidate_id));
      return next;
    });

  const clearAll = () => setSelectedIds(new Set());

  return (
    <Stack spacing={2}>
      {/* Stats bar */}
      <Box sx={{ p: 1.25, bgcolor: "grey.50", borderRadius: 1 }}>
        {stats ? (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={`${stats.pending} ready to run`}
              color={stats.pending > 0 ? "primary" : "default"} />
            <Chip size="small" label={`${stats.completed} already done`} color="success" variant="outlined" />
            {stats.processing > 0 && <Chip size="small" label={`${stats.processing} in progress`} color="warning" />}
            {stats.failed > 0 && <Chip size="small" label={`${stats.failed} failed`} color="error" variant="outlined" />}
          </Stack>
        ) : (
          <Stack direction="row" spacing={1}>
            {[90, 80, 80].map((w, i) => <Skeleton key={i} width={w} height={22} variant="rounded" />)}
          </Stack>
        )}
      </Box>

      {/* Mode toggle */}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <SelectionCard
          selected={goldScope === "all_pending"}
          title="All ready candidates"
          desc={stats ? `Queue all ${stats.pending} unprocessed candidates at once.` : "Queue all unprocessed candidates."}
          badge={stats?.pending ? `${stats.pending}` : undefined}
          onClick={() => { setGoldScope("all_pending"); clearAll(); }}
        />
        <SelectionCard
          selected={goldScope === "specific"}
          title="Choose which ones"
          desc="Search and pick the specific candidates you want to run."
          badge={selectedIds.size > 0 ? `${selectedIds.size} selected` : undefined}
          onClick={() => setGoldScope("specific")}
        />
      </Stack>

      {/* Multi-select picker — only shown in specific mode */}
      {goldScope === "specific" && (
        <Box>
          {/* Search + select-all header */}
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <TextField
              size="small" placeholder="Search by text…" value={search}
              onChange={(e) => setSearch(e.target.value)}
              sx={{ flex: 1 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
                  </InputAdornment>
                ),
              }}
            />
            {selectedIds.size > 0 && (
              <Button size="small" onClick={clearAll} sx={{ whiteSpace: "nowrap" }}>
                Clear {selectedIds.size} selected
              </Button>
            )}
          </Stack>

          {/* List */}
          <Paper variant="outlined" sx={{ maxHeight: 320, overflowY: "auto" }}>
            {/* Select all on page */}
            <Box sx={{
              px: 1.5, py: 0.75, borderBottom: "1px solid", borderColor: "divider",
              bgcolor: "grey.50", position: "sticky", top: 0, zIndex: 1,
            }}>
              <Stack direction="row" alignItems="center" spacing={0.5}>
                <Checkbox size="small" checked={allPageSelected} indeterminate={somePageSelected && !allPageSelected}
                  onChange={togglePage} sx={{ p: 0.5 }} />
                <Typography variant="caption" color="text.secondary">
                  {loading ? "Loading…" : `${total} candidate${total !== 1 ? "s" : ""} match`}
                  {selectedIds.size > 0 && ` · ${selectedIds.size} selected`}
                </Typography>
              </Stack>
            </Box>

            {loading ? (
              <Stack spacing={0.5} sx={{ p: 1 }}>
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} height={40} variant="rounded" />)}
              </Stack>
            ) : candidates.length === 0 ? (
              <Box sx={{ p: 2, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">No candidates match.</Typography>
              </Box>
            ) : (
              candidates.map((c) => {
                const sel = selectedIds.has(c.candidate_id);
                return (
                  <Box key={c.candidate_id} onClick={() => toggleOne(c.candidate_id)}
                    sx={{
                      display: "flex", alignItems: "flex-start", gap: 1,
                      px: 1.5, py: 0.75, cursor: "pointer",
                      bgcolor: sel ? "primary.50" : "background.paper",
                      borderBottom: "1px solid", borderColor: "divider",
                      "&:last-child": { borderBottom: 0 },
                      "&:hover": { bgcolor: sel ? "primary.100" : "grey.50" },
                    }}>
                    <Checkbox size="small" checked={sel} sx={{ p: 0.5, mt: 0.25 }}
                      onChange={() => toggleOne(c.candidate_id)} onClick={(e) => e.stopPropagation()} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.disabled" }}>
                        {c.candidate_id.slice(0, 14)}…
                      </Typography>
                      <Typography variant="body2" sx={{
                        overflow: "hidden", textOverflow: "ellipsis",
                        display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                        lineHeight: 1.4, fontSize: "0.8rem",
                      }}>
                        {c.text}
                      </Typography>
                    </Box>
                  </Box>
                );
              })
            )}
          </Paper>

          {/* Pagination */}
          {totalPages > 1 && (
            <Stack direction="row" justifyContent="center" alignItems="center" spacing={1} sx={{ mt: 1 }}>
              <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Prev</Button>
              <Typography variant="caption" color="text.secondary">
                Page {page} of {totalPages}
              </Typography>
              <Button size="small" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next →</Button>
            </Stack>
          )}
        </Box>
      )}

      {/* Test mode toggle */}
      <Paper variant="outlined" onClick={() => setDryRun(!dryRun)}
        sx={{
          px: 1.5, py: 0.75, cursor: "pointer", display: "inline-flex",
          borderColor: dryRun ? "warning.main" : "divider",
          borderWidth: dryRun ? 2 : 1,
          bgcolor: dryRun ? "warning.50" : "background.paper",
        }}>
        <Typography variant="caption" fontWeight={dryRun ? 700 : 400}>
          {dryRun ? "Test mode ON — nothing will be saved" : "Test mode OFF — results will be saved"}
        </Typography>
      </Paper>
    </Stack>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ClinicalScopePanel — scope UI for patient/encounter pipelines
// ─────────────────────────────────────────────────────────────────────────────

function ClinicalScopePanel({
  clinicalScope, setClinicalScope, patientId, setPatientId,
  encounterId, setEncounterId, dryRun, setDryRun,
  bulkOrgId, setBulkOrgId,
  bulkAckExpensive, setBulkAckExpensive,
  bulkAckDestructive, setBulkAckDestructive,
  bulkAckBackground, setBulkAckBackground,
  bulkConfirmationText, setBulkConfirmationText,
  bulkPreview, bulkPreviewLoading, onPreviewBulk,
}: {
  clinicalScope: ClinicalScope; setClinicalScope: (s: ClinicalScope) => void;
  patientId: string; setPatientId: (v: string) => void;
  encounterId: string; setEncounterId: (v: string) => void;
  dryRun: boolean; setDryRun: (v: boolean) => void;
  bulkOrgId: string; setBulkOrgId: (v: string) => void;
  bulkAckExpensive: boolean; setBulkAckExpensive: (v: boolean) => void;
  bulkAckDestructive: boolean; setBulkAckDestructive: (v: boolean) => void;
  bulkAckBackground: boolean; setBulkAckBackground: (v: boolean) => void;
  bulkConfirmationText: string; setBulkConfirmationText: (v: string) => void;
  bulkPreview: { patient_count: number; encounter_count: number } | null;
  bulkPreviewLoading: boolean;
  onPreviewBulk: () => void;
}) {
  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <SelectionCard
          selected={clinicalScope === "patient"}
          title="A patient"
          desc="Run on all encounters for one patient."
          onClick={() => setClinicalScope("patient")}
        />
        <SelectionCard
          selected={clinicalScope === "encounter"}
          title="A single encounter"
          desc="Re-run one specific encounter. Shows live results."
          onClick={() => setClinicalScope("encounter")}
        />
        <SelectionCard
          selected={clinicalScope === "all_patients"}
          title="All scoped patients"
          desc="Reset and reprocess all patients in one org. This is expensive."
          onClick={() => setClinicalScope("all_patients")}
        />
      </Stack>

      <Stack spacing={1.5}>
        {clinicalScope !== "all_patients" && (
          <TextField label="Patient ID" size="small" value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            placeholder="e.g. 9990000001" fullWidth />
        )}
        {clinicalScope === "encounter" && (
          <TextField label="Encounter ID" size="small" value={encounterId}
            onChange={(e) => setEncounterId(e.target.value)}
            placeholder="e.g. doc_c73f4fcad01996bb" fullWidth />
        )}
        {clinicalScope === "all_patients" && (
          <TextField label="Organization ID" size="small" value={bulkOrgId}
            onChange={(e) => setBulkOrgId(e.target.value)}
            placeholder="e.g. org-gp-001" fullWidth />
        )}
      </Stack>

      {clinicalScope === "all_patients" && (
        <Stack spacing={1.25}>
          <Alert severity="error">
            This will delete existing pipeline artefacts for every patient in the selected organization, then queue full reprocessing. It can take a long time and costs more.
          </Alert>

          <Button
            variant="outlined"
            onClick={onPreviewBulk}
            disabled={bulkPreviewLoading || bulkOrgId.trim().length === 0}
          >
            {bulkPreviewLoading ? "Checking scope..." : "Preview impact"}
          </Button>

          {bulkPreview && (
            <Alert severity="warning">
              Scope preview: {bulkPreview.patient_count} patient(s), {bulkPreview.encounter_count} encounter(s) to queue.
            </Alert>
          )}

          <Stack direction="row" alignItems="center" spacing={1}>
            <Checkbox
              checked={bulkAckExpensive}
              onChange={(e) => setBulkAckExpensive(e.target.checked)}
            />
            <Typography variant="body2">I understand this run is expensive.</Typography>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Checkbox
              checked={bulkAckDestructive}
              onChange={(e) => setBulkAckDestructive(e.target.checked)}
            />
            <Typography variant="body2">I understand this deletes current patient pipeline artefacts first.</Typography>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Checkbox
              checked={bulkAckBackground}
              onChange={(e) => setBulkAckBackground(e.target.checked)}
            />
            <Typography variant="body2">I understand this runs in the background and may continue after I leave this page.</Typography>
          </Stack>
          <TextField
            label="Type confirmation text"
            size="small"
            value={bulkConfirmationText}
            onChange={(e) => setBulkConfirmationText(e.target.value)}
            placeholder={BULK_CONFIRM_TEXT}
            fullWidth
          />
        </Stack>
      )}

      <Paper variant="outlined" onClick={() => setDryRun(!dryRun)}
        sx={{
          px: 1.5, py: 0.75, cursor: "pointer", display: "inline-flex",
          borderColor: dryRun ? "warning.main" : "divider",
          borderWidth: dryRun ? 2 : 1,
          bgcolor: dryRun ? "warning.50" : "background.paper",
        }}>
        <Typography variant="caption" fontWeight={dryRun ? 700 : 400}>
          {dryRun ? "Test mode ON - nothing will be saved" : "Test mode OFF - results will be saved"}
        </Typography>
      </Paper>
    </Stack>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function RunAIPage() {
  const router = useRouter();

  const [pipelines,        setPipelines]        = useState<Pipeline[]>([]);
  const [loadingPipelines, setLoadingPipelines] = useState(true);
  const [pipelineError,    setPipelineError]    = useState(false);
  const [selectedPipeline, setSelectedPipeline] = useState<Pipeline | null>(null);

  // Gold training state
  const [goldScope,    setGoldScope]    = useState<GoldScope>("all_pending");
  const [selectedIds,  setSelectedIds]  = useState<Set<string>>(new Set());

  // Clinical pipeline state
  const [clinicalScope, setClinicalScope] = useState<ClinicalScope>("patient");
  const [patientId,     setPatientId]     = useState("");
  const [encounterId,   setEncounterId]   = useState("");
  const [bulkOrgId, setBulkOrgId] = useState("");
  const [bulkAckExpensive, setBulkAckExpensive] = useState(false);
  const [bulkAckDestructive, setBulkAckDestructive] = useState(false);
  const [bulkAckBackground, setBulkAckBackground] = useState(false);
  const [bulkConfirmationText, setBulkConfirmationText] = useState("");
  const [bulkPreview, setBulkPreview] = useState<{ patient_count: number; encounter_count: number } | null>(null);
  const [bulkPreviewLoading, setBulkPreviewLoading] = useState(false);
  const [confirmBulkRunOpen, setConfirmBulkRunOpen] = useState(false);

  // Shared
  const [dryRun,   setDryRun]   = useState(false);
  const [running,  setRunning]  = useState(false);
  const [events,   setEvents]   = useState<RunEvent[]>([]);
  const [done,     setDone]     = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runId,    setRunId]    = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  const isGoldPipeline = selectedPipeline?.id === GOLD_PIPELINE_ID;

  useEffect(() => {
    api.get<{ entry?: Array<{ resource: Pipeline }> }>("/fhir/PlanDefinition")
      .then((data) => {
        const plans = (data.entry ?? []).map((e) => e.resource);
        setPipelines(plans);
        if (plans.length === 1) setSelectedPipeline(plans[0]);
      })
      .catch(() => { setPipelines([]); setPipelineError(true); })
      .finally(() => setLoadingPipelines(false));
  }, []);

  useEffect(() => () => { cancelRef.current?.(); }, []);

  const processedCount = events.filter((e) =>
    ["encounter_processed", "encounter_done", "extraction_done", "gold_label_written"].includes(e.type)
  ).length;
  const errorCount = events.filter((e) =>
    ["pipeline_error", "encounter_error"].includes(e.type)
  ).length;

  // Can we run?
  const canRun = (() => {
    if (!selectedPipeline) return false;
    if (isGoldPipeline) {
      return goldScope === "all_pending" || selectedIds.size > 0;
    }
    if (clinicalScope === "all_patients") {
      return !dryRun
        && bulkOrgId.trim().length > 0
        && !!bulkPreview
        && bulkAckExpensive
        && bulkAckDestructive
        && bulkAckBackground
        && bulkConfirmationText.trim() === BULK_CONFIRM_TEXT;
    }
    return patientId.trim().length > 0 &&
      (clinicalScope === "patient" || encounterId.trim().length > 0);
  })();

  const addEvent = (ev: RunEvent) => setEvents((p) => [...p, ev]);

  const handlePreviewBulk = async () => {
    setBulkPreviewLoading(true);
    try {
      const preview = await postJson<{
        preview: boolean;
        patient_count: number;
        encounter_count: number;
      }>("/api/pipeline/run-all-patients", {
        org_id: bulkOrgId.trim(),
        preview: true,
      });
      setBulkPreview({
        patient_count: preview.patient_count,
        encounter_count: preview.encounter_count,
      });
    } catch (e) {
      setBulkPreview(null);
      setRunError(e instanceof Error ? e.message : "Could not preview bulk run.");
    } finally {
      setBulkPreviewLoading(false);
    }
  };

  const handleRun = async () => {
    cancelRef.current?.();
    setRunning(true); setDone(false); setRunError(null); setEvents([]); setRunId(null);

    try {
      if (isGoldPipeline) {
        // ── Gold Training: queue one job per candidate ──────────────
        const candidateIds = goldScope === "specific"
          ? Array.from(selectedIds)
          : [];

        addEvent({ type: "info", message: "Sending training candidates to queue…" });
        const resp = await postJson<{ run_id: string; queued: number }>(
          "/api/pipeline/run-gold-training",
          {
            plan_definition_id: selectedPipeline!.id,
            mode: goldScope,
            candidate_ids: candidateIds,
            preview: dryRun,
          },
        );
        setRunId(resp.run_id);
        addEvent({
          type: "queued",
          message: `${resp.queued} candidate${resp.queued !== 1 ? "s" : ""} queued. `
            + "The pipeline worker will process them in the background.",
        });

        // Stream progress from Redis relay
        cancelRef.current = openStream(
          `/api/pipeline/progress/${resp.run_id}`,
          addEvent,
          () => { setRunning(false); setDone(true); },
          () => {
            setRunning(false);
            addEvent({
              type: "warning",
              message: "Live updates not available right now. "
                + "The job is running — check Verification examples for results.",
            });
            setDone(true);
          },
        );

      } else if (clinicalScope === "encounter") {
        // ── Single encounter: canonical queued run via reset-and-recode ─────
        addEvent({ type: "info", message: "Queueing canonical encounter run…" });
        const encounterResp = await postJson<{ run_id: string }>(
          `/api/patients/${encodeURIComponent(patientId.trim())}/encounters/${encodeURIComponent(encounterId.trim())}/reset-and-recode`,
          { dry_run: dryRun, rerun_episode_detector: true },
        );
        setRunId(encounterResp.run_id);
        addEvent({ type: "queued", message: "Encounter run queued. Waiting for worker pickup…" });
        cancelRef.current = openStream(
          `/api/pipeline/progress/${encounterResp.run_id}`,
          addEvent,
          () => { setRunning(false); setDone(true); },
          () => {
            setRunning(false);
            addEvent({
              type: "warning",
              message: "Live updates not available right now. The job is running in the background.",
            });
            setDone(true);
          },
        );

      } else if (clinicalScope === "all_patients") {
        addEvent({ type: "warning", message: "Starting destructive bulk reset and reprocess run..." });
        const resp = await postJson<{
          run_id: string;
          queued: number;
          patient_count: number;
          encounter_count: number;
        }>("/api/pipeline/run-all-patients", {
          org_id: bulkOrgId.trim(),
          preview: false,
          acknowledge_expensive: bulkAckExpensive,
          acknowledge_destructive: bulkAckDestructive,
          acknowledge_background: bulkAckBackground,
          confirmation_text: bulkConfirmationText.trim(),
          expected_patient_count: bulkPreview?.patient_count ?? null,
        });
        setRunId(resp.run_id);
        addEvent({
          type: "queued",
          message: `Queued ${resp.queued} encounter job(s) for ${resp.patient_count} patient(s).`,
        });
        cancelRef.current = openStream(
          `/api/pipeline/progress/${resp.run_id}`,
          addEvent,
          () => { setRunning(false); setDone(true); },
          () => {
            setRunning(false);
            addEvent({
              type: "warning",
              message: "Live updates not available right now. The bulk run is still processing in the background.",
            });
            setDone(true);
          },
        );
      } else {
        // ── Patient: full canonical pipeline via Service Bus ──────────
        addEvent({ type: "info", message: "Sending to processing queue…" });
        const resp = await postJson<{ run_id: string }>("/api/pipeline/run-patient", {
          patient_id: patientId.trim(),
          action: "full_pipeline",
          preview: dryRun,
        });
        setRunId(resp.run_id);
        addEvent({ type: "queued", message: "Job queued. Waiting for the worker to pick it up…" });
        cancelRef.current = openStream(
          `/api/pipeline/progress/${resp.run_id}`,
          addEvent,
          () => { setRunning(false); setDone(true); },
          () => {
            setRunning(false);
            addEvent({
              type: "warning",
              message: "Live updates not available right now. The job is running in the background.",
            });
            setDone(true);
          },
        );
      }
    } catch (e) {
      setRunning(false);
      setRunError(e instanceof Error ? e.message : "Could not start the run.");
    }
  };

  const handleRunClick = () => {
    if (!canRun || running) return;
    if (!isGoldPipeline && clinicalScope === "all_patients") {
      setConfirmBulkRunOpen(true);
      return;
    }
    void handleRun();
  };

  const handleStop = () => {
    cancelRef.current?.();
    setRunning(false);
    addEvent({ type: "stopped", message: "Stopped." });
  };

  const summaryText = (() => {
    if (!selectedPipeline || !canRun) return null;
    if (isGoldPipeline) {
      return goldScope === "all_pending"
        ? "all pending candidates"
        : `${selectedIds.size} specific candidate(s)`;
    }
    return clinicalScope === "patient"
      ? `patient ${patientId}`
      : clinicalScope === "encounter"
        ? `encounter ${encounterId} (patient ${patientId})`
        : `all patients in org ${bulkOrgId || "(not set)"}`;
  })();

  return (
    <Box sx={{ p: 3, maxWidth: 760, mx: "auto" }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 3 }}>
        <Tooltip title="Back to Console">
          <IconButton size="small" onClick={() => router.push("/admin/console")}>
            <ArrowBackIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Box>
          <Typography variant="h5" fontWeight={700}>Run the AI</Typography>
          <Typography variant="body2" color="text.secondary">
            Choose a pipeline and what to run it on, then press Run.
          </Typography>
        </Box>
      </Stack>

      {/* ── Step 1: Pipeline ─────────────────────────────────────── */}
      <Paper variant="outlined" sx={{ p: 2.5, mb: 2 }}>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          Step 1 — Which pipeline?
        </Typography>
        {loadingPipelines ? (
          <Stack spacing={1}>
            <Skeleton variant="rounded" height={52} />
            <Skeleton variant="rounded" height={52} />
          </Stack>
        ) : pipelineError ? (
          <Alert severity="error">Could not load pipelines. Check the API service is running.</Alert>
        ) : pipelines.length === 0 ? (
          <Alert severity="warning">
            No pipelines set up yet.{" "}
            <Box component="span" sx={{ textDecoration: "underline", cursor: "pointer" }}
              onClick={() => router.push("/admin/knowledge?tab=pathways")}>
              Go to Pathways to create one.
            </Box>
          </Alert>
        ) : (
          <Stack spacing={1}>
            {pipelines.map((p) => {
              const sel = selectedPipeline?.id === p.id;
              return (
                <Paper key={p.id} variant="outlined"
                  onClick={() => { setSelectedPipeline(p); setEvents([]); setDone(false); setRunError(null); }}
                  sx={{
                    px: 2, py: 1.25, cursor: "pointer",
                    borderColor: sel ? "primary.main" : "divider",
                    borderWidth: sel ? 2 : 1,
                    bgcolor: sel ? "primary.50" : "background.paper",
                  }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Box>
                      <Typography variant="body2" fontWeight={700}>{p.name}</Typography>
                      {p.description && (
                        <Typography variant="caption" color="text.secondary">{p.description}</Typography>
                      )}
                    </Box>
                    <Stack direction="row" spacing={0.75} alignItems="center">
                      <Chip size="small" label={p.status} variant="outlined"
                        color={p.status === "active" ? "success" : "default"} />
                      {sel && <CheckCircleIcon fontSize="small" color="primary" />}
                    </Stack>
                  </Stack>
                </Paper>
              );
            })}
          </Stack>
        )}
      </Paper>

      {/* ── Step 2: Scope (adapts to which pipeline is selected) ─── */}
      {selectedPipeline && (
        <Paper variant="outlined" sx={{ p: 2.5, mb: 2 }}>
          <Typography variant="subtitle2" fontWeight={700} gutterBottom>
            Step 2 — What do you want to run it on?
          </Typography>

          {isGoldPipeline ? (
            <GoldScopePanel
              goldScope={goldScope} setGoldScope={setGoldScope}
              selectedIds={selectedIds} setSelectedIds={setSelectedIds}
              dryRun={dryRun} setDryRun={setDryRun}
            />
          ) : (
            <ClinicalScopePanel
              clinicalScope={clinicalScope} setClinicalScope={setClinicalScope}
              patientId={patientId} setPatientId={setPatientId}
              encounterId={encounterId} setEncounterId={setEncounterId}
              dryRun={dryRun} setDryRun={setDryRun}
              bulkOrgId={bulkOrgId} setBulkOrgId={setBulkOrgId}
              bulkAckExpensive={bulkAckExpensive} setBulkAckExpensive={setBulkAckExpensive}
              bulkAckDestructive={bulkAckDestructive} setBulkAckDestructive={setBulkAckDestructive}
              bulkAckBackground={bulkAckBackground} setBulkAckBackground={setBulkAckBackground}
              bulkConfirmationText={bulkConfirmationText} setBulkConfirmationText={setBulkConfirmationText}
              bulkPreview={bulkPreview}
              bulkPreviewLoading={bulkPreviewLoading}
              onPreviewBulk={handlePreviewBulk}
            />
          )}
        </Paper>
      )}

      {/* ── Step 3: Run ──────────────────────────────────────────── */}
      {selectedPipeline && (
        <Paper variant="outlined" sx={{ p: 2.5 }}>
          <Typography variant="subtitle2" fontWeight={700} gutterBottom>
            Step 3 — Run
          </Typography>

          {summaryText && (
            <Box sx={{ mb: 1.5, p: 1.25, bgcolor: "grey.50", borderRadius: 1 }}>
              <Typography variant="body2" component="div">
                <Box component="span">
                  <strong>{selectedPipeline.name}</strong>{" · "}{summaryText}
                </Box>
                {dryRun && (
                  <Chip size="small" label="test mode" color="warning"
                    sx={{ ml: 1, height: 18, fontSize: "0.65rem", verticalAlign: "middle" }} />
                )}
              </Typography>
            </Box>
          )}

          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
            <Button variant="contained"
              startIcon={running ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
              onClick={handleRunClick} disabled={!canRun || running}>
              {running ? "Running…" : "Run now"}
            </Button>

            {running && (
              <Button variant="outlined" color="error" size="small" onClick={handleStop}>Stop</Button>
            )}

            {done && !runError && (
              <Stack direction="row" spacing={0.5} alignItems="center">
                <CheckCircleIcon color="success" fontSize="small" />
                <Typography variant="body2" color="success.main">
                  {processedCount > 0
                    ? `Done — ${processedCount} processed`
                    : "Done"}
                  {errorCount > 0 && ` · ${errorCount} error${errorCount !== 1 ? "s" : ""}`}
                </Typography>
              </Stack>
            )}

            {runError && (
              <Stack direction="row" spacing={0.5} alignItems="center">
                <ErrorOutlineIcon color="error" fontSize="small" />
                <Typography variant="body2" color="error.main">{runError}</Typography>
              </Stack>
            )}
          </Stack>

          {running && <LinearProgress sx={{ mt: 1.5, borderRadius: 1 }} />}

          {runId && !done && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              Reference: <Box component="span" sx={{ fontFamily: "monospace" }}>{runId}</Box>
            </Typography>
          )}

          <EventLog events={events} />

          {events.length > 0 && !running && (
            <>
              <Divider sx={{ mt: 2, mb: 1.5 }} />
              <Stack direction="row" spacing={1} alignItems="center">
                {processedCount > 0 && <Chip size="small" label={`${processedCount} processed`} color="success" />}
                {errorCount > 0 && <Chip size="small" label={`${errorCount} errors`} color="error" />}
                <Button size="small"
                  onClick={() => { setEvents([]); setDone(false); setRunError(null); setRunId(null); }}>
                  Clear
                </Button>
              </Stack>
            </>
          )}
        </Paper>
      )}
      {confirmBulkRunOpen && (
        <ConfirmDialog
          title="Final check before bulk run"
          body={
            `You are about to reset and reprocess ${bulkPreview?.patient_count ?? 0} patients `
            + `and queue ${bulkPreview?.encounter_count ?? 0} encounters. `
            + "This is expensive, destructive, and runs in the background. Continue now?"
          }
          confirmLabel="Yes, run now"
          cancelLabel="Cancel"
          variant="danger"
          onCancel={() => setConfirmBulkRunOpen(false)}
          onConfirm={() => {
            setConfirmBulkRunOpen(false);
            void handleRun();
          }}
        />
      )}
    </Box>
  );
}
