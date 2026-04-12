"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import ConfirmDialog from "@/components/ConfirmDialog";

type JobState = "queued" | "running" | "completed" | "failed";

interface Props {
  selectedCount: number;
  totalResults: number;
  loading: boolean;
  triggerAnalysis: boolean;
  onTriggerAnalysisChange: (v: boolean) => void;
  statuses: Record<string, JobState>;
  message: string | null;
  onRunBatchSelected: () => void;
  onRunBatchAll: () => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
  hasRows: boolean;
}

function jobCounts(statuses: Record<string, JobState>) {
  const values = Object.values(statuses);
  return {
    queued: values.filter((s) => s === "queued").length,
    running: values.filter((s) => s === "running").length,
    completed: values.filter((s) => s === "completed").length,
    failed: values.filter((s) => s === "failed").length,
    total: values.length,
  };
}

function messageAlertSeverity(msg: string): "success" | "info" | "warning" | "error" {
  if (msg.startsWith("Batch queued")) return "success";
  if (msg.toLowerCase().includes("fail") || msg.toLowerCase().includes("error")) return "error";
  if (msg.toLowerCase().includes("select") || msg.toLowerCase().includes("no encounter")) return "warning";
  return "info";
}

export default function EncounterBatchBar({
  selectedCount,
  totalResults,
  loading,
  triggerAnalysis,
  onTriggerAnalysisChange,
  statuses,
  message,
  onRunBatchSelected,
  onRunBatchAll,
  onSelectAll,
  onClearSelection,
  hasRows,
}: Props) {
  const [confirmAll, setConfirmAll] = useState(false);
  const counts = jobCounts(statuses);
  const hasStatuses = counts.total > 0;

  return (
    <Paper
      elevation={0}
      sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2 }}
    >
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Button
          variant="contained"
          color="warning"
          size="small"
          onClick={onRunBatchSelected}
          disabled={!selectedCount}
        >
          Recode selected ({selectedCount})
        </Button>
        <Button
          variant="contained"
          color="error"
          size="small"
          onClick={() => { if (totalResults > 0) setConfirmAll(true); }}
          disabled={!totalResults || loading}
        >
          Recode all results ({totalResults})
        </Button>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

        <Button variant="text" size="small" onClick={onSelectAll} disabled={!hasRows}>
          Select loaded
        </Button>
        <Button
          variant="text"
          size="small"
          color="inherit"
          onClick={onClearSelection}
          disabled={!selectedCount}
        >
          Clear
        </Button>

        <Box sx={{ flex: 1 }} />

        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={triggerAnalysis}
              onChange={(e) => onTriggerAnalysisChange(e.target.checked)}
            />
          }
          label={<Typography variant="body2">Rerun analytics</Typography>}
          sx={{ mr: 0 }}
        />
      </Stack>

      {hasStatuses && (
        <Stack direction="row" spacing={0.75} sx={{ mt: 1.5, flexWrap: "wrap" }} useFlexGap>
          {counts.queued > 0 && (
            <Chip size="small" label={`${counts.queued} queued`} variant="outlined" />
          )}
          {counts.running > 0 && (
            <Chip size="small" label={`${counts.running} running`} color="info" variant="filled" />
          )}
          {counts.completed > 0 && (
            <Chip size="small" label={`${counts.completed} done`} color="success" variant="filled" />
          )}
          {counts.failed > 0 && (
            <Chip size="small" label={`${counts.failed} failed`} color="error" variant="filled" />
          )}
        </Stack>
      )}

      {message && (
        <Alert
          severity={messageAlertSeverity(message)}
          sx={{ mt: 1.5 }}
          onClose={() => {}}
        >
          {message}
        </Alert>
      )}

      {confirmAll && (
        <ConfirmDialog
          title="Recode all matching encounters?"
          body={`This will queue reset and recode for all ${totalResults} encounters that match your current search. This cannot be undone.`}
          confirmLabel={`Recode all ${totalResults}`}
          variant="danger"
          onConfirm={() => {
            setConfirmAll(false);
            onRunBatchAll();
          }}
          onCancel={() => setConfirmAll(false)}
        />
      )}
    </Paper>
  );
}
