/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-21936FDD")
 */
"use client";

import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";

export interface CreateSubdomainDialogProps {
  open: boolean;
  createSubmitting: boolean;
  createName: string;
  createDesc: string;
  onClose: () => void;
  onCreateNameChange: (v: string) => void;
  onCreateDescChange: (v: string) => void;
  onSubmit: () => void;
}

export default function CreateSubdomainDialog({
  open,
  createSubmitting,
  createName,
  createDesc,
  onClose,
  onCreateNameChange,
  onCreateDescChange,
  onSubmit,
}: CreateSubdomainDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={() => !createSubmitting && onClose()}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>Create subdomain</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          label="Subdomain name"
          placeholder="e.g. cancer types"
          fullWidth
          value={createName}
          onChange={(e) => onCreateNameChange(e.target.value)}
          helperText="Spaces will be converted to underscores."
        />
        <TextField
          margin="dense"
          label="Description"
          placeholder="Optional description"
          fullWidth
          multiline
          rows={2}
          value={createDesc}
          onChange={(e) => onCreateDescChange(e.target.value)}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={createSubmitting}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={onSubmit}
          disabled={!createName.trim() || createSubmitting}
        >
          {createSubmitting ? "Creating\u2026" : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
