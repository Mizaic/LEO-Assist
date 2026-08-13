/**
 * RuleEditor -- inline drawer panel for creating or editing a guard rule.
 *
 * Shows a minimal form for the common guard rule fields (pattern, rule_type,
 * active). Guards with extra shape-specific fields should extend via the
 * extraFields prop.
 *
 * Includes a RuleImpactBanner placeholder that previews how many pipeline
 * runs would be affected by this change (P2-J).
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import RuleImpactBanner from "./RuleImpactBanner";
import RuleHistoryPanel from "./RuleHistoryPanel";

export interface RuleFormValues {
  pattern: string;
  rule_type: string;
  active: boolean;
  [key: string]: unknown;
}

export interface RuleEditorProps {
  /** Title shown at top of the editor pane. */
  title?: string;
  /** Current rule values to populate the form. Pass null for a new rule. */
  initialValues?: Partial<RuleFormValues> | null;
  /** Available rule_type options for the selector. */
  ruleTypeOptions: Array<{ value: string; label: string }>;
  /** Called when the user clicks Save with valid values. */
  onSave: (values: RuleFormValues) => void | Promise<void>;
  /** Called when the user clicks Cancel. */
  onCancel?: () => void;
  /** Extra form fields rendered below the standard ones. */
  extraFields?: React.ReactNode;
  /** When true, the Save button shows a loading state. */
  saving?: boolean;
  /** Existing rule ID -- enables impact preview and version history. */
  ruleId?: string;
  /** Guard family for impact scoping (e.g. "scope_guard"). */
  ruleFamily?: string;
  /** When true, fields are locked and Save is hidden (built-in rules). */
  readOnly?: boolean;
  /** Called after a version restore so the parent can reload the rule. */
  onReverted?: () => void;
}

export default function RuleEditor({
  title = "Edit rule",
  initialValues,
  ruleTypeOptions,
  onSave,
  onCancel,
  extraFields,
  saving = false,
  ruleId,
  ruleFamily,
  onReverted,
  readOnly = false,
}: RuleEditorProps) {
  const [pattern, setPattern] = useState(initialValues?.pattern ?? "");
  const [rule_type, setRuleType] = useState(
    initialValues?.rule_type ?? (ruleTypeOptions[0]?.value ?? ""),
  );
  const [active, setActive] = useState(initialValues?.active ?? true);

  async function handleSave() {
    await onSave({ pattern, rule_type, active });
  }

  return (
    <Paper
      variant="outlined"
      sx={{ p: 3, borderRadius: "12px", display: "flex", flexDirection: "column", gap: 2.5 }}
    >
      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
        {title}
      </Typography>

      {readOnly && (
        <Typography variant="body2" color="text.secondary">
          This rule ships with LEO. Add a new rule to extend it. You cannot edit or turn off a built-in rule here.
        </Typography>
      )}

      <TextField
        label="Pattern"
        value={pattern}
        onChange={(e) => setPattern(e.target.value)}
        size="small"
        fullWidth
        disabled={readOnly}
        helperText="Python regex fragment (re.IGNORECASE applied automatically)."
        multiline
        minRows={2}
      />

      <TextField
        select
        label="Rule type"
        value={rule_type}
        onChange={(e) => setRuleType(e.target.value)}
        size="small"
        fullWidth
        disabled={readOnly}
      >
        {ruleTypeOptions.map((opt) => (
          <MenuItem key={opt.value} value={opt.value}>
            {opt.label}
          </MenuItem>
        ))}
      </TextField>

      {extraFields}

      <FormControlLabel
        control={
          <Switch
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
            color="primary"
            disabled={readOnly}
          />
        }
        label="Active"
      />

      {!readOnly && (
        <RuleImpactBanner
          rule_id={ruleId}
          pattern={pattern}
          family={ruleFamily}
        />
      )}

      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end", pt: 1 }}>
        {onCancel && (
          <Button variant="text" onClick={onCancel} disabled={saving}>
            {readOnly ? "Close" : "Cancel"}
          </Button>
        )}
        {!readOnly && (
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving || !pattern.trim()}
            data-testid="rule-editor-save-btn"
          >
            {saving ? "Saving..." : "Save rule"}
          </Button>
        )}
      </Box>

      {!readOnly && ruleId && (
        <>
          <Divider />
          <RuleHistoryPanel rule_id={ruleId} onReverted={onReverted} />
        </>
      )}
    </Paper>
  );
}
