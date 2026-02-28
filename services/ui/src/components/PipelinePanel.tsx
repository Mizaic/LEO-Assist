"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Divider,
  FormControlLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import AutorenewIcon from "@mui/icons-material/Autorenew";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import AnalyticsIcon from "@mui/icons-material/Analytics";
import BoltIcon from "@mui/icons-material/Bolt";
import { cleanPatients } from "@/lib/api";
import { usePipeline } from "@/context/PipelineContext";
import type { EncounterLogEntry, EncounterOutcome } from "@/hooks/usePipelineStream";
import { parseNhsNumberInput, isValidNhsNumber } from "@/lib/nhsNumber";

interface ExtractorStatus {
  backend: "llm" | "model" | "auto";
  strict: boolean;
  model_name: string;
  model_version: string;
  model_endpoint: string;
  fallback_enabled: boolean;
}

interface PatientListItem {
  patient_id: string;
  encounter_count: number;
  reviewed_count?: number;
  progress?: number;
}

interface CodingSummary {
  patient_id: string;
  demographics?: { gender?: string | null; birth_date?: string | null };
  encounters: {
    total: number;
    classified: number;
    clinical: number;
    admin_only: number;
    document_transfer: number;
    coded: number;
    uncoded: number;
    progress_pct: number;
    date_from?: string | null;
    date_to?: string | null;
  };
  review: { approved: number; pending: number; failed: number };
  semantic_tag_counts: Array<{ semantic_tag: string; count: number }>;
  analysis: { episode_count: number; safety_alert_count: number; has_analysis_outputs: boolean };
}

type ActionKind = "code_new" | "recode_all" | "run_analysis" | "full_pipeline";

function backendLabel(status: ExtractorStatus | null): string {
  if (!status) return "Loading…";
  if (status.backend === "model") return "NER Model";
  if (status.backend === "auto") return "Auto (NER → LLM)";
  return "LLM";
}

function actionLabel(action: ActionKind): string {
  switch (action) {
    case "code_new":
      return "Code new encounters";
    case "recode_all":
      return "Re-code everything";
    case "run_analysis":
      return "Run analysis";
    case "full_pipeline":
      return "Full pipeline";
    default:
      return action;
  }
}

const OUTCOME_CONFIG: Record<EncounterOutcome, { icon: React.ReactNode; color: string; label: string }> = {
  processing: { icon: <AutorenewIcon fontSize="small" />, color: "text.secondary", label: "Processing" },
  queued: { icon: <CheckCircleIcon fontSize="small" />, color: "info.main", label: "Queued for review" },
  auto_approved: { icon: <CheckCircleIcon fontSize="small" />, color: "success.main", label: "Auto-approved" },
  failed: { icon: <ErrorIcon fontSize="small" />, color: "error.main", label: "Failed" },
  dry_run: { icon: <WarningAmberIcon fontSize="small" />, color: "warning.main", label: "Dry-run (skipped)" },
};

