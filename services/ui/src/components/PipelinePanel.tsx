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
import { exportMedSpaCyTraining } from "@/lib/api";
import { usePipeline } from "@/context/PipelineContext";

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
          </Stack>

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
