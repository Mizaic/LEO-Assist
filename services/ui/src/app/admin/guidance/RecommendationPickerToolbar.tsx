/**
 * Quick-select toolbar for RecommendationPickerDialog.
 *
 * Atlas: DI-EB716E68
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

interface Props {
  attachMode: boolean;
  allChecked: boolean;
  someChecked: boolean;
  allNoRules: number;
  approvedCount: number;
  compiledCount: number;
  onToggleAll: (checked: boolean) => void;
  onSelectApproved: () => void;
  onSelectCompiled: () => void;
}

export function RecommendationPickerToolbar({
  attachMode,
  allChecked,
  someChecked,
  allNoRules,
  approvedCount,
  compiledCount,
  onToggleAll,
  onSelectApproved,
  onSelectCompiled,
}: Props) {
  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      flexWrap="wrap"
      useFlexGap
      sx={{ mb: 1.5 }}
    >
      <FormControlLabel
        control={
          <Checkbox
            size="small"
            checked={allChecked}
            indeterminate={someChecked && !allChecked}
            onChange={(e) => onToggleAll(e.target.checked)}
            inputProps={{ "aria-label": "Select all recommendations" }}
          />
        }
        label={
          <Typography variant="body2" sx={{ fontSize: "0.8rem" }}>
            All recommendations
          </Typography>
        }
      />
      {attachMode ? (
        <>
          <Button
            size="small"
            variant="outlined"
            onClick={onSelectApproved}
            disabled={approvedCount === 0}
            aria-label="Select all approved"
          >
            Select all approved ({approvedCount})
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={onSelectCompiled}
            disabled={compiledCount === 0}
            aria-label="Select all compiled"
          >
            Select all compiled ({compiledCount})
          </Button>
          <Typography variant="caption" color="text.secondary">
            Start with none selected - tick the ones to test
          </Typography>
        </>
      ) : (
        <Typography variant="caption" color="text.secondary">
          {allNoRules} without rules
        </Typography>
      )}
    </Stack>
  );
}
