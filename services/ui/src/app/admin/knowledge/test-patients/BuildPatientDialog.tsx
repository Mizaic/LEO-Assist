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
 * Build a (blank) test patient -- aspect-aware dialog.
 *
 * Per Atlas DI-7625C251 the centralised library has to support four
 * AI aspects. The Guidelines aspect already has a richer dialog
 * (AppearanceCard + rule expectations) inside the legacy guideline
 * editor; this dialog covers the three remaining aspects -- NLP,
 * Episodes and Summarisation -- where a Phase A build is just
 * "stamp an empty :TestPatient row, then attach content".
 *
 * For aspect = "guidelines" the dialog directs the reviewer to use
 * the guideline editor (which already has the rule-aware build
 * surface) rather than creating a half-built fixture here.
 *
 * Audience standard (see .cursor/rules/health-literacy.mdc):
 *   - UK reading age 11.
 *   - "Aspect" -> "Part of AI"; "Patient" -> short plain copy.
 *   - All errors say what failed and what to do next.
 */

import { useState } from "react";
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
  type AspectFilter,
} from "./types";
import { buildBlankTestPatient } from "./api";

type BuildableAspect = "nlp" | "episodes" | "summarisation";

const BUILDABLE_ASPECTS: BuildableAspect[] = ["nlp", "episodes", "summarisation"];

interface BuildPatientDialogProps {
  open: boolean;
  initialAspect?: AspectFilter;
  onClose: () => void;
  onCreated: (id: string) => void;
}

interface FormState {
  aspect: BuildableAspect;
  name: string;
  description: string;
  age: string;
  sex: "" | "male" | "female" | "other";
}

const EMPTY_FORM: FormState = {
  aspect: "nlp",
  name: "",
  description: "",
  age: "",
  sex: "",
};

function pickInitialAspect(initial?: AspectFilter): BuildableAspect {
  if (initial && (BUILDABLE_ASPECTS as string[]).includes(initial)) {
    return initial as BuildableAspect;
  }
  return "nlp";
}

// LONG FUNCTION: dialog must own form state, validation and submit.
// Splitting would scatter controlled-component plumbing across files.
export default function BuildPatientDialog({
  open,
  initialAspect,
  onClose,
  onCreated,
}: BuildPatientDialogProps) {
  const [form, setForm] = useState<FormState>(() => ({
    ...EMPTY_FORM,
    aspect: pickInitialAspect(initialAspect),
  }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClose = () => {
    if (submitting) return;
    setForm({ ...EMPTY_FORM, aspect: pickInitialAspect(initialAspect) });
    setError(null);
    onClose();
  };

  const handleSubmit = async () => {
    const trimmedName = form.name.trim();
    if (!trimmedName) {
      setError("Give the test patient a short name first.");
      return;
    }
    let age: number | null = null;
    if (form.age.trim()) {
      const parsed = Number(form.age.trim());
      if (!Number.isFinite(parsed) || parsed < 0 || parsed > 130) {
        setError("Age must be a whole number between 0 and 130.");
        return;
      }
      age = parsed;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await buildBlankTestPatient({
        aspect: form.aspect,
        name: trimmedName,
        description: form.description.trim(),
        age,
        sex: form.sex || null,
      });
      onCreated(result.id);
      handleClose();
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Could not create the test patient. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (initialAspect === "guidelines") {
    return (
      <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
        <DialogTitle>Build a test patient -- Rule checks</DialogTitle>
        <DialogContent>
          <Alert severity="info">
            Build patients for rule checks inside the guideline editor. Open
            the rule you want to test, then use Build a patient there. That
            screen lets you snapshot which rules should fire so the library
            can replay them later.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Close</Button>
        </DialogActions>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Build a test patient</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            We will save an empty test patient with a "test_" prefix. After
            that you can attach the part of the AI you want to check (notes,
            patient story or SBAR handover).
          </Typography>

          <TextField
            select
            label="Part of AI"
            value={form.aspect}
            onChange={(event) =>
              setForm((prev) => ({
                ...prev,
                aspect: event.target.value as BuildableAspect,
              }))
            }
            helperText={ASPECT_HINT[form.aspect]}
            disabled={submitting}
            fullWidth
          >
            {BUILDABLE_ASPECTS.map((value) => (
              <MenuItem key={value} value={value}>
                {ASPECT_LABEL[value]}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Short name"
            placeholder="e.g. older man with cough"
            value={form.name}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, name: event.target.value }))
            }
            helperText='We will add a "test_" prefix automatically.'
            disabled={submitting}
            fullWidth
            required
          />

          <TextField
            label="What this patient is for (optional)"
            placeholder="One short line: what should the AI see?"
            value={form.description}
            onChange={(event) =>
              setForm((prev) => ({
                ...prev,
                description: event.target.value,
              }))
            }
            disabled={submitting}
            fullWidth
            multiline
            minRows={2}
          />

          <Box sx={{ display: "flex", gap: 2 }}>
            <TextField
              label="Age (years)"
              value={form.age}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, age: event.target.value }))
              }
              type="number"
              inputProps={{ min: 0, max: 130, step: 1 }}
              disabled={submitting}
              sx={{ flex: 1 }}
            />
            <TextField
              select
              label="Sex"
              value={form.sex}
              onChange={(event) =>
                setForm((prev) => ({
                  ...prev,
                  sex: event.target.value as FormState["sex"],
                }))
              }
              disabled={submitting}
              sx={{ flex: 1 }}
            >
              <MenuItem value="">Not set</MenuItem>
              <MenuItem value="female">Female</MenuItem>
              <MenuItem value="male">Male</MenuItem>
              <MenuItem value="other">Other</MenuItem>
            </TextField>
          </Box>

          {error ? (
            <Alert severity="error" onClose={() => setError(null)}>
              {error}
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
          onClick={handleSubmit}
          disabled={submitting || !form.name.trim()}
          startIcon={
            submitting ? <CircularProgress size={16} color="inherit" /> : null
          }
        >
          {submitting ? "Creating..." : "Create test patient"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
