"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import GroupOutlinedIcon from "@mui/icons-material/GroupOutlined";
import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

// -- Types -------------------------------------------------------------------

interface PatientOption {
  patient_id: string;
  encounter_count: number;
}

type RunMode = "pick" | "all";

type PipelineAction =
  | "full_pipeline"
  | "code_new"
  | "recode_all"
  | "run_analysis";

const ACTION_LABELS: Record<PipelineAction, { label: string; hint: string }> = {
  full_pipeline: {
    label: "Full pipeline",
    hint: "Code encounters and run analysis - the most thorough option",
  },
  code_new: {
    label: "New records only",
    hint: "Only process encounters that have not been coded yet",
  },
  recode_all: {
    label: "Re-code everything",
    hint: "Wipe existing codes and start again - use after training a new model",
  },
  run_analysis: {
    label: "Analyse only",
    hint: "Re-run analysis on already-coded encounters, without re-coding",
  },
};

interface RunRecord {
  startedAt: string;
  duration: number;
  patients: number;
  action: PipelineAction;
  status: "ok" | "error";
}

// -- Fetch helpers -----------------------------------------------------------

async function fetchPatients(): Promise<PatientOption[]> {
  const res = await fetch("/api/patients", { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<PatientOption[]>;
}

// -- Component ---------------------------------------------------------------

export default function RunSection() {
  // Mode
  const [mode, setMode] = useState<RunMode>("pick");
  const [action, setAction] = useState<PipelineAction>("full_pipeline");
  const [dryRun, setDryRun] = useState(false);

  // Patient picker state
  const [allPatients, setAllPatients] = useState<PatientOption[]>([]);
  const [patientsLoading, setPatientsLoading] = useState(false);
  const [patientsError, setPatientsError] = useState("");
  const [selected, setSelected] = useState<PatientOption[]>([]);

  // Run state
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Load patient list on mount
  useEffect(() => {
    setPatientsLoading(true);
    fetchPatients()
      .then((pts) => {
        setAllPatients(pts);
        setPatientsError("");
      })
      .catch(() => setPatientsError("Could not load the patient list. You can still type IDs manually below."))
      .finally(() => setPatientsLoading(false));
  }, []);

  const scrollToBottom = useCallback(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const appendLog = useCallback(
    (line: string) => {
      setLog((prev) => [...prev, line]);
      setTimeout(scrollToBottom, 50);
    },
    [scrollToBottom],
  );

  const resolvePatientIds = useCallback((): string[] => {
    if (mode === "all") {
      return allPatients.map((p) => p.patient_id);
    }
    return selected.map((p) => p.patient_id);
  }, [mode, allPatients, selected]);

  const startRun = useCallback(async () => {
    const ids = resolvePatientIds();
    if (ids.length === 0) {
      setError(
        mode === "pick"
          ? "Please select at least one patient."
          : "No patients found to run.",
      );
      return;
    }

    setRunning(true);
    setError("");
    setLog([]);
    setProgress(0);
    const started = Date.now();
    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const start = await fetch("/api/pipeline/run-cohort", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ patient_ids: ids, action, preview: dryRun }),
        signal: abort.signal,
      });
      if (!start.ok) throw new Error(`Server returned ${start.status}`);
      const startPayload = (await start.json()) as { run_id?: string };
      if (!startPayload.run_id) throw new Error("Run ID missing from start response.");

      appendLog(
        `Queued run ${startPayload.run_id.slice(0, 8)} for ${ids.length} patient${ids.length === 1 ? "" : "s"}. Waiting for worker...`,
      );

      const res = await fetch(
        `/api/pipeline/progress/${encodeURIComponent(startPayload.run_id)}`,
        {
          credentials: "include",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            Accept: "text/event-stream",
          },
          signal: abort.signal,
        },
      );
      if (!res.ok || !res.body) throw new Error(`Server returned ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";

        for (const raw of lines) {
          if (!raw.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(raw.slice(6));
            if (evt.type === "run_started" || evt.type === "patient_started") {
              appendLog("Running...");
              setProgress(15);
            }
            if (evt.type === "encounter_started") setProgress((p) => Math.max(p, 25));
            if (evt.type === "term_extraction_started") setProgress((p) => Math.max(p, 40));
            if (evt.type === "persist_completed") setProgress((p) => Math.max(p, 75));
            if (
              evt.type === "run_completed" ||
              evt.type === "pipeline_done" ||
              evt.type === "extraction_done"
            )
              setProgress(100);
            if (evt.message) appendLog(evt.message);
            if (evt.type === "pipeline_error") appendLog(`Error: ${evt.message}`);
          } catch {
            appendLog(raw.slice(6));
          }
        }
      }

      setProgress(100);
      appendLog("Pipeline finished.");
      setRuns((prev) => [
        {
          startedAt: new Date(started).toLocaleTimeString(),
          duration: Math.round((Date.now() - started) / 1000),
          patients: ids.length,
          action,
          status: "ok",
        },
        ...prev,
      ]);
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        const msg = err instanceof Error ? err.message : "Something went wrong.";
        setError(msg);
        appendLog(`Error: ${msg}`);
        setRuns((prev) => [
          {
            startedAt: new Date(started).toLocaleTimeString(),
            duration: Math.round((Date.now() - started) / 1000),
            patients: ids.length,
            action,
            status: "error",
          },
          ...prev,
        ]);
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }, [resolvePatientIds, mode, action, dryRun, appendLog]);

  const stopRun = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
    appendLog("Stopped by user.");
  }, [appendLog]);

  const removePatient = useCallback((id: string) => {
    setSelected((prev) => prev.filter((p) => p.patient_id !== id));
  }, []);

  const canRun =
    !running &&
    (mode === "all" ? allPatients.length > 0 : selected.length > 0);

  const runLabel =
    mode === "all"
      ? `Run for all ${allPatients.length.toLocaleString()} patients`
      : selected.length > 0
        ? `Run for ${selected.length} patient${selected.length === 1 ? "" : "s"}`
        : "Select patients to run";

  // -- Render ----------------------------------------------------------------

  return (
    <Stack gap={2.5}>
      {error && (
        <Alert severity="error" onClose={() => setError("")}>
          {error}
        </Alert>
      )}
      {patientsError && (
        <Alert severity="warning" onClose={() => setPatientsError("")}>
          {patientsError}
        </Alert>
      )}

      {/* -- Mode selector -------------------------------------------------- */}
      <Card variant="outlined">
        <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
            Who should we process?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Pick specific patients, or run the pipeline for everyone.
          </Typography>

          <ToggleButtonGroup
            value={mode}
            exclusive
            onChange={(_, v) => { if (v) setMode(v as RunMode); }}
            aria-label="Patient selection mode"
            size="small"
            sx={{ mb: 2.5 }}
          >
            <ToggleButton value="pick" aria-label="Pick specific patients">
              <GroupOutlinedIcon sx={{ mr: 0.75, fontSize: 18 }} />
              Pick patients
            </ToggleButton>
            <ToggleButton value="all" aria-label="All patients">
              <PeopleAltOutlinedIcon sx={{ mr: 0.75, fontSize: 18 }} />
              {patientsLoading
                ? "All patients"
                : `All ${allPatients.length.toLocaleString()} patients`}
            </ToggleButton>
          </ToggleButtonGroup>

          {/* Pick mode: autocomplete + chips */}
          {mode === "pick" && (
            <Box>
              {patientsLoading ? (
                <Skeleton variant="rounded" height={56} />
              ) : (
                <Autocomplete<PatientOption, false, false, false>
                  options={allPatients.filter(
                    (p) => !selected.some((s) => s.patient_id === p.patient_id),
                  )}
                  getOptionLabel={(o) => o.patient_id}
                  renderOption={(props, option) => (
                    <Box component="li" {...props} key={option.patient_id}>
                      <Stack direction="row" justifyContent="space-between" width="100%">
                        <Typography variant="body2">{option.patient_id}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {option.encounter_count}{" "}
                          {option.encounter_count === 1 ? "encounter" : "encounters"}
                        </Typography>
                      </Stack>
                    </Box>
                  )}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Search by patient ID"
                      placeholder="Type to filter..."
                      size="small"
                      InputProps={{
                        ...params.InputProps,
                        endAdornment: (
                          <>
                            {patientsLoading && (
                              <CircularProgress size={16} aria-label="Loading patients" />
                            )}
                            {params.InputProps.endAdornment}
                          </>
                        ),
                      }}
                    />
                  )}
                  onChange={(_, value) => {
                    if (value) {
                      setSelected((prev) =>
                        prev.some((p) => p.patient_id === value.patient_id)
                          ? prev
                          : [...prev, value],
                      );
                    }
                  }}
                  value={null}
                  blurOnSelect
                  clearOnBlur
                  disabled={running}
                  noOptionsText="No matching patients"
                />
              )}

              {/* Selected chips */}
              {selected.length > 0 && (
                <Box sx={{ mt: 1.5 }}>
                  <Stack
                    direction="row"
                    flexWrap="wrap"
                    gap={0.75}
                    role="list"
                    aria-label="Selected patients"
                  >
                    {selected.map((p) => (
                      <Tooltip
                        key={p.patient_id}
                        title={`${p.encounter_count} encounter${p.encounter_count === 1 ? "" : "s"}`}
                      >
                        <Chip
                          role="listitem"
                          label={p.patient_id}
                          size="small"
                          onDelete={running ? undefined : () => removePatient(p.patient_id)}
                          color="primary"
                          variant="outlined"
                        />
                      </Tooltip>
                    ))}
                  </Stack>
                  {!running && (
                    <Button
                      size="small"
                      variant="text"
                      color="error"
                      sx={{ mt: 0.5, fontSize: "0.75rem" }}
                      onClick={() => setSelected([])}
                    >
                      Clear all
                    </Button>
                  )}
                </Box>
              )}

              {selected.length === 0 && !patientsLoading && (
                <Typography variant="caption" color="text.disabled" sx={{ mt: 1, display: "block" }}>
                  Search above and click a patient to add them.
                </Typography>
              )}
            </Box>
          )}

          {/* All mode: summary */}
          {mode === "all" && (
            <Alert severity="info" icon={false} sx={{ py: 0.75 }}>
              {patientsLoading ? (
                "Loading patient count..."
              ) : (
                <>
                  This will process <strong>all {allPatients.length.toLocaleString()} patients</strong>. Use{" "}
                  <em>New records only</em> below to avoid re-processing everything.
                </>
              )}
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* -- What to do ---------------------------------------------------- */}
      <Card variant="outlined">
        <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
            What should it do?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Choose what the pipeline runs for these patients.
          </Typography>

          <FormControl fullWidth size="small">
            <InputLabel id="action-label">Pipeline action</InputLabel>
            <Select
              labelId="action-label"
              label="Pipeline action"
              value={action}
              onChange={(e) => setAction(e.target.value as PipelineAction)}
              disabled={running}
            >
              {(Object.keys(ACTION_LABELS) as PipelineAction[]).map((key) => (
                <MenuItem key={key} value={key}>
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {ACTION_LABELS[key].label}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {ACTION_LABELS[key].hint}
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </CardContent>
      </Card>

      {/* -- Run controls --------------------------------------------------- */}
      <Card variant="outlined">
        <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            alignItems={{ xs: "flex-start", sm: "center" }}
            justifyContent="space-between"
            gap={1.5}
          >
            <FormControlLabel
              control={
                <Switch
                  checked={dryRun}
                  onChange={(_, v) => setDryRun(v)}
                  disabled={running}
                  size="small"
                />
              }
              label={
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
                    Test run
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Goes through all the steps but does not save anything
                  </Typography>
                </Box>
              }
            />

            {running ? (
              <Button variant="outlined" color="error" onClick={stopRun} sx={{ minWidth: 120 }}>
                Stop
              </Button>
            ) : (
              <Button
                variant="contained"
                startIcon={<PlayArrowIcon />}
                onClick={startRun}
                disabled={!canRun}
                sx={{ minWidth: 200 }}
              >
                {runLabel}
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* -- Progress + log ------------------------------------------------- */}
      {(running || log.length > 0) && (
        <Card variant="outlined">
          <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
            {running && (
              <Box sx={{ mb: 2 }}>
                <LinearProgress
                  variant={progress > 0 ? "determinate" : "indeterminate"}
                  value={progress}
                  aria-label="Pipeline progress"
                />
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                  {progress > 0 ? `${progress}% complete` : "Starting..."}
                </Typography>
              </Box>
            )}

            <Box
              role="log"
              aria-label="Pipeline log"
              sx={{
                maxHeight: 280,
                overflow: "auto",
                bgcolor: "action.hover",
                borderRadius: 1,
                p: 1.5,
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "0.8rem",
                lineHeight: 1.6,
              }}
            >
              {log.map((line, i) => (
                <Box
                  key={i}
                  sx={{ color: line.startsWith("Error") ? "error.main" : "text.primary" }}
                >
                  {line}
                </Box>
              ))}
              <div ref={logEndRef} />
            </Box>
          </CardContent>
        </Card>
      )}

      {/* -- Run history (this session) ------------------------------------- */}
      {runs.length > 0 && (
        <>
          <Divider />
          <Box>
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
              This session
            </Typography>
            <Stack gap={1}>
              {runs.map((r, i) => (
                <Stack
                  key={i}
                  direction="row"
                  alignItems="center"
                  flexWrap="wrap"
                  gap={1}
                  sx={{
                    p: 1.5,
                    border: 1,
                    borderColor: "divider",
                    borderRadius: 1.5,
                    bgcolor: "background.paper",
                  }}
                >
                  <Chip
                    label={r.status === "ok" ? "Done" : "Failed"}
                    size="small"
                    color={r.status === "ok" ? "success" : "error"}
                  />
                  <Typography variant="body2">
                    {r.patients.toLocaleString()}{" "}
                    {r.patients === 1 ? "patient" : "patients"}
                  </Typography>
                  <Chip
                    label={ACTION_LABELS[r.action]?.label ?? r.action}
                    size="small"
                    variant="outlined"
                  />
                  <Typography variant="body2" color="text.secondary">
                    {r.duration}s
                  </Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <Typography variant="caption" color="text.disabled">
                    {r.startedAt}
                  </Typography>
                </Stack>
              ))}
            </Stack>
          </Box>
        </>
      )}
    </Stack>
  );
}
