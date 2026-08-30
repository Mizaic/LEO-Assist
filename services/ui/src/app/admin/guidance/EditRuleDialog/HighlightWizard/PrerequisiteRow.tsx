/**
 * One always-true captured row in the guided wizard.
 *
 * Atlas trace:
 *   DO: DO-F8C56339
 *   DI: DI-42246DA7, DI-0F0B27D3
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-F8C56339")
 */

"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import DemographicRow from "../LogicTreeEditor/DemographicRow";
import ObservationRow from "../LogicTreeEditor/ObservationRow";
import type { TextMatchRange } from "../SentenceEditor/recommendationTextMatch";
import { conceptSeedLabels } from "../treeToSentence";
import type { EditableLogicNode, NodeUpdate } from "../types";
import CapturedConceptChips from "./CapturedConceptChips";
import { STEP_PREREQUISITES, WIZARD_TOOLTIPS } from "./copy";

export interface PrerequisiteRowData {
  node: EditableLogicNode;
  label: string;
  matches: TextMatchRange[];
}

export default function PrerequisiteRow({
  row,
  onEdit,
  onEditConcept,
  onUpdate,
  onRemove,
}: {
  row: PrerequisiteRowData;
  onEdit: (nodeId: string, anchor?: HTMLElement | null) => void;
  onEditConcept: (nodeId: string) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRemove: (nodeId: string) => void;
}) {
  const isDemographic = row.node.kind === "DEMOGRAPHIC";
  const isObservation = row.node.kind === "OBSERVATION";
  const isInlineEditable = isDemographic || isObservation;
  const [expanded, setExpanded] = useState(false);
  const hasAnchor = row.matches.length > 0;
  const seedLabels = row.node.kind === "CONCEPT" ? conceptSeedLabels(row.node) : [];

  function handleEdit(anchor: HTMLElement) {
    if (row.node.kind === "CONCEPT") {
      onEditConcept(row.node.node_id);
      return;
    }
    if (isInlineEditable) {
      setExpanded((prev) => !prev);
      return;
    }
    onEdit(row.node.node_id, anchor);
  }

  const editLabel = isInlineEditable
    ? expanded
      ? STEP_PREREQUISITES.doneEditingLabel
      : STEP_PREREQUISITES.editLabel
    : hasAnchor
      ? STEP_PREREQUISITES.editLabel
      : STEP_PREREQUISITES.placeManuallyLabel;
  const editTip = isInlineEditable
    ? expanded
      ? WIZARD_TOOLTIPS.doneEditing
      : WIZARD_TOOLTIPS.editCaptured
    : hasAnchor
      ? WIZARD_TOOLTIPS.editCaptured
      : WIZARD_TOOLTIPS.placeManually;

  return (
    <Box
      data-testid={`prerequisite-row-${row.node.node_id}`}
      data-has-anchor={hasAnchor}
      data-node-id={row.node.node_id}
      data-wizard-jump-target="true"
      sx={{
        p: 1,
        borderRadius: 1,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1}>
        {hasAnchor ? (
          <CheckCircleIcon fontSize="small" color="success" />
        ) : (
          <InfoOutlinedIcon fontSize="small" color="action" />
        )}
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          {seedLabels.length > 1 ? (
            <CapturedConceptChips terms={seedLabels} />
          ) : (
            <Typography variant="body2">{row.label}</Typography>
          )}
          {!hasAnchor && (
            <Typography variant="caption" color="text.secondary" display="block">
              {STEP_PREREQUISITES.noAnchorHint}
            </Typography>
          )}
        </Box>
        <Tooltip title={editTip}>
          <Button size="small" onClick={(e) => handleEdit(e.currentTarget)}>
            {editLabel}
          </Button>
        </Tooltip>
        <Tooltip title={WIZARD_TOOLTIPS.removePrerequisite}>
          <Button
            size="small"
            color="error"
            startIcon={<DeleteOutlineIcon fontSize="small" />}
            onClick={() => onRemove(row.node.node_id)}
          >
            {STEP_PREREQUISITES.removeLabel}
          </Button>
        </Tooltip>
      </Stack>
      {isDemographic && (
        <Collapse in={expanded} unmountOnExit>
          <Box sx={{ mt: 1, pl: 4 }}>
            <DemographicRow node={row.node} onUpdate={onUpdate} />
          </Box>
        </Collapse>
      )}
      {isObservation && (
        <Collapse in={expanded} unmountOnExit>
          <Box sx={{ mt: 1, pl: 4 }}>
            <ObservationRow
              node={row.node}
              onUpdate={onUpdate}
              onSelect={(nodeId, anchor) => onEdit(nodeId, anchor)}
            />
          </Box>
        </Collapse>
      )}
    </Box>
  );
}
