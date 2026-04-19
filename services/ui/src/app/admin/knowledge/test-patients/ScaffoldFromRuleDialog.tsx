"use client";

/**
 * Scaffold a test patient from one guideline rule (AI-assisted).
 *
 * Flow 1 of the AI-assisted authoring story for the Knowledge >
 * Test Patients tab. The reviewer:
 *   1. Picks the part of AI to test against (default: SBAR handover).
 *   2. Picks ONE rule from the existing tree picker dialog.
 *   3. Clicks "Scaffold". The backend asks Haiku to draft 1-2 plain
 *      English UK GP notes that mention every trigger SNOMED in the
 *      rule, plus a plausible age and sex inside any APPLIES_TO
 *      constraints. The expected SBAR (when the aspect is SBAR) is
 *      filled in deterministically from the rule, NOT from the LLM,
 *      so the test does not check the AI against itself.
 *   4. On success the editor drawer opens with the new patient pre
 *      populated -- the reviewer reviews, tweaks and saves.
 *
 * Audience standard (see .cursor/rules/health-literacy.mdc):
 *   - UK reading age 11.
 *   - "Aspect" -> "Part of AI"; "Rule" -> "Guideline rule".
 *   - Errors say what failed AND what to do next (retry, fix the
 *     rule, or fall back to Build a patient).
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
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";

import { ASPECT_HINT, ASPECT_LABEL, type AspectFilter } from "./types";
import { listGuidanceRules, scaffoldFromRule } from "./api";
import type { GuidanceRulePickerEntry } from "./types";
import RulePickerDialog from "./editor/RulePickerDialog";

type ScaffoldAspect = "nlp" | "episodes" | "summarisation";

const SCAFFOLDABLE_ASPECTS: ScaffoldAspect[] = [
  "summarisation",
  "episodes",
  "nlp",
];

interface ScaffoldFromRuleDialogProps {
  open: boolean;
  initialAspect?: AspectFilter;
  onClose: () => void;
  onScaffolded: (newPatientId: string) => void;
  /**
   * When set, the rule picker is hidden and the dialog scaffolds
   * against this rule directly. Used by the rule editor's "Try it on
   * real patients" panel so the reviewer cannot accidentally pick a
   * different rule from the one they are editing.
   *
   * The `lockedRuleHint` is a short plain-English label (the
   * verbatim NICE recommendation, the rule name, etc.) shown in the
   * locked preview so the reviewer can confirm what the AI will
   * draft against without scrolling back through the picker.
   */
  lockedRuleId?: string;
  lockedRuleHint?: string;
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

