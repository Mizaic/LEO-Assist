"use client";

import { useId } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";

interface Props {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "danger" | "primary";
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Accessible confirmation dialog.
 *
 * aria-labelledby and aria-describedby are wired via generated useId() so
 * screen readers announce both the title and the body on open.
 * See DI-LEO-AI-120 and VT-LEO-AI-115.
 */
export default function ConfirmDialog({
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  variant = "primary",
  onConfirm,
  onCancel,
}: Props) {
  const titleId = useId();
  const bodyId = useId();
  return (
    <Dialog
      open
      onClose={onCancel}
      maxWidth="xs"
      fullWidth
      aria-labelledby={titleId}
      aria-describedby={bodyId}
    >
      <DialogTitle id={titleId}>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText id={bodyId} color="text.secondary">
          {body}
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button variant="text" color="inherit" onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button
          variant="contained"
          color={variant === "danger" ? "error" : "primary"}
          onClick={onConfirm}
          autoFocus
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
