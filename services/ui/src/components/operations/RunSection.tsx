"use client";

import { useCallback, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import FormControlLabel from "@mui/material/FormControlLabel";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

// -- Types -------------------------------------------------------------------

interface RunRecord {
  startedAt: string;
  duration: number;
  patients: number;
  status: "ok" | "error";
}

// -- Component ---------------------------------------------------------------

export default function RunSection() {
  const [patientIds, setPatientIds] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

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

  const startRun = useCallback(async () => {
    const ids = patientIds
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    if (ids.length === 0) {
      setError("Enter at least one patient ID.");
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
        body: JSON.stringify({
          patient_ids: ids,
          action: "full_pipeline",
          preview: dryRun,
        }),
        signal: abort.signal,
      });
      if (!start.ok) {
        throw new Error(`Server returned ${start.status}`);
      }
      const startPayload = (await start.json()) as { run_id?: string };
      if (!startPayload.run_id) {
        throw new Error("Run ID missing from start response.");
      }
      appendLog(`Queued run ${startPayload.run_id.slice(0, 8)}. Waiting for worker pickup...`);

      const res = await fetch(
        `/api/pipeline/progress/${encodeURIComponent(startPayload.run_id)}`,
        {
          credentials: "include",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            Accept: "text/event-stream",
          },
          signal: abort.signal,
        }
      );
      if (!res.ok || !res.body) {
        throw new Error(`Server returned ${res.status}`);
      }

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
            if (evt.type === "run_completed" || evt.type === "pipeline_done" || evt.type === "extraction_done") {
              setProgress(100);
            }
            if (evt.message) appendLog(evt.message);
            if (evt.type === "pipeline_error") {
              appendLog(`Error: ${evt.message}`);
            }
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
          status: "ok",
        },
        ...prev,
      ]);
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        const msg =
          err instanceof Error ? err.message : "Something went wrong.";
        setError(msg);
        appendLog(`Error: ${msg}`);
        setRuns((prev) => [
          {
            startedAt: new Date(started).toLocaleTimeString(),
            duration: Math.round((Date.now() - started) / 1000),
            patients: ids.length,
            status: "error",
          },
          ...prev,
        ]);
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }, [patientIds, dryRun, appendLog]);

  const stopRun = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
    appendLog("Stopped by user.");
  }, [appendLog]);

  return (
    <Stack gap={2.5}>
      {error && (
        <Alert severity="error" onClose={() => setError("")}>
          {error}
        </Alert>
      )}

      {/* Input card */}
      <Card>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 0.5, fontWeight: 600 }}>
            Run the pipeline
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Enter patient IDs (one per line or separated by commas). The system
            will process their records and create review items.
          </Typography>

          <TextField
            multiline
            minRows={3}
            maxRows={8}
            fullWidth
            placeholder={"P001\nP002\nP003"}
            value={patientIds}
            onChange={(e) => setPatientIds(e.target.value)}
            disabled={running}
            aria-label="Patient IDs, one per line"
            sx={{ mb: 2 }}
          />

          <Stack direction="row" alignItems="center" gap={2}>
            <FormControlLabel
              control={
                <Switch
                  checked={dryRun}
                  onChange={(_, v) => setDryRun(v)}
                  disabled={running}
                  size="small"
                />
              }
              label="Dry run (do not save results)"
            />

            <Box sx={{ flexGrow: 1 }} />

            {running ? (
              <Button variant="outlined" color="error" onClick={stopRun}>
                Stop
              </Button>
            ) : (
              <Button
                variant="contained"
                startIcon={<PlayArrowIcon />}
                onClick={startRun}
                disabled={patientIds.trim().length === 0}
              >
                Run pipeline
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Progress + log */}
      {(running || log.length > 0) && (
        <Card>
          <CardContent sx={{ p: 3 }}>
            {running && (
              <Box sx={{ mb: 2 }}>
                <LinearProgress
                  variant={progress > 0 ? "determinate" : "indeterminate"}
                  value={progress}
                  aria-label="Pipeline progress"
                />
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mt: 0.5, display: "block" }}
                >
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
                bgcolor: "#F1F5F9",
                borderRadius: 1,
                p: 1.5,
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: "0.8rem",
                lineHeight: 1.6,
              }}
            >
              {log.map((line, i) => (
                <Box key={i} sx={{ color: line.startsWith("Error") ? "error.main" : "text.primary" }}>
                  {line}
                </Box>
              ))}
              <div ref={logEndRef} />
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Run history (this session) */}
      {runs.length > 0 && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            This session
          </Typography>
          <Stack gap={1}>
            {runs.map((r, i) => (
              <Stack
                key={i}
                direction="row"
                alignItems="center"
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
                  {r.patients} {r.patients === 1 ? "patient" : "patients"}
                </Typography>
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
      )}
    </Stack>
  );
}
