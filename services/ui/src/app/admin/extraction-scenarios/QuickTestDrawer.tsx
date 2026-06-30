/**
 * QuickTestDrawer -- paste text, run the full production pipeline, see per-stage results.
 *
 * Encounter mode: creates Patient + Encounter -> pd-gp-encounter-coding.
 * Referral mode:  creates Patient + ReferralRequest + DR + Chunks -> pd-referral-assessment.
 *
 * Polls GET /extraction-scenarios/runs/:run_id until status = "completed" | "failed".
 * A "Clear" button removes the ephemeral demo patient nodes from Neo4j.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { SegmentedTabs } from "@leo/design-system";

import { deleteQuickRun, pollQuickRun, startQuickRun } from "./api";
import type { QuickRunMode, QuickRunResult } from "./types";
import QuickTestResults from "./QuickTestResults";

const POLL_MS = 2000;

const GUIDELINES = [
  { value: "", label: "None (extraction only)" },
  { value: "NG12", label: "NG12 -- Suspected cancer (all sites)" },
  { value: "NG12-lower-gi", label: "NG12 -- Lower GI (colorectal)" },
  { value: "NG12-upper-gi", label: "NG12 -- Upper GI (oesophago-gastric)" },
  { value: "NG12-lung", label: "NG12 -- Lung" },
  { value: "NG12-breast", label: "NG12 -- Breast" },
  { value: "NG12-urology", label: "NG12 -- Urology (bladder / kidney / prostate)" },
  { value: "NG12-haem", label: "NG12 -- Haematological" },
];

const MODE_TABS = [
  { id: "encounter", label: "GP encounter note" },
  { id: "referral", label: "Referral letter" },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function QuickTestDrawer({ open, onClose }: Props) {
  const [mode, setMode] = useState<QuickRunMode>("encounter");
  const [text, setText] = useState("");
  const [patientAge, setPatientAge] = useState<string>("");
  const [patientSex, setPatientSex] = useState<string>("unknown");
  const [guidelineId, setGuidelineId] = useState("");
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [result, setResult] = useState<QuickRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stageLabel, setStageLabel] = useState("Waiting for pipeline worker...");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const startPolling = useCallback(
    (id: string) => {
      pollRef.current = setInterval(async () => {
        try {
          const data = await pollQuickRun(id);
          if (data.stage_snapshots) {
            const stages = Object.keys(data.stage_snapshots);
            if (stages.length) setStageLabel(`Completed: ${stages.join(", ")}`);
          }
          if (data.status === "completed" || data.status === "failed") {
            stopPolling();
            setResult(data);
            setRunning(false);
            if (data.status === "failed") setError("The pipeline run failed.");
          }
        } catch (err) {
          stopPolling();
          setRunning(false);
          setError(String(err));
        }
      }, POLL_MS);
    },
    [stopPolling],
  );

  const handleRun = useCallback(async () => {
    setError(null);
    setResult(null);
    setRunning(true);
    setStageLabel("Publishing to pipeline worker...");
    const ageNum = patientAge.trim() ? Number(patientAge) : undefined;
    try {
      const resp = await startQuickRun({
        mode,
        text,
        patient_age: ageNum != null && !Number.isNaN(ageNum) ? ageNum : undefined,
        patient_sex: patientSex !== "unknown" ? patientSex : undefined,
        guideline_id: guidelineId || undefined,
      });
      setRunId(resp.run_id);
      startPolling(resp.run_id);
    } catch (err) {
      setRunning(false);
      setError(String(err));
    }
  }, [mode, text, guidelineId, startPolling]);

  const handleClear = useCallback(async () => {
    if (!runId) return;
    try {
      await deleteQuickRun(runId);
    } catch {
      // best-effort
    }
    setRunId(null);
    setResult(null);
    setError(null);
    setStageLabel("Waiting for pipeline worker...");
  }, [runId]);

  const handleClose = useCallback(() => {
    stopPolling();
    onClose();
  }, [stopPolling, onClose]);

  const canRun = text.trim().length > 0 && !running;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={handleClose}
      PaperProps={{ sx: { width: { xs: "100vw", sm: 720 }, p: 3, display: "flex", flexDirection: "column" } }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography variant="h6" component="h2">Quick pipeline test</Typography>
        <IconButton aria-label="Close quick test" onClick={handleClose} size="small">
          <CloseIcon />
        </IconButton>
      </Stack>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Paste text below and run the full production pipeline against a temporary demo patient.
        You will see what each stage extracts.
      </Typography>

      <SegmentedTabs
        tabs={MODE_TABS}
        value={mode}
        onChange={(v) => { setMode(v as QuickRunMode); setResult(null); setError(null); }}
        aria-label="Pipeline mode"
      />

      <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
        <TextField
          label="Age"
          size="small"
          type="number"
          value={patientAge}
          onChange={(e) => setPatientAge(e.target.value)}
          inputProps={{ min: 0, max: 120, step: 1 }}
          InputProps={{ endAdornment: <InputAdornment position="end">yrs</InputAdornment> }}
          sx={{ width: 110 }}
          aria-label="Patient age in years"
        />
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel id="sex-label">Sex</InputLabel>
          <Select
            labelId="sex-label"
            value={patientSex}
            label="Sex"
            onChange={(e) => setPatientSex(e.target.value)}
          >
            <MenuItem value="unknown">Not specified</MenuItem>
            <MenuItem value="male">Male</MenuItem>
            <MenuItem value="female">Female</MenuItem>
          </Select>
        </FormControl>
      </Stack>

      {mode === "referral" && (
        <FormControl size="small" sx={{ mt: 1.5, minWidth: 260 }}>
          <InputLabel id="guideline-label">Guideline (for completeness)</InputLabel>
          <Select
            labelId="guideline-label"
            value={guidelineId}
            label="Guideline (for completeness)"
            onChange={(e) => setGuidelineId(e.target.value)}
          >
            {GUIDELINES.map((g) => (
              <MenuItem key={g.value} value={g.value}>{g.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      <TextField
        multiline
        rows={10}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={
          mode === "encounter"
            ? "Paste GP consultation text here..."
            : "Paste referral letter text here..."
        }
        sx={{ mt: 2, flex: "0 0 auto" }}
        aria-label="Clinical text input"
      />

      <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
        <Button
          variant="contained"
          onClick={handleRun}
          disabled={!canRun}
          startIcon={running ? <CircularProgress size={16} aria-label="Loading" role="status" /> : undefined}
        >
          {running ? "Running..." : "Run pipeline"}
        </Button>
        {result && (
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteOutlineIcon />}
            onClick={handleClear}
            disabled={running}
          >
            Clear demo patient
          </Button>
        )}
      </Stack>

      {running && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {stageLabel}
        </Typography>
      )}

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}

      {result && result.status === "completed" && (
        <>
          <Divider sx={{ mt: 3, mb: 1 }} />
          <QuickTestResults result={result} />
        </>
      )}
    </Drawer>
  );
}
