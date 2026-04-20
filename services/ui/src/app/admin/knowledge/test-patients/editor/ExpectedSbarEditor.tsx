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
 * Expected SBAR editor -- summarisation aspect only.
 *
 * Lets a reviewer pin down what a "good" SBAR transcript should
 * look like for this patient: the four sections of free text, the
 * phrases that MUST appear, the phrases that MUST NOT appear, the
 * matched rule IDs the recommendation is based on, and the action
 * priority (e.g. "2ww") the recommendation must drive.
 *
 * Audience standard (UK reading age 11): the labels avoid jargon
 * ("Situation" / "Background" instead of "S section / B section")
 * and explain the purpose of each list in one short sentence.
 *
 * The arrays (matched rules, phrases) are entered as comma- or
 * newline-separated strings and split on save -- each list rejects
 * blanks so a stray newline cannot create empty assertion strings.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";

import { listGuidanceRules } from "../api";
import type { EditorExpectedSbar, GuidanceRulePickerEntry } from "../types";
import RulePickerDialog from "./RulePickerDialog";

interface ExpectedSbarEditorProps {
  value: EditorExpectedSbar;
  onChange: (next: EditorExpectedSbar) => void;
  disabled?: boolean;
}

function listToText(values: string[] | null | undefined): string {
  if (!values || values.length === 0) return "";
  return values.join("\n");
}

