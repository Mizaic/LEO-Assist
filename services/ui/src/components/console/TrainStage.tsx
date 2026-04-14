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
          <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
            Training curve
          </Typography>
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
