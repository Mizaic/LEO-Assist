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
import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded";
import PlayArrowRoundedIcon from "@mui/icons-material/PlayArrowRounded";

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
          p: 2,
          display: "flex",
          flexDirection: "column",
          gap: 1.5,
        }}
      >
        <Stack direction="row" alignItems="center" spacing={0.75}>
          <AutoAwesomeRoundedIcon
            sx={{ fontSize: 16, color: "primary.main" }}
          />
          <Typography
            variant="overline"
            sx={{
              display: "block",
              color: "text.secondary",
              letterSpacing: 0.5,
              lineHeight: 1,
            }}
          >
            Before and after
          </Typography>
        </Stack>
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
        p: 2,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={0.75}>
        <AutoAwesomeRoundedIcon
          sx={{ fontSize: 16, color: "primary.main" }}
        />
        <Typography
          variant="overline"
          sx={{
            display: "block",
            color: "text.secondary",
            letterSpacing: 0.5,
            lineHeight: 1,
          }}
        >
          Live preview
        </Typography>
      </Stack>
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
  const ready = Boolean(procedure);
  return (
    <Box
      role="region"
      aria-label="What the system will do when this rule matches"
      sx={{
        position: "relative",
        borderRadius: 2,
        border: "1px solid",
        borderColor: ready ? "success.100" : "warning.100",
        bgcolor: "background.paper",
        overflow: "hidden",
        boxShadow:
          "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04)",
      }}
    >
      <Box
        aria-hidden
        sx={{
          height: 4,
          width: "100%",
          bgcolor: ready ? "success.main" : "warning.main",
        }}
      />
      <Box sx={{ p: 1.75 }}>
        <Stack direction="row" alignItems="center" spacing={0.75}>
          <PlayArrowRoundedIcon
            sx={{
              fontSize: 16,
              color: ready ? "success.main" : "warning.main",
            }}
          />
          <Typography
            variant="overline"
            sx={{
              display: "block",
              color: "text.secondary",
              letterSpacing: 0.5,
              lineHeight: 1,
            }}
          >
            What the system will do
          </Typography>
        </Stack>
        <Typography
          variant="body2"
          sx={{ lineHeight: 1.6, mt: 0.75, fontWeight: 500 }}
        >
          If this rule matches:{" "}
          <Box
            component="span"
            sx={{
              fontWeight: 700,
              color: ready ? "success.dark" : "warning.dark",
            }}
          >
            {strengthLabel}
          </Box>
          {procedure ? (
            <>
              {" "}-{" "}
              <Box
                component="span"
                sx={{ fontWeight: 700, color: "text.primary" }}
              >
                {procedure}
              </Box>
            </>
          ) : (
            <>
              {" "}-{" "}
              <Box
                component="span"
                sx={{ fontStyle: "italic", color: "text.secondary" }}
              >
                no procedure picked yet
              </Box>
            </>
          )}
          .
        </Typography>
      </Box>
    </Box>
  );
}
