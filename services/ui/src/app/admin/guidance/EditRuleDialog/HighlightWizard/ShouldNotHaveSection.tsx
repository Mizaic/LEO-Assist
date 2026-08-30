/**
 * Guided-editor list and add button for "Patient should not have".
 *
 * Atlas trace:
 *   DO: DO-4EA3C153
 *   DI: DI-0F0B27D3, DI-42246DA7
 *   Risks: R-4E4F22EF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4EA3C153")
 */

"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";

import type { EditableLogicNode } from "../types";
import { STEP_PREREQUISITES } from "./copy";
import { shouldNotHaveLabel } from "./shouldNotHave";

export function ShouldNotHaveButton({
  ariaLabel,
  tooltip,
  onClick,
}: {
  ariaLabel: string;
  tooltip: string;
  onClick: (anchor: HTMLElement) => void;
}) {
  return (
    <Tooltip title={tooltip}>
      <Button
        variant="outlined"
        size="small"
        startIcon={<AddRoundedIcon fontSize="small" />}
        onClick={(e) => onClick(e.currentTarget)}
        aria-label={ariaLabel}
      >
        {STEP_PREREQUISITES.shouldNotHaveLabel}
      </Button>
    </Tooltip>
  );
}

export function ShouldNotHaveSection({
  leaves,
  onEdit,
  onRemove,
}: {
  leaves: EditableLogicNode[];
  onEdit?: (node: EditableLogicNode) => void;
  onRemove?: (nodeId: string) => void;
}) {
  if (leaves.length === 0) return null;
  return (
    <Stack spacing={0.75} data-testid="should-not-have-section">
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: "text.secondary",
        }}
      >
        {STEP_PREREQUISITES.shouldNotHaveHeading}
      </Typography>
      {leaves.map((node) => (
        <Stack
          key={node.node_id}
          direction="row"
          alignItems="center"
          spacing={0.75}
          data-testid={`should-not-have-row-${node.node_id}`}
          data-node-id={node.node_id}
          data-wizard-jump-target="true"
          sx={{
            p: 1,
            borderRadius: 1,
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Box
            component={onEdit ? "button" : "div"}
            type={onEdit ? "button" : undefined}
            onClick={onEdit ? () => onEdit(node) : undefined}
            sx={{
              flexGrow: 1,
              textAlign: "left",
              background: "none",
              border: "none",
              cursor: onEdit ? "pointer" : "default",
              p: 0,
              font: "inherit",
              color: "inherit",
            }}
          >
            <Typography variant="body2">{shouldNotHaveLabel(node)}</Typography>
          </Box>
          {onRemove && (
            <Button size="small" color="error" onClick={() => onRemove(node.node_id)}>
              {STEP_PREREQUISITES.removeLabel}
            </Button>
          )}
        </Stack>
      ))}
    </Stack>
  );
}
