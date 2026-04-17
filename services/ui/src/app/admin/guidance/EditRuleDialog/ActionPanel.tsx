"use client";

/**
 * Editable view of the rule's recommended action (the SNOMED procedure
 * the system suggests when the rule fires).
 *
 * Click the chip to target it for the right-hand concept search panel
 * (same flow as logic-tree concept chips). Clicking a search hit then
 * updates the action via the parent dialog.
 *
 * Design Controls: DI-LEO-AI-170, DO-LEO-AI-169, R-LEO-AI-169.
 */

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { friendlyTerm } from "./copy";
import type { LogicCriterion } from "./types";

interface Props {
  action: LogicCriterion | null;
  isSelected: boolean;
  onSelect: () => void;
}

export default function ActionPanel({ action, isSelected, onSelect }: Props) {
  const friendly = friendlyTerm(action?.preferred_term);
  const hasCode = Boolean(action?.snomed_concept_id);
  const label = friendly || "No procedure picked yet";
  const tooltip = action?.snomed_concept_id
    ? `${friendly} (clinical code ${action.snomed_concept_id}). Click to swap.`
    : "Pick the SNOMED procedure the system should suggest when this rule fires.";

  return (
    <Box
      role="region"
      aria-label="Recommended procedure for this rule"
      sx={{
        p: 1.25,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: hasCode ? "success.100" : "warning.100",
        bgcolor: hasCode ? "success.50" : "warning.50",
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1} sx={{ flexWrap: "wrap" }}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            variant="overline"
            sx={{ display: "block", color: "text.secondary", letterSpacing: 0.5 }}
          >
            What the system will suggest when this rule matches
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.4 }}>
            Click the green pill to swap this for a different procedure.
          </Typography>
        </Box>
        <Tooltip title={tooltip} arrow>
          <Chip
            label={label}
            color={isSelected ? "primary" : hasCode ? "success" : "warning"}
            variant={isSelected ? "filled" : "outlined"}
            size="medium"
            onClick={onSelect}
            sx={{ height: 32, fontSize: "0.85rem", maxWidth: "100%" }}
            aria-label={`${label}. Click to pick a different procedure.`}
          />
        </Tooltip>
      </Stack>
    </Box>
  );
}
