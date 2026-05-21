/**
 * Create or edit an extraction validation scenario.
 *
 * Atlas trace:
 *   DI: DI-1B3B5375
 *   DO: DO-416BA91D
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { createScenario, getScenario, updateScenario } from "./api";
import {
  EMPTY_EXPECTED_ANALYSIS,
  EMPTY_EXPECTED_SBAR,
  normaliseExpectedAnalysis,
  normaliseExpectedSbar,
  serialiseExpectedAnalysis,
  serialiseExpectedSbar,
} from "./pipelinePlaceholderHelpers";
import {
  SEMANTIC_TAG_OPTIONS,
  arrayToCommaList,
  buildExpectedObservablesFromPhrases,
  buildExpectedStringsFromPhrases,
  buildObservableValueLookup,
  commaListToArray,
  isObservableEntityTag,
  linesToList,
  listToLines,
  toExpectedPhrases,
} from "./phraseHelpers";
import ScenarioPipelinePlaceholders from "./ScenarioPipelinePlaceholders";
import type {
  ExpectedAnalysis,
  ExpectedPhrase,
  ExpectedSbar,
  ScenarioWritePayload,
} from "./types";

interface Props {
  open: boolean;
  mode: "create" | "edit";
  caseId?: string | null;
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  caseId: string;
  site: string;
  format: string;
  markdownBody: string;
  phrases: ExpectedPhrase[];
  mustNotExtract: string;
  phraseClasses: string;
  difficulty: string;
  notes: string;
  expectedAnalysis: ExpectedAnalysis;
  expectedSbar: ExpectedSbar;
}

const EMPTY_FORM: FormState = {
  caseId: "",
  site: "",
  format: "",
  markdownBody: "",
  phrases: [{ text: "", semantic_tag: "finding" }],
  mustNotExtract: "",
  phraseClasses: "",
  difficulty: "",
  notes: "",
  expectedAnalysis: { ...EMPTY_EXPECTED_ANALYSIS },
  expectedSbar: { ...EMPTY_EXPECTED_SBAR },
};

function buildPayload(
  form: FormState,
  extraPayload: Pick<
    ScenarioWritePayload,
    "synthetic_patient" | "blood_results" | "source_template_markdown" | "schema_version"
  >,
): ScenarioWritePayload {
  return {
    site: form.site.trim(),
    format: form.format.trim(),
    markdown_body: form.markdownBody.trim(),
    expected_strings: buildExpectedStringsFromPhrases(form.phrases),
    expected_observables: buildExpectedObservablesFromPhrases(form.phrases),
    expected_analysis: serialiseExpectedAnalysis(form.expectedAnalysis),
    expected_sbar: serialiseExpectedSbar(form.expectedSbar),
    must_not_extract: linesToList(form.mustNotExtract),
    phrase_classes: commaListToArray(form.phraseClasses),
    difficulty: commaListToArray(form.difficulty),
    notes_for_clinician_review: form.notes.trim() || null,
    ...extraPayload,
  };
}

function PhraseRows({
  phrases,
  onChange,
}: {
  phrases: ExpectedPhrase[];
  onChange: (next: ExpectedPhrase[]) => void;
}) {
  const updateRow = (index: number, patch: Partial<ExpectedPhrase>) => {
    onChange(
      phrases.map((row, i) => {
        if (i !== index) return row;
        const next = { ...row, ...patch };
        if (patch.semantic_tag && !isObservableEntityTag(patch.semantic_tag)) {
          delete next.value;
          delete next.unit;
        }
        if (patch.semantic_tag && isObservableEntityTag(patch.semantic_tag)) {
          next.value = next.value ?? "";
          next.unit = next.unit ?? "";
        }
        return next;
      }),
    );
  };

  const removeRow = (index: number) => {
    if (phrases.length <= 1) {
      onChange([{ text: "", semantic_tag: "finding" }]);
      return;
    }
    onChange(phrases.filter((_, i) => i !== index));
  };

  return (
    <Stack spacing={1}>
      {phrases.map((row, index) => {
        const showObservableFields = isObservableEntityTag(row.semantic_tag);
        return (
          <Stack key={index} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="flex-start">
            <TextField
              label={`Expected phrase ${index + 1}`}
              value={row.text}
              onChange={(e) => updateRow(index, { text: e.target.value })}
              fullWidth
              size="small"
              sx={{ flex: 1, minWidth: 0 }}
              inputProps={{ "data-testid": `expected-phrase-input-${index}` }}
            />
            <TextField
              select
              label="Tag"
              value={row.semantic_tag}
              onChange={(e) => updateRow(index, { semantic_tag: e.target.value })}
              size="small"
              sx={{ minWidth: 150, flexShrink: 0 }}
              inputProps={{ "data-testid": `expected-phrase-tag-${index}` }}
            >
              {SEMANTIC_TAG_OPTIONS.map((tag) => (
                <MenuItem key={tag} value={tag}>
                  {tag.replace(/_/g, " ")}
                </MenuItem>
              ))}
            </TextField>
            {showObservableFields ? (
              <>
                <TextField
                  label="Value"
                  value={row.value ?? ""}
                  onChange={(e) => updateRow(index, { value: e.target.value })}
                  size="small"
                  sx={{ width: { xs: "100%", sm: 110 }, flexShrink: 0 }}
                  inputProps={{ "data-testid": `expected-phrase-value-${index}` }}
                />
                <TextField
                  label="Unit"
                  value={row.unit ?? ""}
                  onChange={(e) => updateRow(index, { unit: e.target.value })}
                  size="small"
                  sx={{ width: { xs: "100%", sm: 120 }, flexShrink: 0 }}
                  inputProps={{ "data-testid": `expected-phrase-unit-${index}` }}
                />
              </>
            ) : null}
            <TextField
              label="SNOMED ID"
              value={row.concept_id ?? ""}
              onChange={(e) => updateRow(index, { concept_id: e.target.value })}
              size="small"
              sx={{ width: { xs: "100%", sm: 120 }, flexShrink: 0 }}
              placeholder="Optional"
              inputProps={{ "data-testid": `expected-phrase-concept-id-${index}` }}
            />
            <TextField
              label="Preferred term"
              value={row.preferred_term ?? ""}
              onChange={(e) => updateRow(index, { preferred_term: e.target.value })}
              size="small"
              sx={{ width: { xs: "100%", sm: 180 }, flexShrink: 0 }}
              placeholder="Optional"
              inputProps={{ "data-testid": `expected-phrase-preferred-term-${index}` }}
            />
            <IconButton
              aria-label={`Remove expected phrase ${index + 1}`}
              onClick={() => removeRow(index)}
              size="small"
              sx={{ alignSelf: { xs: "flex-start", sm: "center" }, flexShrink: 0 }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Stack>
        );
      })}
      <Button
        size="small"
        startIcon={<AddIcon fontSize="small" />}
        onClick={() => onChange([...phrases, { text: "", semantic_tag: "finding" }])}
        data-testid="add-expected-phrase"
      >
        Add phrase
      </Button>
    </Stack>
  );
}

export default function ScenarioEditorDialog({
  open,
  mode,
  caseId,
  onClose,
  onSaved,
}: Props) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extraPayload, setExtraPayload] = useState<
    Pick<
      ScenarioWritePayload,
      "synthetic_patient" | "blood_results" | "source_template_markdown" | "schema_version"
    >
  >({});

  useEffect(() => {
    if (!open) return;
    setError(null);
    if (mode === "create") {
      setForm(EMPTY_FORM);
      setExtraPayload({});
      return;
    }
    if (!caseId) return;
    setLoading(true);
    getScenario(caseId)
      .then((detail) => {
        const valueLookup = buildObservableValueLookup(
          detail.expected_observables,
          detail.blood_results,
        );
        setForm({
          caseId: detail.case_id,
          site: detail.site,
          format: detail.format,
          markdownBody: detail.markdown_body,
          phrases: toExpectedPhrases(detail.expected_strings, valueLookup),
          mustNotExtract: listToLines(detail.must_not_extract),
          phraseClasses: arrayToCommaList(detail.phrase_classes),
          difficulty: arrayToCommaList(detail.difficulty),
          notes: detail.notes_for_clinician_review ?? "",
          expectedAnalysis: normaliseExpectedAnalysis(detail.expected_analysis),
          expectedSbar: normaliseExpectedSbar(detail.expected_sbar),
        });
        setExtraPayload({
          synthetic_patient: detail.synthetic_patient,
          blood_results: detail.blood_results,
          source_template_markdown: detail.source_template_markdown,
          schema_version: detail.schema_version,
        });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Could not load this scenario.");
      })
      .finally(() => setLoading(false));
  }, [open, mode, caseId]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload(form, extraPayload);
      if (mode === "create") {
        if (!form.caseId.trim()) {
          throw new Error("Case ID is required.");
        }
        await createScenario({ ...payload, case_id: form.caseId.trim() });
      } else if (caseId) {
        await updateScenario(caseId, payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this scenario.");
    } finally {
      setSaving(false);
    }
  }, [caseId, extraPayload, form, mode, onClose, onSaved]);

  const title = mode === "create" ? "New extraction scenario" : `Edit ${caseId ?? "scenario"}`;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="xl"
      scroll="paper"
      data-testid="scenario-editor-dialog"
    >
      <DialogTitle>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {title}
          </Typography>
          <IconButton aria-label="Close editor dialog" onClick={onClose} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        ) : null}
        {loading ? (
          <Typography variant="body2" color="text.secondary">
            Loading scenario...
          </Typography>
        ) : (
          <Stack spacing={2}>
            {mode === "create" ? (
              <TextField
                label="Case ID"
                value={form.caseId}
                onChange={(e) => setForm((prev) => ({ ...prev, caseId: e.target.value }))}
                helperText="Lowercase letters, digits, and underscores. Example: lung_letter_002"
                fullWidth
                required
                inputProps={{ "data-testid": "scenario-case-id-input" }}
              />
            ) : null}
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Site"
                value={form.site}
                onChange={(e) => setForm((prev) => ({ ...prev, site: e.target.value }))}
                fullWidth
                required
                inputProps={{ "data-testid": "scenario-site-input" }}
              />
              <TextField
                label="Format"
                value={form.format}
                onChange={(e) => setForm((prev) => ({ ...prev, format: e.target.value }))}
                fullWidth
                required
                inputProps={{ "data-testid": "scenario-format-input" }}
              />
            </Stack>
            <TextField
              label="Clinical document markdown"
              value={form.markdownBody}
              onChange={(e) => setForm((prev) => ({ ...prev, markdownBody: e.target.value }))}
              fullWidth
              required
              multiline
              minRows={8}
              inputProps={{ "data-testid": "scenario-markdown-input" }}
            />
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Expected phrases
              </Typography>
              <PhraseRows
                phrases={form.phrases}
                onChange={(phrases) => setForm((prev) => ({ ...prev, phrases }))}
              />
            </Box>
            <TextField
              label="Must not extract"
              value={form.mustNotExtract}
              onChange={(e) => setForm((prev) => ({ ...prev, mustNotExtract: e.target.value }))}
              fullWidth
              multiline
              minRows={3}
              helperText="One phrase per line."
              inputProps={{ "data-testid": "scenario-must-not-input" }}
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Phrase classes"
                value={form.phraseClasses}
                onChange={(e) => setForm((prev) => ({ ...prev, phraseClasses: e.target.value }))}
                fullWidth
                helperText="Comma-separated labels."
              />
              <TextField
                label="Difficulty"
                value={form.difficulty}
                onChange={(e) => setForm((prev) => ({ ...prev, difficulty: e.target.value }))}
                fullWidth
                helperText="Comma-separated labels."
              />
            </Stack>
            <TextField
              label="Notes for clinician review"
              value={form.notes}
              onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
              fullWidth
              multiline
              minRows={2}
            />
            <ScenarioPipelinePlaceholders
              expectedAnalysis={form.expectedAnalysis}
              expectedSbar={form.expectedSbar}
              onAnalysisChange={(expectedAnalysis) =>
                setForm((prev) => ({ ...prev, expectedAnalysis }))
              }
              onSbarChange={(expectedSbar) =>
                setForm((prev) => ({ ...prev, expectedSbar }))
              }
            />
            {mode === "edit" ? (
              <Alert severity="info">
                Saving changes resets approval status to awaiting review.
              </Alert>
            ) : null}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={saving || loading}
          data-testid="scenario-save-button"
        >
          {saving ? "Saving..." : mode === "create" ? "Create scenario" : "Save changes"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
