/**
 * The form wording behind a completeness rule, and a mark when a person
 * must check it.
 *
 * Atlas trace: DI-9BF69EC9, DO-F120628C, R-A3BD3AC7
 */
"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { CompletenessLogicGroup } from "./formSchemaTeach";

interface Props {
  group: CompletenessLogicGroup;
  onChange: (group: CompletenessLogicGroup) => void;
}

function targetLabel(leaf: CompletenessLogicGroup | null | undefined): string {
  if (!leaf?.section_id) return "";
  return leaf.item_pattern ? `${leaf.section_id}: ${leaf.item_pattern}` : leaf.section_id;
}

/** Taught sections and tick boxes this rule checks, in plain words. */
export function ruleTargets(group: CompletenessLogicGroup): string[] {
  const leaves = [group, ...(group.members ?? []), group.if_group, group.then_group];
  return leaves.map(targetLabel).filter(Boolean);
}

export function FormSchemaRuleEvidence({ group, onChange }: Props) {
  const targets = ruleTargets(group);
  if (!group.evidence && !group.needs_review && !targets.length) return null;
  return (
    <Stack spacing={0.5} sx={{ mt: 0.75 }} data-testid="completeness-rule-evidence">
      {group.evidence ? (
        <Typography variant="caption" color="text.secondary">
          The form says: &quot;{group.evidence}&quot;
        </Typography>
      ) : null}
      {targets.length ? (
        <Typography variant="caption" color="text.secondary">
          Checks: {targets.join(", ")}
        </Typography>
      ) : null}
      {group.needs_review ? (
        <Alert
          severity="info"
          sx={{ py: 0.25 }}
          data-testid="completeness-needs-review"
          action={
            <Button size="small" onClick={() => onChange({ ...group, needs_review: false })}>
              Mark as checked
            </Button>
          }
        >
          <strong>Check this rule</strong>
          <br />
          We could not find form wording that makes this required, so it is
          optional for now. Change the rule type if the form needs it.
        </Alert>
      ) : null}
    </Stack>
  );
}