export default function ScaffoldFromRuleDialog({
  open,
  initialAspect,
  onClose,
  onScaffolded,
  lockedRuleId,
  lockedRuleHint,
}: ScaffoldFromRuleDialogProps) {
  const [aspect, setAspect] = useState<ScaffoldAspect>(
    pickInitialAspect(initialAspect),
  );
  const [pickedRuleId, setPickedRuleId] = useState<string | null>(
    lockedRuleId ?? null,
  );
  const [rules, setRules] = useState<GuidanceRulePickerEntry[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setAspect(pickInitialAspect(initialAspect));
    setPickedRuleId(lockedRuleId ?? null);
    setError(null);
    setSubmitting(false);
    setRulesLoading(true);
    setRulesError(null);
    let cancelled = false;
    listGuidanceRules({ limit: 500 })
      .then((rows) => {
        if (cancelled) return;
        setRules(rows);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setRulesError(
          exc instanceof Error
            ? exc.message
            : "Could not load the rule list.",
        );
      })
      .finally(() => {
        if (!cancelled) setRulesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, initialAspect, lockedRuleId]);

  const pickedRule =
    pickedRuleId !== null
      ? rules.find((r) => r.rule_id === pickedRuleId) ?? null
      : null;

  const handleScaffold = async () => {
    if (!pickedRuleId) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await scaffoldFromRule({
        rule_id: pickedRuleId,
        aspect,
      });
      onScaffolded(result.patient_id);
      onClose();
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Scaffold failed. Try again, or use Build a patient instead.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={1}>
            <AutoAwesomeOutlinedIcon fontSize="small" />
            <Box>Scaffold a test patient from a rule</Box>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Pick a guideline rule -- the AI drafts a short patient note
            that should make it fire. You review and save.
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

            <Stack spacing={1}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Guideline rule
                </Typography>
                {rulesLoading ? (
                  <CircularProgress size={14} />
                ) : (
                  <Chip
                    size="small"
                    label={
                      lockedRuleId
                        ? "Locked to the rule you are editing"
                        : `${rules.length} loaded`
                    }
                    variant="outlined"
                    color={lockedRuleId ? "primary" : "default"}
                  />
                )}
                <Box sx={{ flex: 1 }} />
                {lockedRuleId ? null : (
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<AccountTreeOutlinedIcon />}
                    onClick={() => setPickerOpen(true)}
                    disabled={
                      submitting || (rulesLoading && rules.length === 0)
                    }
                  >
                    {pickedRule ? "Change rule" : "Pick a rule"}
                  </Button>
                )}
              </Stack>
              {rulesError ? (
                <Alert severity="warning">{rulesError}</Alert>
              ) : null}
              {!pickedRule && lockedRuleId ? (
                <Box
                  sx={{
                    p: 1.5,
                    border: 1,
                    borderColor: "primary.200",
                    borderRadius: 1,
                    bgcolor: "primary.50",
                  }}
                  data-testid="picked-rule-preview"
                >
                  <Stack spacing={0.5}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {lockedRuleHint || lockedRuleId}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Loading the rest of the rule details...
                    </Typography>
                  </Stack>
                </Box>
              ) : null}
              {pickedRule ? (
                <Box
                  sx={{
                    p: 1.5,
                    border: 1,
                    borderColor: "divider",
                    borderRadius: 1,
                    bgcolor: "background.default",
                  }}
                  data-testid="picked-rule-preview"
                >
                  <Stack spacing={0.75}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {pickedRule.display_label}
                    </Typography>
                    <Stack
                      direction="row"
                      spacing={0.75}
                      sx={{ flexWrap: "wrap", rowGap: 0.5, alignItems: "center" }}
                    >
                      {pickedRule.action_priority ? (
                        <Chip
                          size="small"
                          label={pickedRule.action_priority.toUpperCase()}
                          color={
                            pickedRule.action_priority.toLowerCase() === "2ww"
                              ? "error"
                              : pickedRule.action_priority.toLowerCase() ===
                                "urgent"
                              ? "warning"
                              : "default"
                          }
                          variant="outlined"
                        />
                      ) : null}
                      {pickedRule.guideline_title ? (
                        <Typography
                          variant="caption"
                          color="text.secondary"
                        >
                          {pickedRule.guideline_title}
                        </Typography>
                      ) : null}
                      {pickedRule.chapter_title ? (
                        <Typography
                          variant="caption"
                          color="text.secondary"
                        >
                          -- {pickedRule.chapter_title}
                        </Typography>
                      ) : null}
                    </Stack>
                    {pickedRule.trigger_terms.length > 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        Triggers the AI must mention:{" "}
                        {pickedRule.trigger_terms.join(", ")}
                      </Typography>
                    ) : null}
                  </Stack>
                </Box>
              ) : (
                <Box
                  sx={{
                    p: 1.5,
                    border: 1,
                    borderStyle: "dashed",
                    borderColor: "divider",
                    borderRadius: 1,
                    color: "text.secondary",
                  }}
                >
                  <Typography variant="caption">
                    No rule picked yet. Click "Pick a rule" to open the
                    guideline tree.
                  </Typography>
                </Box>
              )}
            </Stack>

            <Alert severity="info" sx={{ mt: 1 }}>
              The AI drafts the patient notes. The expected SBAR
              answer comes straight from the rule -- the AI never
              writes its own ground truth. You can edit everything
              before saving.
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
            disabled={!pickedRuleId || submitting}
            startIcon={
              submitting ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <AutoAwesomeOutlinedIcon />
              )
            }
          >
            {submitting ? "Scaffolding..." : "Scaffold"}
          </Button>
        </DialogActions>
      </Dialog>

      {lockedRuleId ? null : (
        <RulePickerDialog
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          onApply={(ids) => {
            setPickedRuleId(ids[ids.length - 1] ?? null);
            setPickerOpen(false);
          }}
          selectedRuleIds={pickedRuleId ? [pickedRuleId] : []}
          rules={rules}
          loading={rulesLoading}
          error={rulesError}
        />
      )}
    </>
  );
}
