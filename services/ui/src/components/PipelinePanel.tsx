"use client";

import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Divider,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { exportMedSpaCyTraining, enqueueConsensus, cleanPatients } from "@/lib/api";
import { usePipeline } from "@/context/PipelineContext";
import { api } from "@/lib/api";

export default function PipelinePanel() {
  const [patientIds, setPatientIds] = useState("");
  const [maxEnc, setMaxEnc] = useState("50");
  const [dryRun, setDryRun] = useState(false);
  const [workers, setWorkers] = useState("4");
  const [exportName, setExportName] = useState("medspacy_v1");
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<{
    entity_count: number;
    kb_count: number;
    encounter_count: number;
  } | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const pipeline = usePipeline();
  const [recoding, setRecoding] = useState(false);
  const [recodeResult, setRecodeResult] = useState<string | null>(null);
  const [recodeError, setRecodeError] = useState<string | null>(null);
  const [consensusLoading, setConsensusLoading] = useState(false);
  const [consensusResult, setConsensusResult] = useState<string | null>(null);
  const [consensusError, setConsensusError] = useState<string | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [cleanResult, setCleanResult] = useState<string | null>(null);
  const [cleanError, setCleanError] = useState<string | null>(null);

  async function handleConsensus() {
    if (patientIdList.length === 0) return;
    setConsensusLoading(true);
    setConsensusResult(null);
    setConsensusError(null);
    try {
      const result = await enqueueConsensus({
        patient_ids: patientIdList,
        dry_run: dryRun,
      });
      setConsensusResult(
        `Consensus queued for ${result.patients_enqueued} patient(s) — run ${result.run_id.slice(0, 8)}`
      );
    } catch (e) {
      setConsensusError(e instanceof Error ? e.message : "Failed to enqueue consensus");
    } finally {
      setConsensusLoading(false);
    }
  }

  async function handleClean() {
    if (patientIdList.length === 0) return;
    setCleaning(true);
    setCleanResult(null);
    setCleanError(null);
    try {
      const result = await cleanPatients({ patient_ids: patientIdList });
      const counts = Object.entries(result.totals)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => `${k}: ${v}`)
        .join(", ");
      setCleanResult(
        `Cleaned ${result.patients_cleaned} patient(s)${counts ? ` — ${counts}` : ""}`
      );
    } catch (e) {
      setCleanError(e instanceof Error ? e.message : "Failed to clean patients");
    } finally {
      setCleaning(false);
    }
  }

  async function handleRecode() {
    if (patientIdList.length === 0) return;
    setRecoding(true);
    setRecodeResult(null);
    setRecodeError(null);
    try {
      const result = await api.post<{ run_id: string; queued: number }>("/pipeline/enqueue-recode", {
        patient_ids: patientIdList,
        dry_run: dryRun,
      });
      setRecodeResult(`Re-code queued for ${result.queued} patient(s) — run ${result.run_id.slice(0, 8)}`);
    } catch (e) {
      setRecodeError(e instanceof Error ? e.message : "Failed to enqueue re-code");
    } finally {
      setRecoding(false);
    }
  }

  async function handleExportMedSpaCy() {
    setExporting(true);
    setExportResult(null);
    setExportError(null);
    try {
      const ids = patientIds.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
      const result = await exportMedSpaCyTraining({
        export_name: exportName,
        patient_ids: ids.length > 0 ? ids : undefined,
      });
      setExportResult({
        entity_count: result.entity_count,
        kb_count: result.kb_count,
        encounter_count: result.encounter_count,
      });
    } catch (e) {
      setExportResult(null);
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const patientIdList = patientIds
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  function handleRun() {
    if (patientIdList.length === 0) return;

    const maxEncVal = parseInt(maxEnc, 10);
    const workerVal = Math.max(1, Math.min(8, parseInt(workers, 10) || 4));

    pipeline.start({
      patientIds: patientIdList,
      maxEncountersPerPatient: Number.isNaN(maxEncVal) ? undefined : maxEncVal,
      dryRun,
      workers: workerVal,
    });
  }

  return (
    <Box sx={{ maxWidth: 960, mx: "auto", py: 4, px: 3 }}>
      <Card>
        <CardContent sx={{ p: 3 }}>
          {/* ── Processing ── */}
          <Typography variant="h6" sx={{ mb: 2 }}>
            Process Records
          </Typography>

          <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="flex-end">
            <TextField
              label="Patient IDs (comma or space separated)"
              value={patientIds}
              onChange={(e) => setPatientIds(e.target.value)}
              placeholder="e.g. 4202301609, 4203796334"
              sx={{ flex: "1 1 200px" }}
              InputProps={{ sx: { fontFamily: "var(--font-mono)" } }}
            />
            <TextField
              label="Max enc."
              type="number"
              value={maxEnc}
              onChange={(e) => setMaxEnc(e.target.value)}
              sx={{ width: 110 }}
              InputProps={{ sx: { fontFamily: "var(--font-mono)" } }}
            />
            <TextField
              label="Threads"
              type="number"
              value={workers}
              onChange={(e) => setWorkers(e.target.value)}
              inputProps={{ min: 1, max: 8 }}
              sx={{ width: 100 }}
              InputProps={{ sx: { fontFamily: "var(--font-mono)" } }}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  color="primary"
                />
              }
              label="Preview"
              sx={{ pb: 0.5 }}
            />
            <Button
              variant="contained"
              color="primary"
              onClick={handleRun}
              disabled={pipeline.running || patientIdList.length === 0}
              title={
                patientIdList.length === 0
                  ? "Enter at least one patient ID"
                  : undefined
              }
            >
              {pipeline.running ? "Running\u2026" : "Process Records"}
            </Button>
            <Button
              variant="outlined"
              color="secondary"
              onClick={handleRecode}
              disabled={recoding || pipeline.running || patientIdList.length === 0}
              title="Re-run extraction only — classification already done"
            >
              {recoding ? "Queuing\u2026" : "Re-code Only"}
            </Button>
            <Button
              variant="outlined"
              color="primary"
              onClick={handleConsensus}
              disabled={consensusLoading || pipeline.running || patientIdList.length === 0}
              title="Multi-model consensus extraction via worker queue"
            >
              {consensusLoading ? "Queuing\u2026" : "Consensus"}
            </Button>
            <Button
              variant="outlined"
              color="warning"
              onClick={handleClean}
              disabled={cleaning || pipeline.running || patientIdList.length === 0}
              title="Remove all pipeline artefacts for these patients"
            >
              {cleaning ? "Cleaning\u2026" : "Clean"}
            </Button>
          </Stack>
          {recodeResult && (
            <Alert severity="success" sx={{ mt: 1.5 }} onClose={() => setRecodeResult(null)}>
              {recodeResult}
            </Alert>
          )}
          {recodeError && (
            <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setRecodeError(null)}>
              {recodeError}
            </Alert>
          )}
          {consensusResult && (
            <Alert severity="success" sx={{ mt: 1.5 }} onClose={() => setConsensusResult(null)}>
              {consensusResult}
            </Alert>
          )}
          {consensusError && (
            <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setConsensusError(null)}>
              {consensusError}
            </Alert>
          )}
          {cleanResult && (
            <Alert severity="info" sx={{ mt: 1.5 }} onClose={() => setCleanResult(null)}>
              {cleanResult}
            </Alert>
          )}
          {cleanError && (
            <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setCleanError(null)}>
              {cleanError}
            </Alert>
          )}

          {/* Inline summary when modal is minimized (user on Pipeline page) */}
          {!pipeline.showModal && pipeline.running && pipeline.live && (
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mt: 1.5 }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: "success.light",
                  animation: "pulse 1.5s infinite",
                  "@keyframes pulse": {
                    "0%, 100%": { opacity: 1 },
                    "50%": { opacity: 0.4 },
                  },
                }}
              />
              <Typography variant="subtitle2" color="text.primary">
                {pipeline.status} &mdash; Processed: {pipeline.live.processed_encounters}
              </Typography>
              <Button
                variant="contained"
                size="small"
                onClick={() => pipeline.setShowModal(true)}
              >
                Expand
              </Button>
            </Stack>
          )}

          {/* Last result when not running */}
          {pipeline.result && !pipeline.running && (
            <Alert severity="success" sx={{ mt: 1.5, fontFamily: "var(--font-mono)", fontSize: 13 }}>
              <Stack
                direction="row"
                flexWrap="wrap"
                spacing={2}
                divider={<Divider orientation="vertical" flexItem />}
              >
                <span>Processed: {pipeline.result.processed_encounters}</span>
                {(pipeline.result.auto_approved ?? 0) > 0 && (
                  <span>Auto-approved: {pipeline.result.auto_approved}</span>
                )}
                <span>Queued: {pipeline.result.queued_for_review}</span>
                <span>Span Issues: {pipeline.result.rejected_hard_fail}</span>
                <span>Warnings: {pipeline.result.warnings_only}</span>
              </Stack>
            </Alert>
          )}

          {pipeline.error && !pipeline.running && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {pipeline.error}
            </Alert>
          )}

          {/* ── Export ── */}
          <Divider sx={{ my: 3 }} />

          <Typography variant="h6" sx={{ mb: 2 }}>
            Export Training Data
          </Typography>

          <Stack direction="row" spacing={1.5} alignItems="flex-end" flexWrap="wrap">
            <TextField
              label="Export name"
              value={exportName}
              onChange={(e) => setExportName(e.target.value)}
              placeholder="medspacy_v1"
              InputProps={{ sx: { fontFamily: "var(--font-mono)" } }}
            />
            <Button
              variant="contained"
              color="secondary"
              onClick={handleExportMedSpaCy}
              disabled={exporting}
            >
              {exporting ? "Exporting\u2026" : "Export training data"}
            </Button>
          </Stack>

          <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
            Uses patient IDs above if set; otherwise exports all approved data.
          </Typography>

          {exportResult && (
            <Alert severity="success" sx={{ mt: 1 }}>
              Exported: {exportResult.entity_count} entities, {exportResult.kb_count} KB rows, {exportResult.encounter_count} encounters
            </Alert>
          )}

          {exportError && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {exportError}
            </Alert>
          )}
        </CardContent>
      </Card>

    </Box>
  );
}
