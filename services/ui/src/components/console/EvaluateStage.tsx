"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import Chip from "@mui/material/Chip";
import LockIcon from "@mui/icons-material/Lock";
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer,
} from "recharts";
import { TrainingJob } from "./useConsoleState";
import { FONT_SIZES } from "@/theme/tokens";

interface EvaluateStageProps {
  jobs: TrainingJob[];
  latestJob: TrainingJob | null;
  promotedVersion?: string | null;
  onPromote?: (version: string, notes: string) => Promise<void>;
}

export function EvaluateStage({ jobs, latestJob, promotedVersion, onPromote }: EvaluateStageProps) {
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [promoteNotes, setPromoteNotes] = useState("");
  const [promoting, setPromoting] = useState(false);

  const doneJob = latestJob?.status === "done" ? latestJob : null;
  const canPromote = !!doneJob?.passed_gates && !!doneJob?.model_version;

  const handlePromote = async () => {
    if (!doneJob?.model_version || !onPromote) return;
    setPromoting(true);
    try {
      await onPromote(doneJob.model_version, promoteNotes);
      setPromoteOpen(false);
      setPromoteNotes("");
    } finally {
      setPromoting(false);
    }
  };

  return (
    <Box sx={{ pt: 2, display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Aggregate scores */}
      {doneJob && (
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
          <ScoreCard label="Precision" value={doneJob.precision} pass={(doneJob.precision ?? 0) >= 0.8} />
          <ScoreCard label="Recall" value={doneJob.recall} pass={(doneJob.recall ?? 0) >= 0.75} />
          <ScoreCard label="F1" value={doneJob.f1} pass={(doneJob.f1 ?? 0) >= 0.77} />
          {doneJob.golden_f1 != null && (
            <ScoreCard
              label="Golden F1"
              value={doneJob.golden_f1}
              pass={doneJob.golden_passed ?? false}
              locked
            />
          )}
        </Box>
      )}

      {/* Per-entity F1 */}
      {doneJob?.per_label_f1 && Object.keys(doneJob.per_label_f1).length > 0 && (
        <PerLabelChart perLabel={doneJob.per_label_f1} />
      )}

      {/* Regression history */}
      {jobs.length > 1 && <RegressionTable jobs={jobs} />}

      {/* Promote button */}
      <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
        <Button
          variant="contained"
          color="success"
          disabled={!canPromote}
          onClick={() => setPromoteOpen(true)}
          sx={{ textTransform: "none" }}
        >
          Promote to live
        </Button>
        {promotedVersion && (
          <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary" }}>
            Live: {promotedVersion}
          </Typography>
        )}
      </Box>

      {/* Promote confirmation dialog */}
      <Dialog open={promoteOpen} onClose={() => !promoting && setPromoteOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Promote model to live</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            <Typography variant="body2">
              Version <strong>{doneJob?.model_version}</strong> will become the live model.
            </Typography>
            {doneJob && (
              <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
                <Chip size="small" label={`P ${((doneJob.precision ?? 0) * 100).toFixed(1)}%`} color="primary" />
                <Chip size="small" label={`R ${((doneJob.recall ?? 0) * 100).toFixed(1)}%`} color="primary" />
                <Chip size="small" label={`F1 ${((doneJob.f1 ?? 0) * 100).toFixed(1)}%`} color="success" />
                {doneJob.golden_f1 != null && (
                  <Chip
                    size="small"
                    label={`Golden F1 ${(doneJob.golden_f1 * 100).toFixed(1)}%`}
                    color={doneJob.golden_passed ? "success" : "error"}
                    icon={<LockIcon sx={{ fontSize: 14 }} />}
                  />
                )}
              </Box>
            )}
            <TextField
              label="Promotion notes (optional)"
              multiline
              rows={3}
              value={promoteNotes}
              onChange={(e) => setPromoteNotes(e.target.value)}
              fullWidth
              size="small"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPromoteOpen(false)} disabled={promoting}>Cancel</Button>
          <Button
            variant="contained"
            color="success"
            onClick={handlePromote}
            disabled={promoting}
          >
            {promoting ? "Promoting..." : "Confirm promotion"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// -- Score card --------------------------------------------------------------

function ScoreCard({
  label,
  value,
  pass,
  locked = false,
}: {
  label: string;
  value: number | null | undefined;
  pass: boolean;
  locked?: boolean;
}) {
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: pass ? "success.main" : "error.main",
        borderRadius: 1.5,
        px: 1.5,
        py: 0.75,
        minWidth: 80,
        textAlign: "center",
        bgcolor: pass ? "success.50" : "error.50",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 0.5 }}>
        <Typography sx={{ fontSize: FONT_SIZES.label, color: "text.secondary" }}>{label}</Typography>
        {locked && <LockIcon sx={{ fontSize: 12, color: "text.disabled" }} />}
      </Box>
      <Typography sx={{ fontWeight: 700, fontSize: FONT_SIZES.heading, color: pass ? "success.dark" : "error.main" }}>
        {value != null ? `${(value * 100).toFixed(1)}%` : "—"}
      </Typography>
    </Box>
  );
}

// -- Per-label bar chart -----------------------------------------------------

function PerLabelChart({ perLabel }: { perLabel: Record<string, { f1: number }> }) {
  const data = Object.entries(perLabel)
    .map(([label, s]) => ({ label, f1: s.f1 }))
    .sort((a, b) => b.f1 - a.f1);

  return (
    <Box>
      <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
        Per-entity F1
      </Typography>
      <ResponsiveContainer width="100%" height={Math.max(100, data.length * 26)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 8, top: 2, bottom: 2 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
          <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
          <YAxis type="category" dataKey="label" tick={{ fontSize: 11 }} width={130} />
          <RTooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
          <Bar dataKey="f1" maxBarSize={16} radius={[0, 3, 3, 0]}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.f1 >= 0.8 ? "#2e7d32" : d.f1 >= 0.6 ? "#ed6c02" : "#d32f2f"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}

// -- Regression history table ------------------------------------------------

function RegressionTable({ jobs }: { jobs: TrainingJob[] }) {
  const doneJobs = jobs.filter((j) => j.status === "done").slice(0, 8);
  if (doneJobs.length < 2) return null;

  return (
    <Box>
      <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
        Regression history
      </Typography>
      <Box sx={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: FONT_SIZES.label }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #e0e0e0" }}>
              {["Version", "F1", "P", "R", "Golden F1", "Gates"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontWeight: 600, fontSize: FONT_SIZES.label }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {doneJobs.map((j, i) => {
              const prevF1 = doneJobs[i + 1]?.f1;
              const delta = j.f1 != null && prevF1 != null ? j.f1 - prevF1 : null;
              return (
                <tr key={j.job_id} style={{ borderBottom: "1px solid #f5f5f5" }}>
                  <td style={{ padding: "4px 8px" }}>{j.model_version ?? j.job_id.slice(0, 8)}</td>
                  <td style={{ padding: "4px 8px", fontWeight: 600 }}>
                    {j.f1 != null ? `${(j.f1 * 100).toFixed(1)}%` : "—"}
                    {delta != null && (
                      <span style={{ color: delta >= 0 ? "#2e7d32" : "#d32f2f", marginLeft: 4, fontSize: "0.65rem" }}>
                        {delta >= 0 ? "+" : ""}{(delta * 100).toFixed(1)}%
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "4px 8px" }}>{j.precision != null ? `${(j.precision * 100).toFixed(1)}%` : "—"}</td>
                  <td style={{ padding: "4px 8px" }}>{j.recall != null ? `${(j.recall * 100).toFixed(1)}%` : "—"}</td>
                  <td style={{ padding: "4px 8px" }}>
                    {j.golden_f1 != null ? `${(j.golden_f1 * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td style={{ padding: "4px 8px" }}>
                    <Chip
                      size="small"
                      label={j.passed_gates ? "Pass" : "Fail"}
                      color={j.passed_gates ? "success" : "error"}
                      sx={{ height: 16, fontSize: "0.62rem" }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Box>
    </Box>
  );
}
