/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-C4EC82F9
 *   DI: DI-B0832A64
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-C4EC82F9")
 */
"use client";

import { useId } from "react";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
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
  /** When true, disable dismiss/actions and show in-progress feedback. */
  busy?: boolean;
  busyLabel?: string;
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
  busy = false,
  busyLabel = "Working...",
  onConfirm,
  onCancel,
}: Props) {
  const titleId = useId();
  const bodyId = useId();
  return (
    <Dialog
      open
      onClose={busy ? undefined : onCancel}
      disableEscapeKeyDown={busy}
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
        <Button variant="text" color="inherit" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button
          variant="contained"
          color={variant === "danger" ? "error" : "primary"}
          onClick={onConfirm}
          disabled={busy}
          autoFocus={!busy}
          startIcon={
            busy ? (
              <CircularProgress size={14} color="inherit" aria-label="Loading" role="status" />
            ) : undefined
          }
        >
          {busy ? busyLabel : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
