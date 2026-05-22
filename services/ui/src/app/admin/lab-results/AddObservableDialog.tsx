"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";

import { saveLabResultConfig } from "./api";

interface Props {
  onClose: () => void;
  onCreated: (conceptId: string) => void;
}

export default function AddObservableDialog({ onClose, onCreated }: Props) {
  const [conceptId, setConceptId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [canonicalUnit, setCanonicalUnit] = useState("");
  const [source, setSource] = useState("manual");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    if (!conceptId.trim()) {
      setError("Enter the observable SNOMED code.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveLabResultConfig(conceptId.trim(), {
        display_name: displayName,
        canonical_unit: canonicalUnit,
        source,
      });
      onCreated(conceptId.trim());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to save observable.");
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      aria-labelledby="add-observable-title"
    >
      <DialogTitle id="add-observable-title">Add observable</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Observable SNOMED code"
            value={conceptId}
            onChange={(e) => setConceptId(e.target.value)}
            required
            autoFocus
            fullWidth
            helperText="The SNOMED CT concept ID for this observable (e.g. 1022791000000101)"
          />
          <TextField
            label="Display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            fullWidth
            helperText="How LEO shows this test to clinicians"
          />
          <TextField
            label="Canonical unit"
            value={canonicalUnit}
            onChange={(e) => setCanonicalUnit(e.target.value)}
            fullWidth
            helperText="The base unit all results are converted to (e.g. g/dL)"
          />
          <TextField
            label="Source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            fullWidth
            helperText="Who configured this (e.g. manual, NICE, local)"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button variant="text" color="inherit" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Add observable"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
