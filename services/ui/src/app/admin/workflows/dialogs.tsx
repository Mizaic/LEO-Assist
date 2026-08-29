"use client";

import { useState, useCallback } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { CreateWorkflowPayload, Workflow } from "./types";
import { workflowTitle } from "./workflowDisplay";

// -- New Workflow Dialog -------------------------------------------------------

interface NewWorkflowDialogProps {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onCreate: (payload: CreateWorkflowPayload) => void;
}

export function NewWorkflowDialog({
  open,
  busy,
  onClose,
  onCreate,
}: NewWorkflowDialogProps) {
  const [name, setName] = useState("");

  const handleSubmit = useCallback(() => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onCreate({ name: trimmed, serviceId: "" });
    setName("");
  }, [name, onCreate]);

  const handleClose = useCallback(() => {
    setName("");
    onClose();
  }, [onClose]);

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>New workflow</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2, color: "text.secondary" }}>
          Give this workflow a clear name. You can connect it to a service once
          it is open in the canvas.
        </Typography>
        <TextField
          autoFocus
          fullWidth
          label="Workflow name"
          placeholder="e.g. Colorectal Referral - Standard"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
          inputProps={{ maxLength: 120 }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={!name.trim() || busy}
          onClick={handleSubmit}
        >
          {busy ? "Creating..." : "Create workflow"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// -- Delete Workflow Dialog ----------------------------------------------------

interface DeleteWorkflowDialogProps {
  workflow: Workflow | null;
  busy: boolean;
  onClose: () => void;
  onConfirm: (id: string) => void;
}

export function DeleteWorkflowDialog({
  workflow,
  busy,
  onClose,
  onConfirm,
}: DeleteWorkflowDialogProps) {
  const [confirmText, setConfirmText] = useState("");

  const handleClose = useCallback(() => {
    setConfirmText("");
    onClose();
  }, [onClose]);

  const handleConfirm = useCallback(() => {
    if (!workflow) return;
    onConfirm(workflow.id);
    setConfirmText("");
  }, [workflow, onConfirm]);

  const title = workflow ? workflowTitle(workflow) : "";
  const canDelete = confirmText.trim() === title;

  return (
    <Dialog open={!!workflow} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Delete workflow?</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          This will permanently delete{" "}
          <strong>{title}</strong> and all its steps. This cannot be
          undone. Any referrals currently in this workflow will lose their step
          associations.
        </Typography>
        <Typography variant="body2" sx={{ mb: 1, color: "text.secondary" }}>
          Type <strong>{title}</strong> to confirm.
        </Typography>
        <TextField
          autoFocus
          fullWidth
          label="Workflow name"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && canDelete) handleConfirm(); }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color="error"
          disabled={!canDelete || busy}
          onClick={handleConfirm}
        >
          {busy ? "Deleting..." : "Delete workflow"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
