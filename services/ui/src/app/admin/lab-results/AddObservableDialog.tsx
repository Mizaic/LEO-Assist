/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
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

import { SnomedPickConfirmDialog } from "@/components/SnomedPickConfirmDialog";

import { saveLabResultConfig } from "./api";
import { FindingSnomedPicker, type LabSnomedPick } from "./FindingSnomedPicker";

interface Props {
  onClose: () => void;
  onCreated: (conceptId: string) => void;
}

export default function AddObservableDialog({ onClose, onCreated }: Props) {
  const [pending, setPending] = useState<LabSnomedPick | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [canonicalUnit, setCanonicalUnit] = useState("");
  const [source, setSource] = useState("manual");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handlePick(next: LabSnomedPick) {
    setPending(next);
    if (!displayName) setDisplayName(stripTag(next.term));
  }

  async function handleSave() {
    if (!pending?.concept_id) {
      setError("Search SNOMED or Ask LEO, then pick the observable code.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await saveLabResultConfig(pending.concept_id, {
        display_name: displayName || stripTag(pending.term),
        canonical_unit: canonicalUnit,
        source,
      });
      onCreated(pending.concept_id);
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
          {error ? <Alert severity="error">{error}</Alert> : null}
          <FindingSnomedPicker
            seedText={displayName || "laboratory observable"}
            hintTags={["observable entity"]}
            pickedId={pending?.concept_id || ""}
            onPick={handlePick}
            label="Search SNOMED"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button variant="text" color="inherit" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
      </DialogActions>
      {pending ? (
        <SnomedPickConfirmDialog
          copy={{
            title: "Add this observable?",
            lead: "LEO will use this SNOMED code for the laboratory test.",
            confirmLabel: "Add observable",
          }}
          pick={{
            term: pending.term,
            conceptId: pending.concept_id,
            tag: pending.semantic_tag,
          }}
          action={{
            busy: saving,
            onConfirm: () => void handleSave(),
            onCancel: () => setPending(null),
          }}
        >
          <ObservableFields
            name={{ value: displayName, onChange: setDisplayName }}
            unit={{ value: canonicalUnit, onChange: setCanonicalUnit }}
            source={{ value: source, onChange: setSource }}
          />
        </SnomedPickConfirmDialog>
      ) : null}
    </Dialog>
  );
}

function ObservableFields({
  name,
  unit,
  source,
}: {
  name: { value: string; onChange: (next: string) => void };
  unit: { value: string; onChange: (next: string) => void };
  source: { value: string; onChange: (next: string) => void };
}) {
  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <TextField
        label="Display name"
        value={name.value}
        onChange={(e) => name.onChange(e.target.value)}
        fullWidth
        helperText="How LEO shows this test to clinicians"
      />
      <TextField
        label="Canonical unit"
        value={unit.value}
        onChange={(e) => unit.onChange(e.target.value)}
        fullWidth
        helperText="The base unit all results are converted to (e.g. g/dL)"
      />
      <TextField
        label="Source"
        value={source.value}
        onChange={(e) => source.onChange(e.target.value)}
        fullWidth
        helperText="Who configured this (e.g. manual, NICE, local)"
      />
    </Stack>
  );
}

function stripTag(term: string): string {
  return term.replace(/\s*\([^)]+\)\s*$/, "").trim();
}
