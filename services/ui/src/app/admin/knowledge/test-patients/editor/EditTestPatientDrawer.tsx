"use client";

/**
 * Edit drawer for the centralised test patient library.
 *
 * Loads the entire editable subgraph for one :TestPatient via
 * GET /full, lets the reviewer edit the demographics + per-aspect
 * content, and PATCH'es the whole shape back atomically. The form
 * surface switches by aspect:
 *
 *   - Reading notes (NLP):       free text + expected SNOMED codes.
 *   - Patient story (Episodes):  encounter timeline (text + date +
 *                                source label) + expected codes per
 *                                encounter.
 *   - SBAR handover:             encounters as above PLUS the
 *                                expected SBAR transcript and the
 *                                must-include / must-not-say lists.
 *   - Rule checks (Guidelines):  read-only here -- the reviewer is
 *                                directed back to the guideline
 *                                editor where the rule-fire snapshot
 *                                lives. PATCH /full rejects this
 *                                aspect so we surface that here too.
 *
 * Audience standard (see .cursor/rules/health-literacy.mdc):
 * UK reading age 11; "encounter" -> "note", "aspect" -> "part of AI",
 * "SNOMED code" -> "SNOMED ID" with one-sentence helper copy.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
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
  type EditorEncounter,
  type EditorExpectedSbar,
  type FullTestPatient,
  type UpdateFullBody,
} from "../types";
import { getTestPatientFull, updateTestPatientFull } from "../api";
import EncounterListEditor from "./EncounterListEditor";
import ExpectedSbarEditor from "./ExpectedSbarEditor";

interface EditTestPatientDrawerProps {
  patientId: string | null;
  open: boolean;
  onClose: () => void;
  onSaved: (id: string) => void;
}

interface FormState {
  name: string;
  description: string;
  age: string;
  sex: "" | "male" | "female" | "other";
  encounters: EditorEncounter[];
  expectedSbar: EditorExpectedSbar;
}

const EMPTY_EXPECTED_SBAR: EditorExpectedSbar = {
  id: null,
  fixture_id: null,
  situation_md: "",
  background_md: "",
  recommendation_md: "",
  matched_rule_ids: [],
  required_phrases: [],
  banned_phrases: [],
  expected_action_priority: null,
  reviewer_focus: "",
};

function ageToString(age: number | null): string {
  if (age === null || age === undefined) return "";
  return String(age);
}

function loadedToForm(loaded: FullTestPatient): FormState {
  const sex = (loaded.sex ?? "") as FormState["sex"];
  return {
    name: loaded.name ?? "",
    description: loaded.description ?? "",
    age: ageToString(loaded.age),
    sex: sex === "male" || sex === "female" || sex === "other" ? sex : "",
    encounters: loaded.encounters ?? [],
    expectedSbar: loaded.expected_sbar ?? { ...EMPTY_EXPECTED_SBAR },
  };
}

function parseAge(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function isGuidelinesAspect(aspect: string | null | undefined): boolean {
  return (aspect ?? "").toLowerCase() === "guidelines";
}

// LONG FUNCTION: drawer owns load + form + save state and dispatches
// the right per-aspect form. Splitting would scatter loading state.
export default function EditTestPatientDrawer({
  patientId,
  open,
  onClose,
  onSaved,
}: EditTestPatientDrawerProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<FullTestPatient | null>(null);
  const [form, setForm] = useState<FormState | null>(null);

  useEffect(() => {
    if (!open || !patientId) {
      setLoaded(null);
      setForm(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    getTestPatientFull(patientId)
      .then((row) => {
        setLoaded(row);
        setForm(loadedToForm(row));
      })
      .catch((exc: unknown) => {
        setError(
          exc instanceof Error
            ? exc.message
            : "Could not load that test patient.",
        );
      })
      .finally(() => setLoading(false));
  }, [open, patientId]);

  const aspect = loaded?.aspect ?? null;
  const guidelinesAspect = isGuidelinesAspect(aspect);

  const handleClose = useCallback(() => {
    if (saving) return;
    onClose();
  }, [onClose, saving]);

  const handleSave = useCallback(async () => {
    if (!form || !loaded || !patientId) return;
    if (guidelinesAspect) return;
    if (!form.name.trim()) {
      setError("Give the test patient a short name first.");
      return;
    }
    const age = parseAge(form.age);
    if (form.age.trim() && age === null) {
      setError("Age must be a whole number.");
      return;
    }
    const aspectKey = (loaded.aspect ?? "nlp") as UpdateFullBody["aspect"];
    const body: UpdateFullBody = {
      aspect: aspectKey,
      name: form.name.trim(),
      description: form.description.trim(),
      age,
      sex: form.sex || null,
      encounters: form.encounters,
      expected_sbar:
        aspectKey === "summarisation" ? form.expectedSbar : null,
    };
    setSaving(true);
    setError(null);
    try {
      const result = await updateTestPatientFull(patientId, body);
      onSaved(result.id);
      onClose();
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Could not save the changes. Try again.",
      );
    } finally {
      setSaving(false);
    }
  }, [form, loaded, patientId, guidelinesAspect, onClose, onSaved]);

  const dialogTitle = useMemo(() => {
    if (!loaded) return "Edit test patient";
    return `Edit ${loaded.name}`;
  }, [loaded]);

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      fullWidth
      maxWidth="lg"
      data-testid="edit-test-patient-drawer"
    >
      <DialogTitle>{dialogTitle}</DialogTitle>
      <DialogContent dividers>
        {loading ? (
          <Stack alignItems="center" sx={{ py: 6 }}>
            <CircularProgress size={28} />
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: 1 }}
            >
              Loading the test patient...
            </Typography>
          </Stack>
        ) : null}

        {!loading && error && !loaded ? (
          <Alert severity="error" onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}

        {!loading && loaded && form ? (
          <Stack spacing={3} sx={{ mt: 1 }}>
            <Alert severity="info" icon={false}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Part of AI: {ASPECT_LABEL[loaded.aspect]}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {ASPECT_HINT[loaded.aspect]}
              </Typography>
            </Alert>

            {guidelinesAspect ? (
              <Alert severity="warning">
                Rule-check patients are edited inside the guideline editor
                so the snapshot of which rules should fire is kept in
                step. Open the linked guideline to make changes.
              </Alert>
            ) : null}

            <TextField
              label="Short name"
              helperText='We will keep the "test_" prefix automatically.'
              value={form.name}
              onChange={(event) =>
                setForm((prev) =>
                  prev ? { ...prev, name: event.target.value } : prev,
                )
              }
              disabled={saving || guidelinesAspect}
              fullWidth
              required
            />

            <TextField
              label="What this patient is for"
              value={form.description}
              onChange={(event) =>
                setForm((prev) =>
                  prev
                    ? { ...prev, description: event.target.value }
                    : prev,
                )
              }
              disabled={saving || guidelinesAspect}
              fullWidth
              multiline
              minRows={2}
            />

            <Box sx={{ display: "flex", gap: 2 }}>
              <TextField
                label="Age (years)"
                type="number"
                value={form.age}
                onChange={(event) =>
                  setForm((prev) =>
                    prev ? { ...prev, age: event.target.value } : prev,
                  )
                }
                inputProps={{ min: 0, max: 130, step: 1 }}
                disabled={saving || guidelinesAspect}
                sx={{ flex: 1 }}
              />
              <TextField
                select
                label="Sex"
                value={form.sex}
                onChange={(event) =>
                  setForm((prev) =>
                    prev
                      ? {
                          ...prev,
                          sex: event.target.value as FormState["sex"],
                        }
                      : prev,
                  )
                }
                disabled={saving || guidelinesAspect}
                sx={{ flex: 1 }}
              >
                <MenuItem value="">Not set</MenuItem>
                <MenuItem value="female">Female</MenuItem>
                <MenuItem value="male">Male</MenuItem>
                <MenuItem value="other">Other</MenuItem>
              </TextField>
            </Box>

            {!guidelinesAspect ? (
              <>
                <Typography variant="subtitle1">
                  Notes for the AI to read
                </Typography>
                <EncounterListEditor
                  encounters={form.encounters}
                  showDate={
                    loaded.aspect === "episodes" ||
                    loaded.aspect === "summarisation"
                  }
                  showSource={
                    loaded.aspect === "episodes" ||
                    loaded.aspect === "summarisation"
                  }
                  textLabel={
                    loaded.aspect === "nlp"
                      ? "Free text the AI will read"
                      : "Note text"
                  }
                  onChange={(next) =>
                    setForm((prev) =>
                      prev ? { ...prev, encounters: next } : prev,
                    )
                  }
                  disabled={saving}
                />
              </>
            ) : null}

            {loaded.aspect === "summarisation" ? (
              <ExpectedSbarEditor
                value={form.expectedSbar}
                onChange={(next) =>
                  setForm((prev) =>
                    prev ? { ...prev, expectedSbar: next } : prev,
                  )
                }
                disabled={saving}
              />
            ) : null}

            {error ? (
              <Alert severity="error" onClose={() => setError(null)}>
                {error}
              </Alert>
            ) : null}
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={saving}>
          Close
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={
            saving ||
            loading ||
            !form ||
            guidelinesAspect ||
            !form?.name.trim()
          }
          startIcon={
            saving ? <CircularProgress size={16} color="inherit" /> : null
          }
        >
          {saving ? "Saving..." : "Save changes"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
