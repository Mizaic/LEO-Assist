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
 * Scaffold a test patient from a free-text scenario (AI-assisted).
 *
 * Flow 2 of the AI-assisted authoring story for the Knowledge >
 * Test Patients tab. The reviewer:
 *   1. Picks the part of AI to test against (default: SBAR handover).
 *   2. Types a short scenario like "67yo woman with 2-week visible
 *      haematuria, BP 140/85, PMHx HTN".
 *   3. Clicks "Author from scenario". The backend asks Haiku to
 *      expand the scenario into demographics + 1-2 plain English UK
 *      GP notes + a list of clinical terms. Each term is resolved
 *      to SNOMED via the production terminology service, the rule
 *      engine is asked which AppropriatenessRules would fire, and
 *      the expected SBAR (when the aspect is SBAR) is filled in
 *      deterministically from the rule engine's verdict.
 *   4. On success the editor drawer opens with the new patient
 *      pre-populated. The dialog also surfaces a short summary of
 *      what resolved, what needs review, and which rules fired so
 *      the reviewer knows what to check.
 *
 * Audience standard (see .cursor/rules/health-literacy.mdc):
 *   - UK reading age 11.
 *   - "Aspect" -> "Part of AI"; "SNOMED resolution" ->
 *     "matched to a clinical code".
 *   - Errors say what failed AND what to do next.
 */

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
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
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";

import { ASPECT_HINT, ASPECT_LABEL, type AspectFilter } from "./types";
import { scaffoldFromScenario } from "./api";

type ScaffoldAspect = "nlp" | "episodes" | "summarisation";

const SCAFFOLDABLE_ASPECTS: ScaffoldAspect[] = [
  "summarisation",
  "episodes",
  "nlp",
];

const MIN_SCENARIO_CHARS = 12;
const MAX_SCENARIO_CHARS = 2000;

const SCENARIO_PLACEHOLDER =
  "e.g. 67yo woman with 2-week painless visible haematuria, " +
  "BP 140/85, PMHx HTN. No dysuria. Smoker 20/day for 30 years.";

interface ScaffoldFromScenarioDialogProps {
  open: boolean;
  initialAspect?: AspectFilter;
  onClose: () => void;
  onScaffolded: (newPatientId: string) => void;
}

function pickInitialAspect(initial: AspectFilter | undefined): ScaffoldAspect {
  if (
    initial === "nlp" ||
    initial === "episodes" ||
    initial === "summarisation"
  ) {
    return initial;
  }
  return "summarisation";
}

// LONG FUNCTION: dialog owns scenario state + submit + on-success
// summary so the reviewer sees one consistent flow. Splitting would
// scatter the success-state visibility across components.
export default function ScaffoldFromScenarioDialog({
  open,
  initialAspect,
  onClose,
  onScaffolded,
}: ScaffoldFromScenarioDialogProps) {
  const [aspect, setAspect] = useState<ScaffoldAspect>(
    pickInitialAspect(initialAspect),
  );
  const [scenario, setScenario] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setAspect(pickInitialAspect(initialAspect));
    setScenario("");
    setError(null);
    setSubmitting(false);
  }, [open, initialAspect]);

  const trimmed = scenario.trim();
  const tooShort = trimmed.length > 0 && trimmed.length < MIN_SCENARIO_CHARS;
  const tooLong = trimmed.length > MAX_SCENARIO_CHARS;
  const canSubmit =
    !submitting && trimmed.length >= MIN_SCENARIO_CHARS && !tooLong;

  const handleScaffold = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await scaffoldFromScenario({
        scenario: trimmed,
        aspect,
      });
      onScaffolded(result.patient_id);
      onClose();
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Scaffold failed. Try again, rephrase, or use Build a patient instead.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AutoAwesomeOutlinedIcon fontSize="small" />
          <Box>Author a test patient from a scenario</Box>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Type a short patient scenario -- the AI drafts plain English
          notes and finds the SNOMED codes. You review and save.
        </Typography>
      </DialogTitle>

      <DialogContent dividers>
        <Stack spacing={2}>
          <TextField
            select
            label="Part of AI to test"
            value={aspect}
            onChange={(e) => setAspect(e.target.value as ScaffoldAspect)}
            helperText={ASPECT_HINT[aspect]}
            disabled={submitting}
          >
            {SCAFFOLDABLE_ASPECTS.map((a) => (
              <MenuItem key={a} value={a}>
                {ASPECT_LABEL[a]}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Patient scenario"
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            multiline
            minRows={4}
            maxRows={10}
            fullWidth
            disabled={submitting}
            placeholder={SCENARIO_PLACEHOLDER}
            error={tooShort || tooLong}
            helperText={
              tooShort
                ? `Add a bit more detail -- at least ${MIN_SCENARIO_CHARS} characters.`
                : tooLong
                ? `Trim under ${MAX_SCENARIO_CHARS} characters.`
                : `${trimmed.length} / ${MAX_SCENARIO_CHARS} characters. ` +
                  "Plain English is fine -- the AI handles the GP shorthand."
            }
            inputProps={{
              "data-testid": "scenario-input",
              "aria-label": "Patient scenario",
            }}
          />

          <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }}>
            <Chip
              size="small"
              icon={<EditNoteOutlinedIcon fontSize="small" />}
              label="AI drafts the notes"
              variant="outlined"
            />
            <Chip
              size="small"
              label="Codes come from the terminology service"
              variant="outlined"
            />
            <Chip
              size="small"
              label="Expected SBAR comes from the rule engine"
              variant="outlined"
            />
          </Stack>

          <Alert severity="info" sx={{ mt: 1 }}>
            The AI only writes the patient prose. Clinical codes come
            from the terminology service and the expected SBAR comes
            from the rule engine -- the AI never writes its own ground
            truth. You can edit everything before saving.
          </Alert>

          {error ? <Alert severity="error">{error}</Alert> : null}
        </Stack>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          onClick={handleScaffold}
          variant="contained"
          disabled={!canSubmit}
          startIcon={
            submitting ? (
              <CircularProgress size={14} color="inherit" />
            ) : (
              <AutoAwesomeOutlinedIcon />
            )
          }
        >
          {submitting ? "Authoring..." : "Author from scenario"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
