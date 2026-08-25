/**
 * Confirm removal of a paused extraction from My work.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 */
"use client";

import { useState } from "react";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";

import ConfirmDialog from "@/components/ConfirmDialog";
import {
  CANCEL_TASK_BODY,
  CANCEL_TASK_REASONS,
  CANCEL_TASK_TITLE,
} from "@/components/operations/extractionReviewCopy";

interface Props {
  taskId: string;
  onClose: () => void;
  onCancelled: () => void;
}

export default function WorkCancelDialog({
  taskId,
  onClose,
  onCancelled,
}: Props) {
  const [reason, setReason] = useState("duplicate");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirmRemove() {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/operations/extraction-reviews/cancel", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          task_id: taskId,
          reason,
          cancelled_by: "my_work",
        }),
      });
      if (!res.ok) throw new Error("cancel");
      onCancelled();
    } catch {
      setError("We could not remove this task. Try again.");
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog
      title={CANCEL_TASK_TITLE}
      body={error || CANCEL_TASK_BODY}
      confirmLabel="Remove task"
      cancelLabel="Keep task"
      variant="danger"
      busy={busy}
      onConfirm={() => {
        void confirmRemove();
      }}
      onCancel={onClose}
    >
      <TextField
        select
        fullWidth
        size="small"
        margin="normal"
        label="Why are you removing it?"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        disabled={busy}
        data-testid="work-cancel-reason"
      >
        {CANCEL_TASK_REASONS.map((item) => (
          <MenuItem key={item.value} value={item.value}>
            {item.label}
          </MenuItem>
        ))}
      </TextField>
    </ConfirmDialog>
  );
}
