/**
 * Mark a pipeline fact as wrong and pick a category.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import { useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";

import {
  FINDING_CATEGORIES,
  type FindingCategory,
} from "./findingTypes";

interface Props {
  open: boolean;
  target: string;
  onClose: () => void;
  onSave: (category: FindingCategory, note: string) => Promise<void>;
}

export default function MarkWrongDialog({
  open,
  target,
  onClose,
  onSave,
}: Props) {
  const [category, setCategory] = useState<FindingCategory>("extraction");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      await onSave(category, note.trim());
      setNote("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      data-testid="validation-lab-mark-wrong-dialog"
    >
      <DialogTitle>Mark as wrong</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          What went wrong with {target ? `"${target}"` : "this item"}?
        </Typography>
        <ToggleButtonGroup
          exclusive
          fullWidth
          orientation="vertical"
          value={category}
          onChange={(_, value) => {
            if (value) setCategory(value);
          }}
          sx={{ mb: 2 }}
        >
          {FINDING_CATEGORIES.map((row) => (
            <ToggleButton
              key={row.id}
              value={row.id}
              data-testid={`validation-lab-flag-${row.id}`}
              sx={{ justifyContent: "flex-start", textAlign: "left", py: 1 }}
            >
              <Stack>
                <Typography variant="body2" fontWeight={700}>
                  {row.label}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {row.hint}
                </Typography>
              </Stack>
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <TextField
          label="Note (plain English)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          fullWidth
          multiline
          minRows={2}
          inputProps={{ maxLength: 1000 }}
        />
        {error ? (
          <Typography variant="body2" color="error" sx={{ mt: 1 }}>
            {error}
          </Typography>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => void submit()}
          disabled={busy}
          data-testid="validation-lab-mark-wrong-save"
        >
          Save finding
        </Button>
      </DialogActions>
    </Dialog>
  );
}
