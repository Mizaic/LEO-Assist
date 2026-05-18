/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Copy a real patient as a de-identified test patient.
 *
 * This dialog drives the cross-graph clone described in DI-7625C251 /
 * R-8C0CC94B (Atlas):
 *   - Source list comes from the patient graph (real :Patient rows).
 *   - The clone runs through the NLP redactor + regex layer in the
 *     API service, which strips PII from free text and refuses to
 *     write the test patient if any residual PII slips past.
 *   - The cloned subgraph is written into the knowledge graph next
 *     to the saved fixtures.
 *
 * The reviewer chooses one source patient and one aspect, then
 * confirms. The dialog shows a count summary on success so the
 * reviewer can verify "what got copied" before closing.
 *
 * Audience standard (.cursor/rules/health-literacy.mdc): plain
 * English, UK reading age 11. "Aspect" -> "Part of AI"; "Encounters"
 * -> "Visits"; "Concept relationships" -> "Coded entries".
 */

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  ASPECT_HINT,
  ASPECT_LABEL,
  type AspectFilter,
  type CloneResult,
  type SourcePatientPickerEntry,
} from "./types";
import { cloneFromReal, listSourcePatients } from "./api";

type CloneAspect = Exclude<AspectFilter, "all">;

const CLONE_ASPECTS: CloneAspect[] = [
  "nlp",
  "episodes",
  "guidelines",
  "summarisation",
];

interface CopyFromRealDialogProps {
  open: boolean;
  initialAspect?: AspectFilter;
  onClose: () => void;
  onCloned: (id: string) => void;
}

function pickInitialAspect(initial?: AspectFilter): CloneAspect {
  if (initial && initial !== "all") return initial;
  return "nlp";
}

// LONG FUNCTION: dialog owns source-load lifecycle + form + submit.
// Splitting would scatter the loading/error state across files.
export default function CopyFromRealDialog({
  open,
  initialAspect,
  onClose,
  onCloned,
}: CopyFromRealDialogProps) {
  const [sources, setSources] = useState<SourcePatientPickerEntry[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);

  const [selected, setSelected] = useState<SourcePatientPickerEntry | null>(
    null,
  );
  const [aspect, setAspect] = useState<CloneAspect>(() =>
    pickInitialAspect(initialAspect),
  );
  const [description, setDescription] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<CloneResult | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoadingSources(true);
    setSourceError(null);
    listSourcePatients(50)
      .then((rows) => setSources(rows))
      .catch((exc: unknown) => {
        setSourceError(
          exc instanceof Error
            ? exc.message
            : "Could not load real patients for copying.",
        );
      })
      .finally(() => setLoadingSources(false));
  }, [open]);

  useEffect(() => {
    if (open) setAspect(pickInitialAspect(initialAspect));
  }, [open, initialAspect]);

  const handleClose = () => {
    if (submitting) return;
    setSelected(null);
    setDescription("");
    setSubmitError(null);
    setResult(null);
    onClose();
  };

  const handleSubmit = async () => {
    if (!selected) {
      setSubmitError("Pick a real patient to copy from first.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const cloneResult = await cloneFromReal({
        source_patient_id: selected.id,
        aspect,
        description: description.trim(),
      });
      setResult(cloneResult);
      onCloned(cloneResult.id);
    } catch (exc) {
      setSubmitError(
        exc instanceof Error
          ? exc.message
          : "Could not copy this patient. Try again, or pick another.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const aspectHint = useMemo(() => ASPECT_HINT[aspect], [aspect]);

  if (result) {
    return (
      <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
        <DialogTitle>Copy complete</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="success">
              Saved as <strong>{result.name}</strong>. Real patient details
              were removed before saving.
            </Alert>
            <Box>
              <Typography variant="body2" color="text.secondary">
                What we copied across:
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Chip
                  size="small"
                  label={`${result.encounters_cloned} visits`}
                />
                <Chip
                  size="small"
                  label={`${result.documents_cloned} notes`}
                />
                <Chip
                  size="small"
                  label={`${result.concept_rels_cloned} coded entries`}
                />
              </Stack>
            </Box>
            <Typography variant="caption" color="text.secondary">
              Test patient ID: {result.id}
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button variant="contained" onClick={handleClose}>
            Done
          </Button>
        </DialogActions>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Copy a real patient as a test patient</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info" variant="outlined">
            We copy a real patient into the test library, then remove
            anything that could identify them (NHS number, name, address,
            phone, dates of birth, postcode). The original patient record
            is not changed.
          </Alert>

          {sourceError ? (
            <Alert severity="error">{sourceError}</Alert>
          ) : null}

          <Autocomplete
            options={sources}
            value={selected}
            onChange={(_event, value) => setSelected(value)}
            getOptionLabel={(option) =>
              `${option.display_name} (${option.encounter_count} visits)`
            }
            isOptionEqualToValue={(option, value) => option.id === value.id}
            loading={loadingSources}
            disabled={submitting}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Real patient"
                placeholder="Pick a real patient..."
                helperText="Only real patients show here. Test patients are filtered out."
              />
            )}
          />

          <TextField
            select
            label="Part of AI to test with this copy"
            value={aspect}
            onChange={(event) => setAspect(event.target.value as CloneAspect)}
            helperText={aspectHint}
            disabled={submitting}
            fullWidth
          >
            {CLONE_ASPECTS.map((value) => (
              <MenuItem key={value} value={value}>
                {ASPECT_LABEL[value]}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="What this copy is for (optional)"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            disabled={submitting}
            fullWidth
            multiline
            minRows={2}
            placeholder="One short line that tells future reviewers why this fixture exists."
          />

          {submitError ? (
            <Alert severity="error" onClose={() => setSubmitError(null)}>
              {submitError}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color="primary"
          onClick={handleSubmit}
          disabled={submitting || !selected}
          startIcon={
            submitting ? <CircularProgress size={16} color="inherit" /> : null
          }
        >
          {submitting ? "Copying..." : "Copy and remove identifiers"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
