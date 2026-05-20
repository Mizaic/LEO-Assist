/**
 * Run Results Drawer -- polls a validation run and shows per-case F1 results.
 *
 * Polls /extraction-scenarios/runs/:run_id every 1500 ms while running.
 * On completion shows overall F1 / precision / recall vs threshold (pass/fail badge),
 * per-case table with missed and extra phrases, and an Atlas manual record callout.
 *
 * Atlas IDs that must be used when recording manually:
 *   VT-29880CC8   extraction scenario verification test
 *   VAL-87173594  phrase-level F1 validation test
 */
"use client";

import { useCallback, useEffect, useRef } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { getRunStatus } from "./api";
import type { CaseScore, ValidationRunStatus } from "./types";

interface Props {
  run: ValidationRunStatus | null;
  open: boolean;
  onClose: () => void;
  onRunUpdate: (run: ValidationRunStatus) => void;
}

const POLL_INTERVAL_MS = 1500;

function f1Pct(val?: number): string {
  if (val == null) return "-";
  return `${(val * 100).toFixed(1)}%`;
}

function PassBadge({ passed, f1 }: { passed: boolean; f1?: number }) {
  return (
    <Chip
      icon={passed ? <CheckCircleOutlineIcon /> : <ErrorOutlineIcon />}
      label={passed ? `Pass (${f1Pct(f1)})` : `Fail (${f1Pct(f1)})`}
      color={passed ? "success" : "error"}
      variant="outlined"
      sx={{ fontWeight: 600, fontSize: "0.9rem", py: 1.5 }}
      data-testid="pass-fail-badge"
    />
  );
}

function CaseResultsTable({ rows }: { rows: CaseScore[] }) {
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        overflowY: "auto",
        maxHeight: 360,
      }}
    >
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600 }}>Case ID</TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              F1
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              P
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              R
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 600 }}>
              Obs R
            </TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Pipeline stages</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Missed phrases</TableCell>
            <TableCell sx={{ fontWeight: 600 }}>Extra phrases</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow
              key={row.case_id}
              sx={{ bgcolor: row.f1 < 0.95 ? "error.50" : undefined }}
              data-testid={`case-result-${row.case_id}`}
            >
              <TableCell>
                <Typography variant="body2" sx={{ fontWeight: row.f1 < 0.95 ? 600 : 400 }}>
                  {row.case_id}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography
                  variant="body2"
                  color={row.f1 < 0.95 ? "error.main" : "success.main"}
                  sx={{ fontWeight: 600 }}
                >
                  {f1Pct(row.f1)}
                </Typography>
              </TableCell>
              <TableCell align="right">{f1Pct(row.precision)}</TableCell>
              <TableCell align="right">{f1Pct(row.recall)}</TableCell>
              <TableCell align="right">{f1Pct(row.observable_recall)}</TableCell>
              <TableCell>
                {row.stage_snapshots ? (
                  <Tooltip
                    title={Object.entries(row.stage_snapshots)
                      .map(([stage, snap]) => `${stage}: ${snap.entity_count}`)
                      .join(" | ")}
                  >
                    <Typography variant="caption" color="text.secondary" component="span">
                      {Object.entries(row.stage_snapshots)
                        .map(([stage, snap]) => `${stage}:${snap.entity_count}`)
                        .join(" ")}
                    </Typography>
                  </Tooltip>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    -
                  </Typography>
                )}
              </TableCell>
              <TableCell>
                <Typography variant="caption" color="text.secondary">
                  {row.missed_strings?.join(", ") || "-"}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="caption" color="text.secondary">
                  {row.extra_strings?.join(", ") || "-"}
                </Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function AtlasCallout({ runId }: { runId: string }) {
  return (
    <Alert
      severity="info"
      icon={<InfoOutlinedIcon fontSize="inherit" />}
      data-testid="atlas-callout"
      sx={{ mt: 2 }}
    >
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        Record this run in Atlas
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        To record this run automatically, run the following from Cursor or CI:
      </Typography>
      <Box
        component="pre"
        sx={{
          fontFamily: "monospace",
          fontSize: "0.75rem",
          bgcolor: "action.hover",
          borderRadius: 0.5,
          p: 1,
          overflowX: "auto",
          mb: 1,
        }}
      >
        {`python3 scripts/record_extraction_val_in_atlas.py`}
      </Box>
      <Typography variant="body2">
        This records against{" "}
        <Box component="code" sx={{ fontFamily: "monospace", fontWeight: 600 }}>
          VT-29880CC8
        </Box>{" "}
        and{" "}
        <Box component="code" sx={{ fontFamily: "monospace", fontWeight: 600 }}>
          VAL-87173594
        </Box>{" "}
        for run ID{" "}
        <Box component="code" sx={{ fontFamily: "monospace", fontSize: "0.7rem" }}>
          {runId}
        </Box>
        .
      </Typography>
    </Alert>
  );
}

