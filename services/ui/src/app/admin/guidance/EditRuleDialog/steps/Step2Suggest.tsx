/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Step 2 -- "What should the system suggest?"
 *
 * Three controls stacked vertically:
 *   - The recommended-procedures panel (one or more SNOMED chips, each
 *     with its own strength dropdown -- offer / consider / refer /
 *     safety net / do not offer).
 *   - The short rule name shown in the review queue.
 *   - The fallback-rule switch.
 *
 * State lives in the parent dialog. This file is presentational so it
 * can be swapped out, snapshot-tested, and reused from a future
 * "promote to plan-definition" workflow.
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510.
 */

import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import ActionsPanel from "../ActionsPanel";
import PriorityPanel from "../PriorityPanel";
import { STEP_HELPERS, STEP_TITLES } from "../copy";
import type { InvestigationPolicy, RuleAction, RulePriority } from "../types";

interface Props {
  name: string;
  onNameChange: (next: string) => void;
  priority: RulePriority;
  dueDays: number | null;
  onPriorityChange: (next: RulePriority) => void;
  onDueDaysChange: (next: number | null) => void;
  investigationPolicy?: InvestigationPolicy | "";
  onInvestigationPolicyChange?: (next: InvestigationPolicy | "") => void;
  actions: RuleAction[];
  selectedActionIndex: number | null;
  onSelectAction: (index: number) => void;
  onActionStrengthChange: (index: number, strength: string) => void;
  onRemoveAction: (index: number) => void;
  onAddAction: () => void;
  onAddFallback: (afterIndex: number) => void;
  onAddOrAlternative: (afterIndex: number) => void;
  isDefault: boolean;
  onIsDefaultChange: (next: boolean) => void;
}

export default function Step2Suggest({
  name,
  onNameChange,
  priority,
  dueDays,
  onPriorityChange,
  onDueDaysChange,
  investigationPolicy,
  onInvestigationPolicyChange,
  actions,
  selectedActionIndex,
  onSelectAction,
  onActionStrengthChange,
  onRemoveAction,
  onAddAction,
  onAddFallback,
  onAddOrAlternative,
  isDefault,
  onIsDefaultChange,
}: Props) {
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <Box>
        <Typography
          variant="h6"
          component="h3"
          sx={{ fontWeight: 700, fontSize: "1.05rem" }}
        >
          {STEP_TITLES.suggest}
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ lineHeight: 1.5, mt: 0.5 }}
        >
          {STEP_HELPERS.suggest}
        </Typography>
      </Box>

      <PriorityPanel
        priority={priority}
        dueDays={dueDays}
        onPriorityChange={onPriorityChange}
        onDueDaysChange={onDueDaysChange}
        investigationPolicy={investigationPolicy}
        onInvestigationPolicyChange={onInvestigationPolicyChange}
      />

      <ActionsPanel
        actions={actions}
        selectedIndex={selectedActionIndex}
        onSelectAction={onSelectAction}
        onStrengthChange={onActionStrengthChange}
        onRemoveAction={onRemoveAction}
        onAddAction={onAddAction}
        onAddFallback={onAddFallback}
        onAddOrAlternative={onAddOrAlternative}
      />

      <TextField
        size="small"
        label="Short name for this rule"
        helperText="Shown to clinicians in the review queue."
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        inputProps={{
          "aria-label": "Short name for this rule",
          maxLength: 200,
        }}
      />

      <Tooltip
        title="Use this for narrative recommendations that apply when no more specific rule has already fired for this patient."
        placement="bottom-start"
      >
        <FormControlLabel
          control={
            <Switch
              checked={isDefault}
              onChange={(e) => onIsDefaultChange(e.target.checked)}
              inputProps={{ "aria-label": "Mark as fallback rule" }}
              size="small"
            />
          }
          label={
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
                Fallback rule
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.3 }}>
                Only fires if no other rule in this guideline matched.
              </Typography>
            </Box>
          }
          sx={{ alignItems: "flex-start", mt: 0.5, ml: 0 }}
        />
      </Tooltip>
    </Stack>
  );
}
