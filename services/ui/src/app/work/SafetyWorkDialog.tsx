/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import type { WorkTask } from "@leo/design-system";
import { patchAlert } from "@/lib/patientEprApi";
import { workTaskSourceId } from "./workTaskSourceId";

interface Props {
  task: WorkTask;
  onClose: () => void;
  onResolved: () => void;
}

export default function SafetyWorkDialog({ task, onClose, onResolved }: Props) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const alertId = workTaskSourceId(task.task_id);
  const patientId = task.patient_id ?? "";

  async function act(action: "resolve" | "escalate"): Promise<void> {
    if (!patientId) {
      setError("This alert has no patient, so it cannot be closed here.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await patchAlert(patientId, alertId, action);
      onResolved();
    } catch {
      setError("Could not save. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      data-testid="work-task-dialog"
    >
      <DialogTitle sx={{ pr: 6 }}>
        {task.summary}
        <IconButton
          aria-label="Close"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        ) : null}
        <Typography variant="body2">
          Mark this safety alert as done, or send it on if it still needs action.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          variant="outlined"
          onClick={() => void act("escalate")}
          disabled={busy}
        >
          Escalate
        </Button>
        <Button
          variant="contained"
          onClick={() => void act("resolve")}
          disabled={busy}
        >
          Resolve
        </Button>
      </DialogActions>
    </Dialog>
  );
}
