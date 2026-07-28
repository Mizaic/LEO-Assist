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
 * Flat "Add another procedure" means suggest all (AND). On a row, the
 * clinician can add "If not available..." (preferred then fallback) or
 * "Or instead..." (either/or) without learning group jargon.
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

import {
  actionGroupCaption,
  actionGroupRankLabel,
  groupActionsForDisplay,
} from "./actionGroups";
import { STRENGTH_LABELS, friendlyTerm } from "./copy";
import type { ActionGroupMode, RuleAction } from "./types";

const REMOVE_BLOCKED_HINT =
  "A rule needs at least one recommended procedure. Add another before removing this one.";

interface RowProps {
  action: RuleAction;
  index: number;
  rankIndex: number;
  groupMode: ActionGroupMode;
  isSelected: boolean;
  canRemove: boolean;
  onSelect: (index: number) => void;
  onStrengthChange: (index: number, strength: string) => void;
  onRemove: (index: number) => void;
  onAddFallback: (index: number) => void;
  onAddOrAlternative: (index: number) => void;
}

function ProcedureStrengthControls({
  action,
  index,
  isSelected,
  canRemove,
  onSelect,
  onStrengthChange,
  onRemove,
}: Omit<RowProps, "rankIndex" | "groupMode" | "onAddFallback" | "onAddOrAlternative">) {
  const friendly = friendlyTerm(action.criterion?.preferred_term);
  const hasCode = Boolean(action.criterion?.snomed_concept_id);
  const label = friendly || "No procedure picked yet";
  const tooltip = hasCode
    ? `${friendly} (clinical code ${action.criterion.snomed_concept_id}). Click to swap.`
    : "Pick the SNOMED procedure the system should suggest when this rule fires.";
  const selectId = `edit-rule-action-strength-${index}`;

  return (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ flexWrap: "wrap" }}>
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
  );
}

function AlternativeAddButtons({
  index,
  onAddFallback,
  onAddOrAlternative,
}: {
  index: number;
  onAddFallback: (index: number) => void;
  onAddOrAlternative: (index: number) => void;
}) {
  return (
    <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: "wrap" }}>
      <Button
        size="small"
        onClick={() => onAddFallback(index)}
        aria-label={`If not available, add another procedure after row ${index + 1}`}
      >
        If not available, add...
      </Button>
      <Button
        size="small"
        onClick={() => onAddOrAlternative(index)}
        aria-label={`Or instead, add another procedure after row ${index + 1}`}
      >
        Or instead, add...
      </Button>
    </Stack>
  );
}

function ActionRow(props: RowProps) {
  const {
    action,
    index,
    rankIndex,
    groupMode,
    onAddFallback,
    onAddOrAlternative,
  } = props;
  const hasCode = Boolean(action.criterion?.snomed_concept_id);
  const rankLabel = actionGroupRankLabel(groupMode, rankIndex);

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
      {rankLabel ? (
        <Typography
          variant="caption"
          sx={{ display: "block", color: "text.secondary", mb: 0.5, fontWeight: 600 }}
        >
          {rankLabel}
        </Typography>
      ) : null}
      <ProcedureStrengthControls {...props} />
      <AlternativeAddButtons
        index={index}
        onAddFallback={onAddFallback}
        onAddOrAlternative={onAddOrAlternative}
      />
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
  onAddFallback: (afterIndex: number) => void;
  onAddOrAlternative: (afterIndex: number) => void;
}

export default function ActionsPanel({
  actions,
  selectedIndex,
  onSelectAction,
  onStrengthChange,
  onRemoveAction,
  onAddAction,
  onAddFallback,
  onAddOrAlternative,
}: Props) {
  const groups = groupActionsForDisplay(actions);

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
        Add another procedure when the system should suggest both. Use
        &quot;If not available&quot; for MRI then CT-style chains. Use
        &quot;Or instead&quot; when either procedure is fine.
      </Typography>
      <Stack spacing={1.25}>
        {groups.map((group) => {
          const caption = actionGroupCaption(group.mode);
          return (
            <Box
              key={group.key}
              sx={
                group.mode === "all"
                  ? undefined
                  : {
                      p: 1,
                      borderRadius: 1.5,
                      border: "1px dashed",
                      borderColor: "divider",
                      bgcolor: "background.paper",
                    }
              }
            >
              {caption ? (
                <Typography
                  variant="caption"
                  sx={{
                    display: "block",
                    color: "text.secondary",
                    mb: 0.75,
                    fontWeight: 600,
                  }}
                >
                  {caption}
                </Typography>
              ) : null}
              <Stack spacing={1}>
                {group.indices.map((index, rankIndex) => (
                  <ActionRow
                    key={index}
                    action={actions[index]}
                    index={index}
                    rankIndex={rankIndex}
                    groupMode={group.mode}
                    isSelected={selectedIndex === index}
                    canRemove={actions.length > 1}
                    onSelect={onSelectAction}
                    onStrengthChange={onStrengthChange}
                    onRemove={onRemoveAction}
                    onAddFallback={onAddFallback}
                    onAddOrAlternative={onAddOrAlternative}
                  />
                ))}
              </Stack>
            </Box>
          );
        })}
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