export default function RunResultsDrawer({ run, open, onClose, onRunUpdate }: Props) {
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(
    (runId: string) => {
      getRunStatus(runId)
        .then((updated) => {
          onRunUpdate(updated);
          if (updated.status === "completed" || updated.status === "failed") {
            stopPolling();
          }
        })
        .catch(() => {
          // Best-effort: silently continue polling on transient errors.
        });
    },
    [onRunUpdate, stopPolling],
  );

  useEffect(() => {
    if (!open || !run) return;
    if (run.status === "queued" || run.status === "running") {
      stopPolling();
      pollRef.current = setInterval(() => poll(run.run_id), POLL_INTERVAL_MS);
    }
    return stopPolling;
  }, [open, run?.run_id, run?.status]);

  useEffect(() => {
    if (!open) stopPolling();
  }, [open, stopPolling]);

  const isRunning = run?.status === "queued" || run?.status === "running";
  const isComplete = run?.status === "completed";
  const isFailed = run?.status === "failed";

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", md: 800 }, p: 3 } }}
      data-testid="run-results-drawer"
    >
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Validation run
          </Typography>
          {run ? (
            <Typography variant="caption" color="text.secondary">
              Run ID: {run.run_id}
            </Typography>
          ) : null}
        </Box>
        <IconButton onClick={onClose} size="small" aria-label="Close run results">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>

      <Divider sx={{ mb: 2 }} />

      {!run ? (
        <Typography variant="body2" color="text.secondary">
          No run data yet.
        </Typography>
      ) : isRunning ? (
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <CircularProgress size={20} />
            <Typography variant="body2">
              {run.status === "queued" ? "Queued..." : "Running validation..."}
            </Typography>
          </Stack>
          <Box>
            <LinearProgress
              variant="determinate"
              value={run.progress ?? 0}
              sx={{ height: 8, borderRadius: 4 }}
              aria-label="Validation run progress"
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              {run.progress ?? 0}% complete
            </Typography>
          </Box>
        </Stack>
      ) : isFailed ? (
        <Alert severity="error">
          Run failed. {(run as ValidationRunStatus & { error?: string }).error ?? ""}
        </Alert>
      ) : isComplete ? (
        <Stack spacing={2}>
          {/* Overall summary */}
          <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap">
            <PassBadge passed={run.passed ?? false} f1={run.overall_f1} />
            <Tooltip
              title={`Threshold is ${f1Pct(run.pass_threshold)} overall phrase F1`}
              arrow
            >
              <Typography variant="body2" color="text.secondary">
                Threshold: {f1Pct(run.pass_threshold)}
              </Typography>
            </Tooltip>
          </Stack>

          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: 1,
            }}
          >
            {[
              { label: "Precision", value: run.overall_precision },
              { label: "Recall", value: run.overall_recall },
              { label: "F1", value: run.overall_f1 },
            ].map(({ label, value }) => (
              <Box
                key={label}
                sx={{
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                  p: 1.5,
                  textAlign: "center",
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  {label}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {f1Pct(value)}
                </Typography>
              </Box>
            ))}
          </Box>

          {/* Per-case breakdown */}
          {run.per_case_results && run.per_case_results.length > 0 ? (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                Per-case results ({run.per_case_results.length} cases)
              </Typography>
              <CaseResultsTable rows={run.per_case_results} />
            </Box>
          ) : null}

          <AtlasCallout runId={run.run_id} />
        </Stack>
      ) : null}
    </Drawer>
  );
}
