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
 * Step 2 -- "What should the system suggest?"
 *
 * Three controls in a responsive 2-column grid:
 *   - The action SNOMED chip (procedure suggested when the rule fires).
 *   - The strength dropdown (offer / consider / refer / safety net / do not offer).
 *   - The short rule name shown in the review queue.
 *
 * State lives in the parent dialog. This file is presentational so it
 * can be swapped out, snapshot-tested, and reused from a future
 * "promote to plan-definition" workflow.
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510.
 */

import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import ActionPanel from "../ActionPanel";
import { STEP_HELPERS, STEP_TITLES, STRENGTH_LABELS } from "../copy";
import type { LogicCriterion } from "../types";

interface Props {
  name: string;
  onNameChange: (next: string) => void;
  strength: string;
  onStrengthChange: (next: string) => void;
  action: LogicCriterion | null;
  isActionSelected: boolean;
  onSelectAction: () => void;
  isDefault: boolean;
  onIsDefaultChange: (next: boolean) => void;
}

export default function Step2Suggest({
  name,
  onNameChange,
  strength,
  onStrengthChange,
  action,
  isActionSelected,
  onSelectAction,
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

      <ActionPanel
        action={action}
        isSelected={isActionSelected}
        onSelect={onSelectAction}
      />

      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        alignItems="stretch"
      >
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
          sx={{ flex: 2 }}
        />
        <Box sx={{ flex: 1, minWidth: 220 }}>
          <Typography
            variant="caption"
            component="label"
            htmlFor="edit-rule-strength"
            sx={{
              display: "block",
              color: "text.secondary",
              mb: 0.25,
              ml: 0.5,
            }}
          >
            What should the system suggest?
          </Typography>
          <Select
            id="edit-rule-strength"
            size="small"
            fullWidth
            value={strength}
            onChange={(e) => onStrengthChange(String(e.target.value))}
            inputProps={{ "aria-label": "What should the system suggest" }}
          >
            {STRENGTH_LABELS.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </Box>
      </Stack>

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