function EncounterLogTable({
  rows,
  showPatientColumn = false,
}: {
  rows: EncounterLogEntry[];
  showPatientColumn?: boolean;
}) {
  if (rows.length === 0) return null;
  return (
    <Box sx={{ overflowX: "auto", mt: 2, maxHeight: 320, overflowY: "auto" }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            {showPatientColumn && <TableCell sx={{ fontSize: 12 }}>Patient</TableCell>}
            <TableCell sx={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>Encounter</TableCell>
            <TableCell sx={{ fontSize: 12 }}>Worker</TableCell>
            <TableCell sx={{ fontSize: 12 }}>Terms</TableCell>
            <TableCell sx={{ fontSize: 12 }}>Outcome</TableCell>
            <TableCell sx={{ fontSize: 12 }}>Flags</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => {
            const cfg = OUTCOME_CONFIG[row.outcome];
            return (
              <TableRow key={`${row.patientId ?? "p"}:${row.encounterId}`} hover>
                {showPatientColumn && (
                  <TableCell sx={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                    {row.patientId ?? "—"}
                  </TableCell>
                )}
                <TableCell sx={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                  {row.encounterId.slice(0, 20)}{row.encounterId.length > 20 ? "…" : ""}
                </TableCell>
                <TableCell sx={{ fontSize: 12, color: "text.secondary" }}>
                  {row.workerId > 0 ? `W${row.workerId}` : "—"}
                </TableCell>
                <TableCell sx={{ fontSize: 12 }}>
                  {row.termCount !== null ? row.termCount : "—"}
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ color: cfg.color }}>
                    {cfg.icon}
                    <Typography variant="caption">{cfg.label}</Typography>
                  </Stack>
                </TableCell>
                <TableCell>
                  {row.fallbackUsed && (
                    <Chip size="small" label="fallback" color="warning" variant="outlined" sx={{ fontSize: 11 }} />
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

function RunResultCard({
  result,
  onGoToReview,
}: {
  result: NonNullable<ReturnType<typeof usePipeline>["result"]>;
  onGoToReview: (tab: string) => void;
}) {
  const queued = result.queued_for_review ?? 0;
  const autoApproved = result.auto_approved ?? 0;
  const failures = result.rejected_hard_fail ?? 0;
  return (
    <Alert severity={failures > 0 ? "warning" : "success"} sx={{ mt: 2, fontFamily: "var(--font-mono)", fontSize: 13 }}>
      <Stack spacing={0.75}>
        <Stack direction="row" spacing={2} flexWrap="wrap">
          <span>Processed: <strong>{result.processed_encounters}</strong></span>
          {autoApproved > 0 && <span>Auto-approved: <strong>{autoApproved}</strong></span>}
          <span>Queued for review: <strong>{queued}</strong></span>
          {failures > 0 && <span>Failed: <strong>{failures}</strong></span>}
        </Stack>
        <Typography variant="caption" sx={{ color: "text.secondary", fontFamily: "var(--font-mono)" }}>
          run_id: {result.run_id}
        </Typography>
        {queued > 0 && (
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
            <Button size="small" variant="outlined" onClick={() => onGoToReview("classification")}>
              → Classification Review
            </Button>
            <Button size="small" variant="outlined" onClick={() => onGoToReview("anchor")}>
              → Anchor Review
            </Button>
          </Stack>
        )}
      </Stack>
    </Alert>
  );
}

export default function PipelinePanel({
  onNavigateTab,
}: {
  onNavigateTab?: (tab: string) => void;
}) {
  const pipeline = usePipeline();
  const [mode, setMode] = useState<"single" | "cohort">("single");
  const [patients, setPatients] = useState<PatientListItem[]>([]);
  const [patientsLoading, setPatientsLoading] = useState(false);
  const [patientQuery, setPatientQuery] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [summary, setSummary] = useState<CodingSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [selectedCohort, setSelectedCohort] = useState<string[]>([]);

  const [dryRun, setDryRun] = useState(false);
  const [extractorStatus, setExtractorStatus] = useState<ExtractorStatus | null>(null);
  const [uiError, setUiError] = useState<string | null>(null);
  const [uiInfo, setUiInfo] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<ActionKind | null>(null);

  const jsonFetch = async <T,>(url: string, options?: RequestInit): Promise<T> => {
    const r = await fetch(url, { credentials: "include", ...options });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json() as Promise<T>;
  };

  useEffect(() => {
    setPatientsLoading(true);
    jsonFetch<PatientListItem[]>("/api/patients")
      .then((rows) => setPatients(rows))
      .catch((e) => setUiError(e instanceof Error ? e.message : "Failed to load patients"))
      .finally(() => setPatientsLoading(false));
    jsonFetch<ExtractorStatus>("/api/pipeline/extractor-status")
      .then((d) => setExtractorStatus(d))
      .catch(() => null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedPatientId) {
      setSummary(null);
      return;
    }
    setSummaryLoading(true);
    jsonFetch<CodingSummary>(`/api/patients/${selectedPatientId}/coding-summary`)
      .then((data) => setSummary(data))
      .catch((e) => setUiError(e instanceof Error ? e.message : "Failed to load coding summary"))
      .finally(() => setSummaryLoading(false));
  }, [selectedPatientId]);

  useEffect(() => {
    if (!pipeline.classification || !selectedPatientId) return;
    if (pipeline.classification.patientId !== selectedPatientId) return;
    jsonFetch<CodingSummary>(`/api/patients/${selectedPatientId}/coding-summary`)
      .then((data) => setSummary(data))
      .catch(() => null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipeline.classification, selectedPatientId]);

  const filteredPatients = useMemo(() => {
    const q = patientQuery.trim().toLowerCase();
    if (!q) return patients;
    return patients.filter((p) => p.patient_id.toLowerCase().includes(q));
  }, [patients, patientQuery]);

  const singlePatient = useMemo(
    () => patients.find((p) => p.patient_id === selectedPatientId) ?? null,
    [patients, selectedPatientId],
  );

  const parsedTypedIds = parseNhsNumberInput(patientQuery);
  const invalidTypedIds = parsedTypedIds.filter((id) => !isValidNhsNumber(id));

  const cohortProgress = useMemo(() => {
    const byPatient: Record<string, { done: number; failed: number; queued: number }> = {};
    for (const row of pipeline.encounterLog) {
      const pid = row.patientId;
      if (!pid) continue;
      byPatient[pid] ??= { done: 0, failed: 0, queued: 0 };
      if (row.outcome === "failed") byPatient[pid].failed += 1;
      if (row.outcome === "queued") byPatient[pid].queued += 1;
      if (row.outcome === "auto_approved" || row.outcome === "queued" || row.outcome === "dry_run") {
        byPatient[pid].done += 1;
      }
    }
    return byPatient;
  }, [pipeline.encounterLog]);

  const runSingleCoding = async (action: Exclude<ActionKind, "run_analysis">) => {
    if (!selectedPatientId || pipeline.running) return;
    setUiError(null);
    setUiInfo(null);
    setBusyAction(action);
    try {
      if (action === "recode_all") {
        const ok = window.confirm("Re-code everything will clear existing coding outputs for this patient. Continue?");
        if (!ok) return;
        await cleanPatients({ patient_ids: [selectedPatientId] });
      }
      pipeline.start({
        patientIds: [selectedPatientId],
        dryRun,
        workers: 4,
        unprocessedOnly: action === "code_new",
      });
    } catch (e) {
      setUiError(e instanceof Error ? e.message : "Failed to start pipeline run");
    } finally {
      setBusyAction(null);
    }
  };

  const runSingleAnalysis = async () => {
    if (!selectedPatientId) return;
    setUiError(null);
    setUiInfo(null);
    setBusyAction("run_analysis");
    try {
      const res = await jsonFetch<{ run_id: string }>("/api/pipeline/run-patient", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: selectedPatientId,
          action: "run_analysis",
          preview: dryRun,
        }),
      });
      // Subscribe to the Redis relay so progress renders live in the same panel.
      pipeline.subscribeToRun(res.run_id);
    } catch (e) {
      setUiError(e instanceof Error ? e.message : "Failed to queue analysis");
    } finally {
      setBusyAction(null);
    }
  };

  const runCohortCoding = async (action: Exclude<ActionKind, "run_analysis">) => {
    if (selectedCohort.length === 0 || pipeline.running) return;
    setUiError(null);
    setUiInfo(null);
    setBusyAction(action);
    try {
      if (action === "recode_all") {
        const ok = window.confirm(`Reset and re-code ${selectedCohort.length} patients? This removes existing coding outputs.`);
        if (!ok) return;
        await cleanPatients({ patient_ids: selectedCohort });
      }
      pipeline.start({
        patientIds: selectedCohort,
        dryRun,
        workers: 4,
        unprocessedOnly: action === "code_new",
      });
    } catch (e) {
      setUiError(e instanceof Error ? e.message : "Failed to start cohort run");
    } finally {
      setBusyAction(null);
    }
  };

  const runCohortAnalysis = async () => {
    if (selectedCohort.length === 0 || pipeline.running) return;
    setUiError(null);
    setUiInfo(null);
    setBusyAction("run_analysis");
    try {
      const res = await jsonFetch<{ run_id: string; queued: number }>("/api/pipeline/run-cohort", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_ids: selectedCohort,
          action: "run_analysis",
          preview: dryRun,
        }),
      });
      // Subscribe to the Redis relay so worker progress streams live to the panel.
      pipeline.subscribeToRun(res.run_id);
    } catch (e) {
      setUiError(e instanceof Error ? e.message : "Failed to queue cohort analysis");
    } finally {
      setBusyAction(null);
    }
  };

  const allFilteredSelected =
    filteredPatients.length > 0 &&
    filteredPatients.every((p) => selectedCohort.includes(p.patient_id));

  const toggleAllFiltered = () => {
    if (allFilteredSelected) {
      const filtered = new Set(filteredPatients.map((p) => p.patient_id));
      setSelectedCohort((prev) => prev.filter((id) => !filtered.has(id)));
      return;
    }
    setSelectedCohort((prev) => {
      const next = new Set(prev);
      for (const p of filteredPatients) next.add(p.patient_id);
      return Array.from(next);
    });
  };

  const singleStats = summary?.encounters;
  const canCodeNewSingle = !!singlePatient && !pipeline.running && (singleStats?.uncoded ?? 0) > 0;
  const canRecodeSingle = !!singlePatient && !pipeline.running && (singleStats?.total ?? 0) > 0;
  const canRunAnalysisSingle = !!singlePatient && !pipeline.running && (singleStats?.coded ?? 0) > 0;
  const canFullSingle = !!singlePatient && !pipeline.running && (singleStats?.total ?? 0) > 0;
  const canCohortRun = selectedCohort.length > 0 && !pipeline.running;

  const selectedCohortLabel = `${selectedCohort.length} selected`;

  const actionButtonText = (action: ActionKind) => {
    if (busyAction !== action) return actionLabel(action);
    return "Working…";
  }

  const fallbackCount = pipeline.encounterLog.filter((e) => e.fallbackUsed).length;
  const failedCount = pipeline.encounterLog.filter((e) => e.outcome === "failed").length;

  return (
    <Box sx={{ maxWidth: 1000, mx: "auto", py: 4, px: 3 }}>
      <Card variant="outlined" sx={{ mb: 2, bgcolor: "action.hover" }}>
        <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
            <Typography variant="caption" color="text.secondary">
              Coding method
            </Typography>
            <Chip
              size="small"
              label={backendLabel(extractorStatus)}
              color={extractorStatus?.backend === "auto" ? "success" : "primary"}
              sx={{ fontWeight: 600, fontFamily: "var(--font-mono)" }}
            />
            {extractorStatus?.model_version && <Chip size="small" label={`v${extractorStatus.model_version}`} variant="outlined" />}
            {extractorStatus?.strict && <Chip size="small" label="Strict" color="error" variant="outlined" />}
            {extractorStatus?.fallback_enabled && extractorStatus.backend !== "llm" && (
              <Chip size="small" label="Fallback enabled" color="warning" variant="outlined" />
            )}
            {extractorStatus?.model_endpoint && (
              <Typography variant="caption" sx={{ color: "text.secondary", fontFamily: "var(--font-mono)" }}>
                {extractorStatus.model_endpoint}
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="h5" sx={{ mb: 2 }}>Pipeline</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Search, review current state, and run coding actions without technical setup.
          </Typography>

          <ToggleButtonGroup
            color="primary"
            exclusive
            value={mode}
            onChange={(_, v) => v && setMode(v)}
            sx={{ mb: 2 }}
          >
            <ToggleButton value="single">Single patient</ToggleButton>
            <ToggleButton value="cohort">Bulk / cohort</ToggleButton>
          </ToggleButtonGroup>

          <Accordion sx={{ mb: 2 }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="body2">Options</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <FormControlLabel
                control={<Checkbox checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} color="warning" />}
                label="Preview only (dry run)"
              />
            </AccordionDetails>
          </Accordion>

          {uiInfo && <Alert severity="info" sx={{ mb: 2 }}>{uiInfo}</Alert>}
          {uiError && <Alert severity="error" sx={{ mb: 2 }}>{uiError}</Alert>}
          {pipeline.error && !pipeline.running && <Alert severity="error" sx={{ mb: 2 }}>{pipeline.error}</Alert>}

          {mode === "single" && (
            <Stack spacing={2}>
              <Autocomplete
                options={patients}
                loading={patientsLoading}
                getOptionLabel={(o) => o.patient_id}
                onInputChange={(_, value) => setPatientQuery(value)}
                onChange={(_, value) => {
                  setSelectedPatientId(value?.patient_id ?? null);
                  setUiError(null);
                  setUiInfo(null);
                }}
                renderOption={(props, option) => (
                  <li {...props} key={option.patient_id}>
                    <Stack width="100%">
                      <Typography sx={{ fontFamily: "var(--font-mono)" }}>{option.patient_id}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {option.encounter_count} encounters · {Math.round((option.progress ?? 0) * 100)}% reviewed
                      </Typography>
                    </Stack>
                  </li>
                )}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Search patient (NHS number)"
                    placeholder="e.g. 999 000 0001 or 999-000-0001"
                    helperText={
                      parsedTypedIds.length > 0
                        ? `${parsedTypedIds.length} id recognised${invalidTypedIds.length > 0 ? ` · ${invalidTypedIds.length} may fail Modulus 11` : ""}`
                        : "Type or paste NHS number"
                    }
                  />
                )}
              />

              {parsedTypedIds.length > 0 && (
                <Stack direction="row" spacing={1} alignItems="center">
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => setSelectedPatientId(parsedTypedIds[0])}
                  >
                    Use typed ID
                  </Button>
                  <Typography variant="caption" sx={{ fontFamily: "var(--font-mono)" }}>
                    {parsedTypedIds[0]}
                  </Typography>
                </Stack>
              )}

              {summaryLoading && <LinearProgress />}

              {singlePatient && summary && (
                <Card variant="outlined">
                  <CardContent>
                    <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1 }}>
                      <Chip label={`Total ${summary.encounters.total}`} />
                      <Chip label={`Coded ${summary.encounters.coded}`} color="success" variant="outlined" />
                      <Chip label={`Uncoded ${summary.encounters.uncoded}`} color="warning" variant="outlined" />
                      <Chip label={`Progress ${summary.encounters.progress_pct}%`} color="primary" variant="outlined" />
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      Classification: {summary.encounters.clinical} clinical, {summary.encounters.admin_only} admin, {summary.encounters.document_transfer} document transfer
                    </Typography>
                    <Typography variant="caption" display="block" color="text.secondary">
                      Date range: {summary.encounters.date_from ?? "—"} to {summary.encounters.date_to ?? "—"}
                    </Typography>
                    <Typography variant="caption" display="block" color="text.secondary">
                      Analysis: {summary.analysis.episode_count} episodes, {summary.analysis.safety_alert_count} safety alerts
                    </Typography>
                    {summary.semantic_tag_counts.length > 0 && (
                      <List dense sx={{ mt: 1 }}>
                        {summary.semantic_tag_counts.slice(0, 6).map((x) => (
                          <ListItem key={x.semantic_tag} sx={{ py: 0 }}>
                            <ListItemText primary={`${x.semantic_tag}: ${x.count}`} />
                          </ListItem>
                        ))}
                      </List>
                    )}
                  </CardContent>
                </Card>
              )}

              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>Actions</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Button
                    variant="contained"
                    startIcon={<PlayArrowIcon />}
                    disabled={!canCodeNewSingle || busyAction !== null}
                    onClick={() => runSingleCoding("code_new")}
                  >
                    {actionButtonText("code_new")}
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<RefreshIcon />}
                    color="warning"
                    disabled={!canRecodeSingle || busyAction !== null}
                    onClick={() => runSingleCoding("recode_all")}
                  >
                    {actionButtonText("recode_all")}
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<AnalyticsIcon />}
                    disabled={!canRunAnalysisSingle || busyAction !== null}
                    onClick={runSingleAnalysis}
                  >
                    {actionButtonText("run_analysis")}
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<BoltIcon />}
                    disabled={!canFullSingle || busyAction !== null}
                    onClick={() => runSingleCoding("full_pipeline")}
                  >
                    {actionButtonText("full_pipeline")}
                  </Button>
                  {pipeline.running && (
                    <Button variant="outlined" color="error" onClick={pipeline.cancel}>Cancel</Button>
                  )}
                </Stack>
              </Paper>

              {pipeline.running && (
                <Alert severity="info">
                  {pipeline.status ?? "Pipeline running…"}
                  {pipeline.live && (
                    <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap">
                      <Chip size="small" label={`${pipeline.live.processed_encounters} done`} />
                      <Chip size="small" label={`${pipeline.live.queued_for_review ?? 0} queued`} />
                      {(pipeline.live.auto_approved ?? 0) > 0 && (
                        <Chip size="small" color="success" label={`${pipeline.live.auto_approved} auto-approved`} />
                      )}
                      {failedCount > 0 && <Chip size="small" color="error" label={`${failedCount} failed`} />}
                      {fallbackCount > 0 && <Chip size="small" color="warning" label={`${fallbackCount} fallback`} />}
                    </Stack>
                  )}
                </Alert>
              )}

              <EncounterLogTable rows={pipeline.encounterLog} />
              {pipeline.result && !pipeline.running && (
                <RunResultCard result={pipeline.result} onGoToReview={onNavigateTab ?? (() => {})} />
              )}
            </Stack>
          )}

          {mode === "cohort" && (
            <Stack spacing={2}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <TextField
                  label="Filter NHS number"
                  value={patientQuery}
                  onChange={(e) => setPatientQuery(e.target.value)}
                  sx={{ width: 280 }}
                />
                <Button variant="outlined" onClick={toggleAllFiltered}>
                  {allFilteredSelected ? "Deselect filtered" : "Select filtered"}
                </Button>
                <Chip label={selectedCohortLabel} />
              </Stack>

              <Box sx={{ maxHeight: 320, overflow: "auto" }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell padding="checkbox" />
                      <TableCell>NHS number</TableCell>
                      <TableCell align="right">Encounters</TableCell>
                      <TableCell align="right">Progress</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {filteredPatients.map((p) => {
                      const checked = selectedCohort.includes(p.patient_id);
                      return (
                        <TableRow key={p.patient_id} hover>
                          <TableCell padding="checkbox">
                            <Checkbox
                              checked={checked}
                              onChange={() =>
                                setSelectedCohort((prev) =>
                                  checked
                                    ? prev.filter((id) => id !== p.patient_id)
                                    : [...prev, p.patient_id],
                                )
                              }
                            />
                          </TableCell>
                          <TableCell sx={{ fontFamily: "var(--font-mono)" }}>{p.patient_id}</TableCell>
                          <TableCell align="right">{p.encounter_count}</TableCell>
                          <TableCell align="right">{Math.round((p.progress ?? 0) * 100)}%</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Box>

              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>Bulk actions</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Button
                    variant="contained"
                    startIcon={<PlayArrowIcon />}
                    disabled={!canCohortRun || busyAction !== null}
                    onClick={() => runCohortCoding("code_new")}
                  >
                    {actionButtonText("code_new")}
                  </Button>
                  <Button
                    variant="outlined"
                    color="warning"
                    startIcon={<RefreshIcon />}
                    disabled={!canCohortRun || busyAction !== null}
                    onClick={() => runCohortCoding("recode_all")}
                  >
                    {actionButtonText("recode_all")}
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<BoltIcon />}
                    disabled={!canCohortRun || busyAction !== null}
                    onClick={() => runCohortCoding("full_pipeline")}
                  >
                    {actionButtonText("full_pipeline")}
                  </Button>
                  <Button
                    variant="outlined"
                    color="secondary"
                    startIcon={<AnalyticsIcon />}
                    disabled={!canCohortRun || busyAction !== null}
                    onClick={runCohortAnalysis}
                  >
                    {busyAction === "run_analysis" ? "Queuing…" : "Run analysis"}
                  </Button>
                  {pipeline.running && <Button color="error" variant="outlined" onClick={pipeline.cancel}>Cancel</Button>}
                </Stack>
              </Paper>

              {pipeline.running && (
                <Alert severity="info">
                  {pipeline.status ?? "Pipeline running…"}
                </Alert>
              )}

              {selectedCohort.length > 0 && (
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Per-patient progress</Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Patient</TableCell>
                        <TableCell align="right">Done</TableCell>
                        <TableCell align="right">Queued</TableCell>
                        <TableCell align="right">Failed</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {selectedCohort.map((pid) => {
                        const p = cohortProgress[pid] ?? { done: 0, queued: 0, failed: 0 };
                        return (
                          <TableRow key={pid}>
                            <TableCell sx={{ fontFamily: "var(--font-mono)" }}>{pid}</TableCell>
                            <TableCell align="right">{p.done}</TableCell>
                            <TableCell align="right">{p.queued}</TableCell>
                            <TableCell align="right">{p.failed}</TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </Paper>
              )}

              <EncounterLogTable rows={pipeline.encounterLog} showPatientColumn />
              {pipeline.result && !pipeline.running && (
                <RunResultCard result={pipeline.result} onGoToReview={onNavigateTab ?? (() => {})} />
              )}
            </Stack>
          )}

          <Divider sx={{ my: 3 }} />
          <Typography variant="caption" color="text.secondary">
            Worker fan-out and queueing are managed automatically in the background.
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
