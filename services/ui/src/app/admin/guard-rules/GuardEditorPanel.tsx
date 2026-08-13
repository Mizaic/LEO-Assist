/**
 * Guard rule editor. Built-in rules stay read-only.
 */
"use client";

import Stack from "@mui/material/Stack";

import RuleEditor, { type RuleFormValues } from "@/components/workbench/RuleEditor";

import { humanizePattern } from "./humanizePattern";
import type { NerGuardRule } from "./types";

interface GuardEditorPanelProps {
  selectedRule: NerGuardRule | null;
  addingNew: boolean;
  ruleTypeOptions: Array<{ value: string; label: string }>;
  saving: boolean;
  onSave: (values: RuleFormValues) => Promise<void>;
  onCancel: () => void;
}

export default function GuardEditorPanel({
  selectedRule,
  addingNew,
  ruleTypeOptions,
  saving,
  onSave,
  onCancel,
}: GuardEditorPanelProps) {
  const readOnly = selectedRule?.source === "builtin" || selectedRule?.readonly === true;
  return (
    <Stack spacing={2}>
      <RuleEditor
        key={selectedRule?.rule_id ?? "new"}
        title={
          addingNew
            ? "Add guard rule"
            : selectedRule?.summary || humanizePattern(selectedRule?.pattern ?? "")
        }
        initialValues={selectedRule ?? null}
        ruleTypeOptions={ruleTypeOptions}
        onSave={onSave}
        onCancel={onCancel}
        saving={saving}
        readOnly={readOnly}
        ruleId={selectedRule?.source === "builtin" ? undefined : selectedRule?.rule_id}
        ruleFamily={selectedRule?.family}
      />
    </Stack>
  );
}
