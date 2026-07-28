/**
 * Atlas trace:
 *   DI: (new DI for clinical priority editing -- see plan)
 *   DO: (new DO for clinical priority editing -- see plan)
 */
"use client";

/**
 * Editable clinical priority for a guidance rule -- immediate /
 * 2 week wait / urgent / routine, plus optional due-days.
 *
 * Priority is rule-level (shared across every recommended procedure
 * on the rule). Due-days is cleared and disabled when priority is
 * Routine, matching the backend RuleUpdates validator.
 */

import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { RULE_PRIORITIES, type RulePriority } from "./types";

interface Props {
  priority: RulePriority;
  dueDays: number | null;
  onPriorityChange: (next: RulePriority) => void;
  onDueDaysChange: (next: number | null) => void;
}

export default function PriorityPanel({
  priority,
  dueDays,
  onPriorityChange,
  onDueDaysChange,
}: Props) {
  const selectId = "edit-rule-priority";
  const dueDaysId = "edit-rule-due-days";
  const isRoutine = priority === "routine";

  return (
    <Box role="region" aria-label="How urgent is this referral">
      <Typography
        variant="overline"
        sx={{ display: "block", color: "text.secondary", letterSpacing: 0.5 }}
      >
        How urgent is this referral
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ lineHeight: 1.4, mb: 1 }}
      >
        This sets the clinical priority used in Assessment and SBAR.
        Pick Immediate for same-day specialist assessment, or 2 week wait
        for urgent suspected cancer pathways.
      </Typography>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        alignItems={{ xs: "stretch", sm: "flex-end" }}
      >
        <Box sx={{ minWidth: 260, flex: 1 }}>
          <Typography
            variant="caption"
            component="label"
            htmlFor={selectId}
            sx={{ display: "block", color: "text.secondary", mb: 0.25, ml: 0.5 }}
          >
            Priority
          </Typography>
          <Select
            id={selectId}
            size="small"
            fullWidth
            value={priority}
            onChange={(e) =>
              onPriorityChange(String(e.target.value) as RulePriority)
            }
            inputProps={{ "aria-label": "Clinical priority for this rule" }}
          >
            {RULE_PRIORITIES.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </Box>
        <Box sx={{ minWidth: 140, width: { xs: "100%", sm: 160 } }}>
          <TextField
            id={dueDaysId}
            size="small"
            fullWidth
            type="number"
            label="Due within (days)"
            value={isRoutine || dueDays == null ? "" : String(dueDays)}
            disabled={isRoutine}
            onChange={(e) => {
              const raw = e.target.value.trim();
              if (!raw) {
                onDueDaysChange(null);
                return;
              }
              const n = Number(raw);
              if (!Number.isFinite(n) || n < 0) return;
              onDueDaysChange(Math.floor(n));
            }}
            inputProps={{
              min: 0,
              step: 1,
              "aria-label": "Due within how many days",
            }}
            helperText={
              isRoutine ? "Not used for routine priority" : "Optional"
            }
            // MUI's default disabled helper (#9e9e9e on white) fails
            // WCAG 2.1 AA contrast; grey.600 keeps the "disabled" cue
            // while staying above 4.5:1.
            FormHelperTextProps={{
              sx: { "&.Mui-disabled": { color: "grey.600" } },
            }}
          />
        </Box>
      </Stack>
    </Box>
  );
}
