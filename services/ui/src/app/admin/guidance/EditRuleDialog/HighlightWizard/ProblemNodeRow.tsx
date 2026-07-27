/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

/**
 * Makes an otherwise-invisible tree problem show up as a real, clickable
 * row -- almost always an empty group, which has no guideline text of
 * its own to highlight and so never produces a row in either Step 1's
 * leaf list (`collectPrerequisiteLeaves`) or Step 3's text-derived rows
 * (`buildPathwayRows`). Without this, "jump to issue" has nowhere to
 * land: the reviewer gets a warning sentence and has to guess where the
 * problem actually is.
 *
 * Used by both StepPrerequisites (Step 1) and StepPathwayConditions
 * (Step 3) so a problem reads the same way regardless of which step it
 * turns up in.
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ErrorOutlineRoundedIcon from "@mui/icons-material/ErrorOutlineRounded";

import type { ValidationIssue } from "../treeOps";
import { PROBLEM_ROW } from "./copy";

export interface ProblemNodeRowProps {
  issue: ValidationIssue;
  onRemove: (nodeId: string) => void;
}

export default function ProblemNodeRow({ issue, onRemove }: ProblemNodeRowProps) {
  const { nodeId, message } = issue;
  if (!nodeId) return null;
  return (
    <Box
      data-testid={`wizard-problem-row-${nodeId}`}
      data-node-id={nodeId}
      data-wizard-jump-target="true"
      sx={{
        p: 1,
        borderRadius: 1,
        bgcolor: "error.50",
        border: "1px solid",
        borderColor: "error.light",
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1}>
        <ErrorOutlineRoundedIcon fontSize="small" color="error" />
        <Typography variant="body2" sx={{ flexGrow: 1 }}>
          {message}
        </Typography>
        <Button
          size="small"
          color="error"
          startIcon={<DeleteOutlineIcon fontSize="small" />}
          onClick={() => onRemove(nodeId)}
          aria-label={PROBLEM_ROW.removeAriaLabel(message)}
        >
          {PROBLEM_ROW.removeLabel}
        </Button>
      </Stack>
    </Box>
  );
}
