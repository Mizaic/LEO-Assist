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
 * Editable view of the rule's recommended actions -- one or more SNOMED
 * procedures the system suggests when the rule fires, each with its own
 * strength (offer / consider / refer / ...).
 *
 * Click a chip to target it for the right-hand concept search panel (same
 * flow as logic-tree concept chips). Picking a search hit then updates
 * that row's procedure via the parent dialog. Each row also owns a
 * strength Select and a delete icon; the delete icon is disabled on the
 * last remaining row because a rule always needs at least one action.
 *
 * Design Controls: DI-42246DA7, DO-F8C56339.
 */

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import CloseIcon from "@mui/icons-material/Close";

import { STRENGTH_LABELS, friendlyTerm } from "./copy";
import type { RuleAction } from "./types";

const REMOVE_BLOCKED_HINT =
  "A rule needs at least one recommended procedure. Add another before removing this one.";

interface RowProps {
  action: RuleAction;
  index: number;
  isSelected: boolean;
  canRemove: boolean;
  onSelect: (index: number) => void;
  onStrengthChange: (index: number, strength: string) => void;
  onRemove: (index: number) => void;
}

function ActionRow({
  action,
  index,
  isSelected,
  canRemove,
  onSelect,
  onStrengthChange,
  onRemove,
}: RowProps) {
  const friendly = friendlyTerm(action.criterion?.preferred_term);
  const hasCode = Boolean(action.criterion?.snomed_concept_id);
  const label = friendly || "No procedure picked yet";
  const tooltip = hasCode
    ? `${friendly} (clinical code ${action.criterion.snomed_concept_id}). Click to swap.`
    : "Pick the SNOMED procedure the system should suggest when this rule fires.";
  const selectId = `edit-rule-action-strength-${index}`;

  return (
    <Box
      role="group"
      aria-label={`Recommended procedure ${index + 1}`}
      sx={{
        p: 1.25,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: hasCode ? "success.100" : "warning.100",
        bgcolor: hasCode ? "success.50" : "warning.50",
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{ flexWrap: "wrap" }}
      >
        <Tooltip title={tooltip} arrow>
          <Chip
            label={label}
            color={isSelected ? "primary" : hasCode ? "success" : "warning"}
            variant={isSelected ? "filled" : "outlined"}
            size="medium"
            onClick={() => onSelect(index)}
            sx={{ height: 32, fontSize: "0.85rem", maxWidth: "100%" }}
            aria-label={`${label}. Click to pick a different procedure.`}
          />
        </Tooltip>
        <Box sx={{ minWidth: 200, flex: 1 }}>
          <Typography
            variant="caption"
            component="label"
            htmlFor={selectId}
            sx={{ display: "block", color: "text.secondary", mb: 0.25, ml: 0.5 }}
          >
            What should the system suggest?
          </Typography>
          <Select
            id={selectId}
            size="small"
            fullWidth
            value={action.strength}
            onChange={(e) => onStrengthChange(index, String(e.target.value))}
            inputProps={{
              "aria-label": `What should the system suggest for procedure ${index + 1}`,
            }}
          >
            {STRENGTH_LABELS.map((o) => (
              <MenuItem key={o.value} value={o.value}>
                {o.label}
              </MenuItem>
            ))}
          </Select>
        </Box>
        <Tooltip title={canRemove ? "Remove this procedure" : REMOVE_BLOCKED_HINT} arrow>
          <span>
            <IconButton
              size="small"
              onClick={() => onRemove(index)}
              disabled={!canRemove}
              aria-label={`Remove procedure ${index + 1}`}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    </Box>
  );
}

interface Props {
  actions: RuleAction[];
  /** Index of the action row currently targeted by the search panel, or null. */
  selectedIndex: number | null;
  onSelectAction: (index: number) => void;
  onStrengthChange: (index: number, strength: string) => void;
  onRemoveAction: (index: number) => void;
  onAddAction: () => void;
}

export default function ActionsPanel({
  actions,
  selectedIndex,
  onSelectAction,
  onStrengthChange,
  onRemoveAction,
  onAddAction,
}: Props) {
  return (
    <Box role="region" aria-label="Recommended procedures for this rule">
      <Typography
        variant="overline"
        sx={{ display: "block", color: "text.secondary", letterSpacing: 0.5 }}
      >
        What the system will suggest when this rule matches
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ lineHeight: 1.4, mb: 1 }}
      >
        Click a green pill to swap it for a different procedure. Each
        procedure has its own strength.
      </Typography>
      <Stack spacing={1}>
        {actions.map((action, index) => (
          <ActionRow
            key={index}
            action={action}
            index={index}
            isSelected={selectedIndex === index}
            canRemove={actions.length > 1}
            onSelect={onSelectAction}
            onStrengthChange={onStrengthChange}
            onRemove={onRemoveAction}
          />
        ))}
      </Stack>
      <Button
        size="small"
        startIcon={<AddRoundedIcon fontSize="small" />}
        onClick={onAddAction}
        aria-label="Add another recommended procedure"
        sx={{ mt: 1 }}
      >
        Add another procedure
      </Button>
    </Box>
  );
}