function textToList(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

// LONG FUNCTION: SBAR has 4 markdown sections + 4 list fields.
// All controlled-input plumbing in one place keeps the form atomic.
export default function ExpectedSbarEditor({
  value,
  onChange,
  disabled = false,
}: ExpectedSbarEditorProps) {
  const update = useCallback(
    (patch: Partial<EditorExpectedSbar>) => {
      onChange({ ...value, ...patch });
    },
    [value, onChange],
  );

  // Pull the live rule library on mount so the picker shows real rule
  // ids, not free text. Failure here must not break the editor: if the
  // lookup is unavailable (network blip, no rules compiled yet) the
  // reviewer still sees the rules already saved on this patient as
  // free-form chips so nothing is lost.
  const [rules, setRules] = useState<GuidanceRulePickerEntry[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRulesLoading(true);
    setRulesError(null);
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
  }, []);

  const ruleById = useMemo(() => {
    const map = new Map<string, GuidanceRulePickerEntry>();
    for (const rule of rules) {
      map.set(rule.rule_id, rule);
    }
    return map;
  }, [rules]);

  const selectedRules = useMemo<GuidanceRulePickerEntry[]>(() => {
    const ids = value.matched_rule_ids ?? [];
    return ids.map(
      (id) =>
        ruleById.get(id) ?? {
          rule_id: id,
          status: null,
          name: null,
          display_label: id,
          recommendation_text: null,
          chapter_title: null,
          action_priority: null,
          trigger_terms: [],
          guideline_id: null,
          guideline_title: null,
        },
    );
  }, [value.matched_rule_ids, ruleById]);

  const [pickerOpen, setPickerOpen] = useState(false);

  const applyPickerSelection = useCallback(
    (ids: string[]) => {
      const deduped: string[] = [];
      for (const raw of ids) {
        const id = (raw ?? "").trim();
        if (id && !deduped.includes(id)) deduped.push(id);
      }
      update({ matched_rule_ids: deduped });
      setPickerOpen(false);
    },
    [update],
  );

  const removeRule = useCallback(
    (ruleId: string) => {
      const next = (value.matched_rule_ids ?? []).filter(
        (id) => id !== ruleId,
      );
      update({ matched_rule_ids: next });
    },
    [value.matched_rule_ids, update],
  );

  return (
    <Stack spacing={2} data-testid="expected-sbar-editor">
      <Typography variant="subtitle2">Expected SBAR transcript</Typography>
      <Typography variant="body2" color="text.secondary">
        This is what a "good" SBAR handover should say for this patient.
        The check compares the AI's output against these four sections
        and the must-include / must-not-say lists below.
      </Typography>

      <TextField
        label="Situation"
        helperText="One short paragraph: who and why now."
        value={value.situation_md ?? ""}
        onChange={(event) => update({ situation_md: event.target.value })}
        disabled={disabled}
        multiline
        minRows={3}
        fullWidth
      />
      <TextField
        label="Background"
        helperText="The relevant history in bullet points."
        value={value.background_md ?? ""}
        onChange={(event) => update({ background_md: event.target.value })}
        disabled={disabled}
        multiline
        minRows={3}
        fullWidth
      />
      <TextField
        label="Recommendation"
        helperText="What the next step should be."
        value={value.recommendation_md ?? ""}
        onChange={(event) =>
          update({ recommendation_md: event.target.value })
        }
        disabled={disabled}
        multiline
        minRows={3}
        fullWidth
      />

      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
        <TextField
          label="Action priority"
          helperText="e.g. 2ww, urgent, routine."
          placeholder="2ww"
          value={value.expected_action_priority ?? ""}
          onChange={(event) =>
            update({
              expected_action_priority: event.target.value || null,
            })
          }
          disabled={disabled}
          sx={{ minWidth: 200 }}
        />

        <Stack
          spacing={1}
          sx={{ flex: 1, minWidth: 320 }}
          data-testid="matched-rule-ids-picker"
        >
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Rules that should fire
            </Typography>
            <Chip
              size="small"
              label={`${selectedRules.length} picked`}
              color={selectedRules.length > 0 ? "primary" : "default"}
              variant="outlined"
            />
            {rulesLoading ? (
              <CircularProgress size={14} sx={{ ml: 0.5 }} />
            ) : null}
            <Box sx={{ flex: 1 }} />
            <Button
              size="small"
              variant="outlined"
              startIcon={<AccountTreeOutlinedIcon />}
              onClick={() => setPickerOpen(true)}
              disabled={disabled}
            >
              Browse rules
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {rulesError
              ? `${rulesError} The Browse rules dialog will still open with what is loaded.`
              : "Open Browse rules to pick from the guideline tree."}
          </Typography>
          {selectedRules.length === 0 ? (
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
                No rules picked yet. Use Browse rules to choose from the
                guidelines, then tick the rules that should fire for this
                patient.
              </Typography>
            </Box>
          ) : (
            <Box
              sx={{
                display: "flex",
                flexWrap: "wrap",
                gap: 0.75,
                p: 1,
                border: 1,
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              {selectedRules.map((rule) => {
                const label = rule.display_label || rule.rule_id;
                const shortLabel =
                  label.length > 60 ? `${label.slice(0, 59)}...` : label;
                const tooltip = [
                  rule.guideline_title,
                  rule.chapter_title,
                  rule.display_label,
                  rule.action_priority
                    ? `Priority: ${rule.action_priority}`
                    : "",
                ]
                  .filter(Boolean)
                  .join(" -- ");
                return (
                  <Chip
                    key={rule.rule_id}
                    size="small"
                    label={shortLabel}
                    title={tooltip || rule.rule_id}
                    onDelete={
                      disabled ? undefined : () => removeRule(rule.rule_id)
                    }
                  />
                );
              })}
            </Box>
          )}
        </Stack>
      </Box>

      <RulePickerDialog
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onApply={applyPickerSelection}
        selectedRuleIds={value.matched_rule_ids ?? []}
        rules={rules}
        loading={rulesLoading}
        error={rulesError}
      />

      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
        <TextField
          label="Must-include phrases"
          helperText="One per line. The check fails if any are missing."
          value={listToText(value.required_phrases)}
          onChange={(event) =>
            update({ required_phrases: textToList(event.target.value) })
          }
          disabled={disabled}
          multiline
          minRows={3}
          sx={{ flex: 1, minWidth: 240 }}
        />
        <TextField
          label="Must-not-say phrases"
          helperText="One per line. The check fails if any appear."
          value={listToText(value.banned_phrases)}
          onChange={(event) =>
            update({ banned_phrases: textToList(event.target.value) })
          }
          disabled={disabled}
          multiline
          minRows={3}
          sx={{ flex: 1, minWidth: 240 }}
        />
      </Box>

      <TextField
        label="Reviewer notes"
        helperText="What should the reviewer focus on for this patient?"
        value={value.reviewer_focus ?? ""}
        onChange={(event) => update({ reviewer_focus: event.target.value })}
        disabled={disabled}
        multiline
        minRows={2}
        fullWidth
      />
    </Stack>
  );
}
