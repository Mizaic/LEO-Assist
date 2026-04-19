"use client";

/**
 * Right-column live preview for the widescreen rule editor.
 *
 * Two stacked sections:
 *   1. "What this rule means" -- the same plain-English summary
 *      shown elsewhere in the editor, but always pinned open here so
 *      the user can see their edits make sense without parsing the
 *      logic tree.
 *   2. "What the system will do" -- one short sentence built from
 *      the strength label and the action SNOMED preferred term.
 *
 * On step 4 the pane swaps to a "Before / After" variant: two
 * side-by-side summary cards computed from the original tree (`before`)
 * and the edited tree (`after`).
 *
 * Pure presentational; all rendering work is done outside this file
 * (treeToSentence, STRENGTH_LABELS).
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510.
 */

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import SummaryCard from "./SummaryCard";
import { STRENGTH_LABELS, friendlyTerm } from "./copy";
import type { RuleSummary } from "./treeToSentence";
import type { LogicCriterion } from "./types";

interface SystemRecapProps {
  strength: string;
  action: LogicCriterion | null;
}

interface Props {
  /** Live summary of the tree the user is editing. */
  summary: RuleSummary;
  /** Current strength code (e.g. "offer", "consider"). */
  strength: string;
  /** Current action SNOMED criterion. */
  action: LogicCriterion | null;
  /**
   * When true (step 4), render a Before / After diff using `summary`
   * as the after, and `beforeSummary` as the before.
   */
  showBeforeAfter?: boolean;
  beforeSummary?: RuleSummary;
  beforeStrength?: string;
  beforeAction?: LogicCriterion | null;
}

export default function LivePreviewPane({
  summary,
  strength,
  action,
  showBeforeAfter,
  beforeSummary,
  beforeStrength,
  beforeAction,
}: Props) {
  if (showBeforeAfter && beforeSummary) {
    return (
      <Box
        role="region"
        aria-label="Before and after preview of this rule"
        sx={{
          position: "sticky",
          top: 0,
          alignSelf: "flex-start",
          p: 1.5,
          display: "flex",
          flexDirection: "column",
          gap: 1.5,
        }}
      >
        <Typography
          variant="overline"
          sx={{
            display: "block",
            color: "text.secondary",
            letterSpacing: 0.5,
          }}
        >
          Before and after
        </Typography>
        <Stack
          direction={{ xs: "column", lg: "row" }}
          spacing={1.5}
          alignItems="stretch"
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              variant="caption"
              sx={{
                display: "block",
                fontWeight: 700,
                color: "text.secondary",
                mb: 0.5,
              }}
            >
              Before your change
            </Typography>
            <SummaryCard summary={beforeSummary} defaultExpanded />
            <Box sx={{ mt: 1 }}>
              <SystemRecap
                strength={beforeStrength ?? "unspecified"}
                action={beforeAction ?? null}
              />
            </Box>
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              variant="caption"
              sx={{
                display: "block",
                fontWeight: 700,
                color: "primary.dark",
                mb: 0.5,
              }}
            >
              After your change
            </Typography>
            <SummaryCard summary={summary} defaultExpanded />
            <Box sx={{ mt: 1 }}>
              <SystemRecap strength={strength} action={action} />
            </Box>
          </Box>
        </Stack>
      </Box>
    );
  }

  return (
    <Box
      role="region"
      aria-label="Live preview of this rule"
      sx={{
        position: "sticky",
        top: 0,
        alignSelf: "flex-start",
        p: 1.5,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
      }}
    >
      <Typography
        variant="overline"
        sx={{ display: "block", color: "text.secondary", letterSpacing: 0.5 }}
      >
        Live preview
      </Typography>
      <SummaryCard summary={summary} defaultExpanded />
      <SystemRecap strength={strength} action={action} />
    </Box>
  );
}

function SystemRecap({ strength, action }: SystemRecapProps) {
  const strengthLabel =
    STRENGTH_LABELS.find((o) => o.value === strength)?.label ??
    "Not specified yet";
  const procedure = friendlyTerm(action?.preferred_term);
  return (
    <Box
      role="region"
      aria-label="What the system will do when this rule matches"
      sx={{
        p: 1.5,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: procedure ? "success.100" : "warning.100",
        bgcolor: procedure ? "success.50" : "warning.50",
      }}
    >
      <Typography
        variant="overline"
        sx={{
          display: "block",
          color: "text.secondary",
          letterSpacing: 0.5,
        }}
      >
        What the system will do
      </Typography>
      <Typography variant="body2" sx={{ lineHeight: 1.55, mt: 0.25 }}>
        If this rule matches: <strong>{strengthLabel}</strong>
        {procedure ? (
          <>
            {" "}- <strong>{procedure}</strong>
          </>
        ) : (
          <>
            {" "}- <em>no procedure picked yet</em>
          </>
        )}
        .
      </Typography>
    </Box>
  );
}
