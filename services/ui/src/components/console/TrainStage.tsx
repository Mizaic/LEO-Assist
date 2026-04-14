"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import TableBody from "@mui/material/TableBody";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from "recharts";
import { PhaseProgress } from "@/components/ui/PhaseProgress";
import { TrainingJob } from "./useConsoleState";
import { FONT_SIZES } from "@/theme/tokens";

// -- Epoch line parser -------------------------------------------------------

interface EpochRow {
  step: number;
  loss_ner: number;
  ents_f: number;
  ents_p: number;
  ents_r: number;
}

const EPOCH_RE = /^\s*\d+\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/;

function parseEpochLog(lines: string[]): EpochRow[] {
  return lines.reduce<EpochRow[]>((acc, line) => {
    const m = EPOCH_RE.exec(line);
    if (!m) return acc;
    acc.push({
      step: parseInt(m[1], 10),
      loss_ner: parseFloat(m[3]),
      ents_f: parseFloat(m[4]),
      ents_p: parseFloat(m[5]),
      ents_r: parseFloat(m[6]),
    });
    return acc;
  }, []);
}

// -- Components --------------------------------------------------------------

interface TrainStageProps {
  jobs: TrainingJob[];
  runningJob: TrainingJob | null;
  latestJob: TrainingJob | null;
  onTrain: () => void;
  training: boolean;
}

export function TrainStage({ jobs, runningJob, latestJob, onTrain, training }: TrainStageProps) {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const displayJob =
    selectedJobId ? jobs.find((j) => j.job_id === selectedJobId) ?? latestJob : runningJob ?? latestJob;

  const epochData = parseEpochLog(displayJob?.log_lines ?? []);

  return (
    <Box sx={{ pt: 2, display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Action row */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        <Button
          variant="contained"
          onClick={onTrain}
          disabled={training || !!runningJob}
          startIcon={training ? <CircularProgress size={14} color="inherit" /> : undefined}
          sx={{ textTransform: "none" }}
        >
          {runningJob ? "Training in progress" : "Train now"}
        </Button>
        {displayJob && (
          <Chip
            size="small"
            label={displayJob.status}
            color={
              displayJob.status === "done"
                ? "success"
                : displayJob.status === "failed"
                ? "error"
                : "default"
            }
          />
        )}
      </Box>

      {/* Phase progress */}
      {runningJob && (
        <PhaseProgress
          phase={runningJob.phase ?? ""}
          elapsed={runningJob.elapsed_s}
          liveF1={runningJob.f1}
        />
      )}

      {/* Error alert */}
      {displayJob?.status === "failed" && displayJob.error && (
        <Alert severity="error" sx={{ fontSize: FONT_SIZES.body }}>
          {displayJob.error}
        </Alert>
      )}

      {/* Epoch training chart */}
      {epochData.length > 1 && (
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 1 }}>
            <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle }}>
              Training curve
            </Typography>
            <TrainingCurveInfoButton />
          </Box>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={epochData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.4} />
              <XAxis dataKey="step" tick={{ fontSize: 11 }} label={{ value: "step", position: "insideBottom", offset: -2, fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <RTooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="loss_ner" stroke="#e65100" dot={false} strokeWidth={1.5} name="Loss NER" />
              <Line type="monotone" dataKey="ents_f" stroke="#1565c0" dot={false} strokeWidth={2} name="F1" />
              <Line type="monotone" dataKey="ents_p" stroke="#2e7d32" dot={false} strokeWidth={1.5} name="Precision" />
              <Line type="monotone" dataKey="ents_r" stroke="#7b1fa2" dot={false} strokeWidth={1.5} name="Recall" />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      )}

      {/* Per-entity F1 */}
      {displayJob?.per_label_f1 && Object.keys(displayJob.per_label_f1).length > 0 && (
        <PerLabelChart perLabel={displayJob.per_label_f1} />
      )}

      {/* Job history */}
      {jobs.length > 0 && (
        <JobHistoryTable jobs={jobs} selectedJobId={selectedJobId ?? displayJob?.job_id ?? null} onSelect={setSelectedJobId} />
      )}
    </Box>
  );
}

// -- Training curve info button + dialog -------------------------------------

function TrainingCurveInfoButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        size="small"
        variant="text"
        startIcon={<InfoOutlinedIcon sx={{ fontSize: 14 }} />}
        onClick={() => setOpen(true)}
        sx={{
          fontSize: 11,
          textTransform: "none",
          color: "primary.main",
          py: 0,
          px: 0.75,
          minWidth: 0,
          lineHeight: 1.4,
        }}
      >
        What do these lines mean?
      </Button>
      <TrainingCurveInfoDialog open={open} onClose={() => setOpen(false)} />
    </>
  );
}

const GOOD_DATA = Array.from({ length: 20 }, (_, i) => ({
  step: i * 100,
  loss: Math.max(0.05, 2.8 * Math.exp(-i * 0.28)),
  f1: Math.min(0.95, 0.05 + 0.9 * (1 - Math.exp(-i * 0.25))),
  precision: Math.min(0.97, 0.05 + 0.92 * (1 - Math.exp(-i * 0.22))),
  recall: Math.min(0.93, 0.04 + 0.89 * (1 - Math.exp(-i * 0.23))),
}));

const BAD_DATA = Array.from({ length: 20 }, (_, i) => ({
  step: i * 100,
  loss: i < 8 ? 2.8 * Math.exp(-i * 0.3) : 0.3 + 0.4 * Math.sin(i * 0.9),
  f1: i < 8 ? 0.05 + 0.5 * (1 - Math.exp(-i * 0.3)) : 0.35 + 0.2 * Math.sin(i * 0.8),
  precision: i < 8 ? 0.1 + 0.4 * (1 - Math.exp(-i * 0.25)) : 0.3 + 0.25 * Math.sin(i),
  recall: i < 8 ? 0.05 + 0.3 * (1 - Math.exp(-i * 0.2)) : 0.2 + 0.3 * Math.sin(i * 0.7),
}));

const METRICS = [
  { key: "loss", color: "#e65100", label: "Loss NER" },
  { key: "f1", color: "#1565c0", label: "F1" },
  { key: "precision", color: "#2e7d32", label: "Precision" },
  { key: "recall", color: "#7b1fa2", label: "Recall" },
];

const METRIC_DESCRIPTIONS: Record<string, { what: string; good: string; bad: string }> = {
  "Loss NER": {
    what: "How wrong the model is during training. Measured on each batch of text.",
    good: "Falls steadily and levels off near zero. Smooth descent with no big spikes.",
    bad: "Stops falling early, bounces up and down, or never gets below ~0.3.",
  },
  F1: {
    what: "Overall coding accuracy. Balances finding codes (recall) and avoiding wrong ones (precision).",
    good: "Climbs steadily toward 1.0 and plateaus near the top of the chart.",
    bad: "Stalls below 0.5, or rises then drops sharply (the model has overfit).",
  },
  Precision: {
    what: "Of every code LEO suggests, how many are actually correct.",
    good: "Stays above 0.8 and tracks closely with F1.",
    bad: "Diverges far below F1 -- the model is guessing too many codes.",
  },
  Recall: {
    what: "Of all the codes that should be in the record, how many did LEO find.",
    good: "Stays close to Precision. Both lines rise together toward F1.",
    bad: "Drops well below Precision -- the model is missing codes it should find.",
  },
};

function ExampleChart({
  data,
  title,
  borderColor,
}: {
  data: typeof GOOD_DATA;
  title: string;
  borderColor: string;
}) {
  return (
    <Box
      sx={{
        flex: 1,
        border: `2px solid ${borderColor}`,
        borderRadius: 1,
        p: 1,
        minWidth: 0,
      }}
    >
      <Typography sx={{ fontSize: 11, fontWeight: 600, mb: 0.5, color: borderColor }}>
        {title}
      </Typography>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="step" tick={{ fontSize: 9 }} />
          <YAxis tick={{ fontSize: 9 }} domain={[0, 3]} />
          {METRICS.map((m) => (
            <Line
              key={m.key}
              type="monotone"
              dataKey={m.key}
              stroke={m.color}
              dot={false}
              strokeWidth={1.5}
              name={m.label}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Box>
  );
}

function TrainingCurveInfoDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: FONT_SIZES.subtitle, fontWeight: 700 }}>
        How to read the training curve
      </DialogTitle>
      <DialogContent dividers sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <ExampleChart data={GOOD_DATA} title="Healthy training" borderColor="#2e7d32" />
          <ExampleChart data={BAD_DATA} title="Problem training" borderColor="#c62828" />
        </Box>

        <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary" }}>
          A healthy run has a steadily falling loss and rising F1 and Precision lines that
          level off near the top. Problems to watch for are shown in the right chart above.
        </Typography>

        {Object.entries(METRIC_DESCRIPTIONS).map(([label, info]) => {
          const metric = METRICS.find((m) => m.label === label);
          return (
            <Box key={label}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
                <Box
                  sx={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    bgcolor: metric?.color ?? "#999",
                    flexShrink: 0,
                  }}
                />
                <Typography sx={{ fontWeight: 700, fontSize: FONT_SIZES.body }}>
                  {label}
                </Typography>
              </Box>
              <Typography sx={{ fontSize: FONT_SIZES.body, mb: 0.25 }}>{info.what}</Typography>
              <Typography sx={{ fontSize: 12, color: "success.dark" }}>
                <strong>Healthy:</strong> {info.good}
              </Typography>
              <Typography sx={{ fontSize: 12, color: "error.dark" }}>
                <strong>Problem:</strong> {info.bad}
              </Typography>
            </Box>
          );
        })}
      </DialogContent>
      <DialogActions>
        <Button variant="text" onClick={onClose}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// -- Per-label F1 chart ------------------------------------------------------

