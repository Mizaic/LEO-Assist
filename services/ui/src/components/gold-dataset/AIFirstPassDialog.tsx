/**
 * AIFirstPassDialog -- DI-LEO-AI-209 / DO-LEO-AI-206.
 *
 * Reviewer-facing trigger for the AI first-pass workflow over
 * non-completed TrainingCandidate rows.
 *
 * Two-step contract:
 *   1. POST /api/training/candidates/ai-first-pass/jobs with the
 *      AIFirstPassParams payload; receive a run_id immediately.
 *   2. Subscribe via EventSource to /api/training/candidates/
 *      ai-first-pass/jobs/{run_id}/events; render a live by_verdict
 *      and by_action tally as candidate.processed events arrive,
 *      then a final summary panel on job.summary.
 *
 * Safety rails (mirrored from R-LEO-AI-197):
 *   - Dialog cannot be dismissed while a job is running.
 *   - Dry-run defaults to true so first invocation is read-only.
 *   - Completed gold candidates are excluded server-side (DI-208) AND
 *     re-checked TOCTOU before any write/delete; this dialog only
 *     surfaces the per-candidate verdict, never decides it.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

const AI_FIRST_PASS_STATUSES = ["pending", "processing", "failed"] as const;

type AIFirstPassStatus = (typeof AI_FIRST_PASS_STATUSES)[number];
type AIFirstPassVerdict = "pre_done" | "delete" | "review";
type AIFirstPassAction =
  | "upserted_pre_done"
  | "deleted"
  | "skipped_review"
  | "skipped_completed"
  | "not_found"
  | "error";

interface CandidateProcessedEvent {
  type: "candidate.processed";
  candidate_id: string;
  verdict: AIFirstPassVerdict;
  action: AIFirstPassAction;
  accepted: number;
  rejected: number;
  reason?: string;
}

interface JobSummaryEvent {
  type: "job.summary";
  run_id: string;
  candidate_count: number;
  by_verdict: Record<AIFirstPassVerdict, number>;
  by_action: Record<AIFirstPassAction, number>;
  errors: number;
}

interface QueueResponse {
  run_id: string;
  status: string;
  params: Record<string, unknown>;
}

interface AIFirstPassDialogProps {
  open: boolean;
  onClose: () => void;
  onJobComplete?: (summary: JobSummaryEvent) => void;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    let message = `${res.status}`;
    try {
      const payload = (await res.json()) as { detail?: unknown; message?: string };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail.trim();
      } else if (typeof payload.message === "string" && payload.message.trim()) {
        message = payload.message.trim();
      }
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

function clamp01(value: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function VerdictChip({ verdict }: { verdict: AIFirstPassVerdict }) {
  const colorByVerdict: Record<AIFirstPassVerdict, "success" | "error" | "warning"> = {
    pre_done: "success",
    delete: "error",
    review: "warning",
  };
  return (
    <Chip
      size="small"
      label={verdict.replace("_", " ")}
      color={colorByVerdict[verdict]}
      sx={{ textTransform: "capitalize", fontWeight: 600, minWidth: 72 }}
    />
  );
}

const ZERO_VERDICTS: Record<AIFirstPassVerdict, number> = {
  pre_done: 0,
  delete: 0,
  review: 0,
};

const ZERO_ACTIONS: Record<AIFirstPassAction, number> = {
  upserted_pre_done: 0,
  deleted: 0,
  skipped_review: 0,
  skipped_completed: 0,
  not_found: 0,
  error: 0,
};

export default function AIFirstPassDialog({
  open,
  onClose,
  onJobComplete,
}: AIFirstPassDialogProps) {
  const [minSurfaceMatch, setMinSurfaceMatch] = useState<number>(0.7);
  const [semanticVectorFloor, setSemanticVectorFloor] = useState<number>(0.92);
  const [semanticMinSurface, setSemanticMinSurface] = useState<number>(0.66);
  const [statuses, setStatuses] = useState<AIFirstPassStatus[]>([
    "pending",
    "processing",
    "failed",
  ]);
  const [limit, setLimit] = useState<number>(200);
  const [maxWorkers, setMaxWorkers] = useState<number>(4);
  const [fewShotK, setFewShotK] = useState<number>(5);
  const [coderMaxRetries, setCoderMaxRetries] = useState<number>(2);
  const [dryRun, setDryRun] = useState<boolean>(true);

  const [runId, setRunId] = useState<string | null>(null);
  const [running, setRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [processedCount, setProcessedCount] = useState<number>(0);
  const [byVerdict, setByVerdict] =
    useState<Record<AIFirstPassVerdict, number>>(ZERO_VERDICTS);
  const [byAction, setByAction] =
    useState<Record<AIFirstPassAction, number>>(ZERO_ACTIONS);
  const [recent, setRecent] = useState<CandidateProcessedEvent[]>([]);
  const [summary, setSummary] = useState<JobSummaryEvent | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const finishedRef = useRef<boolean>(false);

  useEffect(() => () => esRef.current?.close(), []);

  const reset = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    finishedRef.current = false;
    setRunId(null);
    setRunning(false);
    setError(null);
    setProcessedCount(0);
    setByVerdict(ZERO_VERDICTS);
    setByAction(ZERO_ACTIONS);
    setRecent([]);
    setSummary(null);
  }, []);

  function handleClose() {
    if (running) return;
    reset();
    onClose();
  }

  const subscribe = useCallback(
    (newRunId: string) => {
      const origin =
        typeof window !== "undefined" ? window.location.origin : "";
      const source = new EventSource(
        `${origin}/api/training/candidates/ai-first-pass/jobs/${encodeURIComponent(
          newRunId,
        )}/events`,
      );
      esRef.current = source;

      source.addEventListener("candidate.processed", (e) => {
        let parsed: CandidateProcessedEvent | null = null;
        try {
          parsed = JSON.parse((e as MessageEvent).data) as CandidateProcessedEvent;
        } catch {
          return;
        }
        if (!parsed) return;
        setProcessedCount((n) => n + 1);
        setByVerdict((bv) => ({
          ...bv,
          [parsed!.verdict]: (bv[parsed!.verdict] ?? 0) + 1,
        }));
        setByAction((ba) => ({
          ...ba,
          [parsed!.action]: (ba[parsed!.action] ?? 0) + 1,
        }));
        setRecent((rs) => {
          const next = [parsed!, ...rs];
          return next.slice(0, 50);
        });
      });

      source.addEventListener("job.summary", (e) => {
        finishedRef.current = true;
        let parsed: JobSummaryEvent | null = null;
        try {
          parsed = JSON.parse((e as MessageEvent).data) as JobSummaryEvent;
        } catch {
          parsed = null;
        }
        if (parsed) {
          setSummary(parsed);
          if (onJobComplete) onJobComplete(parsed);
        }
        setRunning(false);
        source.close();
        esRef.current = null;
      });

      source.onerror = () => {
        if (finishedRef.current) return;
        setRunning(false);
        setError("SSE connection dropped");
        source.close();
        esRef.current = null;
      };
    },
    [onJobComplete],
  );

  async function startJob() {
    if (running) return;
    setRunning(true);
    setError(null);
    setProcessedCount(0);
    setByVerdict(ZERO_VERDICTS);
    setByAction(ZERO_ACTIONS);
    setRecent([]);
    setSummary(null);
    finishedRef.current = false;

    const payload = {
      min_surface_match: clamp01(minSurfaceMatch, 0.7),
      semantic_vector_floor: clamp01(semanticVectorFloor, 0.92),
      semantic_min_surface: clamp01(semanticMinSurface, 0.66),
      statuses,
      limit: Math.max(1, Math.min(2000, Math.round(limit || 200))),
      max_workers: Math.max(1, Math.min(8, Math.round(maxWorkers || 4))),
      few_shot_k: Math.max(0, Math.min(20, Math.round(fewShotK || 5))),
      coder_max_retries: Math.max(0, Math.min(4, Math.round(coderMaxRetries || 2))),
      dry_run: dryRun,
    };

    try {
      const res = await jsonFetch<QueueResponse>(
        "/api/training/candidates/ai-first-pass/jobs",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      setRunId(res.run_id);
      subscribe(res.run_id);
    } catch (e) {
      setRunning(false);
      setError(e instanceof Error ? e.message : "Failed to queue job");
    }
  }

  function toggleStatus(status: AIFirstPassStatus) {
    setStatuses((prev) =>
      prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status],
    );
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
      <DialogTitle>AI first-pass over the candidate to-do list</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Stack spacing={1.25}>
            <Typography variant="body2" color="text.secondary">
              This tool uses AI to do a first pass on the sentences in your
              to-do list. It learns from sentences you have already finished,
              then tries to label and code each new one. If the first try
              does not match a clinical code, it tries again with different
              words.
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Every sentence ends up in one of three groups:
            </Typography>
            <Stack component="ul" spacing={0.5} sx={{ pl: 3, my: 0 }}>
              <li>
                <Typography variant="body2" color="text.secondary">
                  <strong>Pre-done</strong> -- the AI found labels and
                  codes. The sentence stays in your list with an
                  &quot;AI suggested&quot; tag so you can check it.
                </Typography>
              </li>
              <li>
                <Typography variant="body2" color="text.secondary">
                  <strong>Delete</strong> -- the AI could not find anything
                  useful. The sentence is removed from your list.
                </Typography>
              </li>
              <li>
                <Typography variant="body2" color="text.secondary">
                  <strong>Review</strong> -- the AI was not sure. The
                  sentence stays in your list, unchanged, for you to look at.
                </Typography>
              </li>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Sentences you have already finished are never changed.
            </Typography>
          </Stack>

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Confidence floors
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="min_surface_match"
                type="number"
                size="small"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={minSurfaceMatch}
                disabled={running}
                onChange={(e) => setMinSurfaceMatch(parseFloat(e.target.value))}
                helperText="default 0.7"
              />
              <TextField
                label="semantic_vector_floor"
                type="number"
                size="small"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={semanticVectorFloor}
                disabled={running}
                onChange={(e) =>
                  setSemanticVectorFloor(parseFloat(e.target.value))
                }
                helperText="default 0.92"
              />
              <TextField
                label="semantic_min_surface"
                type="number"
                size="small"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={semanticMinSurface}
                disabled={running}
                onChange={(e) =>
                  setSemanticMinSurface(parseFloat(e.target.value))
                }
                helperText="default 0.66"
              />
            </Stack>
          </Box>

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Job parameters
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="limit"
                type="number"
                size="small"
                inputProps={{ step: 50, min: 1, max: 2000 }}
                value={limit}
                disabled={running}
                onChange={(e) => setLimit(parseInt(e.target.value, 10))}
                helperText="max 2000"
              />
              <TextField
                label="max_workers"
                type="number"
                size="small"
                inputProps={{ step: 1, min: 1, max: 8 }}
                value={maxWorkers}
                disabled={running}
                onChange={(e) => setMaxWorkers(parseInt(e.target.value, 10))}
                helperText="1-8"
              />
              <TextField
                label="few_shot_k"
                type="number"
                size="small"
                inputProps={{ step: 1, min: 0, max: 20 }}
                value={fewShotK}
                disabled={running}
                onChange={(e) => setFewShotK(parseInt(e.target.value, 10))}
                helperText="gold exemplars"
              />
              <TextField
                label="coder_max_retries"
                type="number"
                size="small"
                inputProps={{ step: 1, min: 0, max: 4 }}
                value={coderMaxRetries}
                disabled={running}
                onChange={(e) =>
                  setCoderMaxRetries(parseInt(e.target.value, 10))
                }
                helperText="Haiku alt-query retries"
              />
            </Stack>
          </Box>

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Status scope
            </Typography>
            <Stack direction="row" spacing={1}>
              {AI_FIRST_PASS_STATUSES.map((s) => (
                <FormControlLabel
                  key={s}
                  control={
                    <Checkbox
                      size="small"
                      checked={statuses.includes(s)}
                      disabled={running}
                      onChange={() => toggleStatus(s)}
                    />
                  }
                  label={s}
                />
              ))}
            </Stack>
            <Typography variant="caption" color="text.secondary">
              Sentences you have already finished (status
              &apos;completed&apos;) are protected. The AI never changes
              them.
            </Typography>
          </Box>

          <FormControlLabel
            control={
              <Checkbox
                checked={dryRun}
                disabled={running}
                onChange={(e) => setDryRun(e.target.checked)}
              />
            }
            label="Dry run (assess only, do not write or delete)"
          />

          {error && <Alert severity="error">{error}</Alert>}

          <Box>
            <Button
              variant="contained"
              onClick={startJob}
              disabled={running || statuses.length === 0}
              data-testid="ai-first-pass-start"
            >
              {running ? (
                <Stack direction="row" spacing={1} alignItems="center">
                  <CircularProgress size={16} />
                  <span>Running...</span>
                </Stack>
              ) : (
                "Start AI first-pass"
              )}
            </Button>
            {runId && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ ml: 2 }}
              >
                run_id: {runId}
              </Typography>
            )}
          </Box>

          {(running || processedCount > 0) && (
            <Box>
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                sx={{ mb: 1 }}
              >
                <Typography variant="subtitle2">
                  Processed {processedCount} candidates
                </Typography>
                {running && <LinearProgress sx={{ flex: 1 }} />}
              </Stack>
              <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
                <Chip color="success" label={`Pre-done: ${byVerdict.pre_done}`} />
                <Chip color="error" label={`Delete: ${byVerdict.delete}`} />
                <Chip color="warning" label={`Review: ${byVerdict.review}`} />
              </Stack>
              <TableContainer sx={{ maxHeight: 320 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Verdict</TableCell>
                      <TableCell>Candidate</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell align="right">Accepted</TableCell>
                      <TableCell align="right">Rejected</TableCell>
                      <TableCell>Reason</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {recent.map((c) => (
                      <TableRow key={`${c.candidate_id}-${c.action}`}>
                        <TableCell>
                          <VerdictChip verdict={c.verdict} />
                        </TableCell>
                        <TableCell sx={{ maxWidth: 280 }}>
                          <Typography variant="caption">
                            {c.candidate_id}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption">{c.action}</Typography>
                        </TableCell>
                        <TableCell align="right">{c.accepted}</TableCell>
                        <TableCell align="right">{c.rejected}</TableCell>
                        <TableCell sx={{ maxWidth: 200 }}>
                          <Typography variant="caption" color="text.secondary">
                            {c.reason ?? "-"}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {summary && (
            <Alert severity="success" data-testid="ai-first-pass-summary">
              <Typography variant="subtitle2" gutterBottom>
                Job complete -- {summary.candidate_count} candidates processed
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                <Chip
                  size="small"
                  color="success"
                  label={`Upserted pre-done: ${summary.by_action.upserted_pre_done}`}
                />
                <Chip
                  size="small"
                  color="error"
                  label={`Deleted: ${summary.by_action.deleted}`}
                />
                <Chip
                  size="small"
                  color="warning"
                  label={`Skipped review: ${summary.by_action.skipped_review}`}
                />
                <Chip
                  size="small"
                  label={`Skipped completed: ${summary.by_action.skipped_completed}`}
                />
                <Chip
                  size="small"
                  label={`Not found: ${summary.by_action.not_found}`}
                />
                <Chip size="small" label={`Errors: ${summary.errors}`} />
              </Stack>
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={running}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