function PerLabelChart({ perLabel }: { perLabel: Record<string, { f1: number }> }) {
  const data = Object.entries(perLabel)
    .map(([label, s]) => ({ label, f1: s.f1 }))
    .sort((a, b) => b.f1 - a.f1);

  return (
    <Box>
      <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
        Per-entity F1
      </Typography>
      <ResponsiveContainer width="100%" height={Math.max(120, data.length * 28)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 8, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.4} />
          <XAxis
            type="number"
            domain={[0, 1]}
            tick={{ fontSize: 11 }}
            tickFormatter={(v) =>
              `${((typeof v === "number" ? v : 0) * 100).toFixed(0)}%`
            }
          />
          <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={120} />
          <RTooltip
            formatter={(v) =>
              `${((typeof v === "number" ? v : 0) * 100).toFixed(1)}%`
            }
          />
          <Bar dataKey="f1" maxBarSize={18} radius={[0, 3, 3, 0]}>
            {data.map((d) => (
              <Cell
                key={d.label}
                fill={d.f1 >= 0.8 ? "#2e7d32" : d.f1 >= 0.6 ? "#ed6c02" : "#d32f2f"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}

// -- Job history table -------------------------------------------------------

function JobHistoryTable({
  jobs,
  selectedJobId,
  onSelect,
}: {
  jobs: TrainingJob[];
  selectedJobId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Box>
      <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
        Job history
      </Typography>
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontSize: FONT_SIZES.label }}>Version</TableCell>
              <TableCell sx={{ fontSize: FONT_SIZES.label }}>Status</TableCell>
              <TableCell sx={{ fontSize: FONT_SIZES.label }}>F1</TableCell>
              <TableCell sx={{ fontSize: FONT_SIZES.label }}>P</TableCell>
              <TableCell sx={{ fontSize: FONT_SIZES.label }}>R</TableCell>
              <TableCell sx={{ fontSize: FONT_SIZES.label }}>Elapsed</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {jobs.slice(0, 10).map((j) => (
              <TableRow
                key={j.job_id}
                hover
                selected={j.job_id === selectedJobId}
                onClick={() => onSelect(j.job_id)}
                sx={{ cursor: "pointer" }}
              >
                <TableCell sx={{ fontSize: FONT_SIZES.label }}>
                  {j.model_version ?? j.job_id.slice(0, 8)}
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={j.status}
                    sx={{ fontSize: FONT_SIZES.label, height: 18 }}
                    color={j.status === "done" ? "success" : j.status === "failed" ? "error" : "default"}
                  />
                </TableCell>
                <TableCell sx={{ fontSize: FONT_SIZES.label }}>
                  {j.f1 != null ? `${(j.f1 * 100).toFixed(1)}%` : "—"}
                </TableCell>
                <TableCell sx={{ fontSize: FONT_SIZES.label }}>
                  {j.precision != null ? `${(j.precision * 100).toFixed(1)}%` : "—"}
                </TableCell>
                <TableCell sx={{ fontSize: FONT_SIZES.label }}>
                  {j.recall != null ? `${(j.recall * 100).toFixed(1)}%` : "—"}
                </TableCell>
                <TableCell sx={{ fontSize: FONT_SIZES.label }}>
                  {j.elapsed_s != null ? `${Math.round(j.elapsed_s)}s` : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    </Box>
  );
}
