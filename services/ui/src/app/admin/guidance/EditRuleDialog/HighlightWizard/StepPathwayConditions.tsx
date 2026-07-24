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
 * Highlight-to-build wizard, Step 3: one pathway at a time, "Within
 * this situation, what must ALL be true?" -- repeated once per
 * confirmed pathway from Step 2, with a "Situation B (2 of 6)"
 * progress indicator.
 *
 * Detects a nested "any of the following" cluster within this one
 * pathway (via `resolveAtLeastCluster`, which already prefers the
 * guideline's own nested `<ul>` over the text-marker heuristic) and
 * renders it as a lead row plus indented child rows through the same
 * `ListRecommendationView` used by Step 2 -- one click per row opens
 * the existing concept-search / observation / demographic flow,
 * pre-filled from that row's own text. AND-vs-OR for the cluster is
 * never inferred silently: the reviewer always confirms "only one
 * needs to match" vs "all must match" explicitly.
 *
 * See the plan's Step 3 wireframe (highlight-to-build_rule_wizard_
 * wireframes.md) for the exact layout this implements.
 */
import { useMemo } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ListRecommendationView, {
  type ListRowResolution,
} from "../SentenceEditor/ListRecommendationView";
import type {
  PathwayTextBoundary,
  RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";
import { STEP_PATHWAY_CONDITIONS } from "./copy";
import { buildPathwayRows, countUnresolvedRows } from "./wizardMapping";
import type { ClusterGrouping } from "./wizardMapping";

export type { ClusterGrouping };

export interface StepPathwayConditionsProps {
  /** 1-based position among the confirmed pathways. */
  pathwayIndex: number;
  pathwayCount: number;
  pathwayLetter: string;
  /** The letter of the pathway that follows this one, if any --
   *  drives the "Confirm situation B, next -> C" footer copy. */
  nextPathwayLetter?: string | null;
  boundary: PathwayTextBoundary;
  getRowResolution?: (
    item: RecommendationStructureItem,
  ) => ListRowResolution | undefined;
  onRowClick: (item: RecommendationStructureItem) => void;
  /** Undefined means "not yet asked" -- only relevant when this
   *  pathway has a detected "any of the following" cluster. */
  clusterGrouping?: ClusterGrouping;
  onChooseGrouping?: (grouping: ClusterGrouping) => void;
  confirmedSummaries?: Array<{ letter: string; summary: string }>;
  onConfirmPathway: () => void;
  /**
   * Non-null disables "Confirm situation X" and shows this
   * plain-English reason instead -- e.g. an unresolved-confidence
   * gate the wizard orchestrator computed against the real tree
   * (`confidenceGate.ts`). This component additionally requires
   * every row it can see to have a resolution of its own before
   * enabling the button, regardless of this prop.
   */
  confirmBlockedReason?: string | null;
}

export default function StepPathwayConditions({
  pathwayIndex,
  pathwayCount,
  pathwayLetter,
  nextPathwayLetter = null,
  boundary,
  getRowResolution,
  onRowClick,
  clusterGrouping,
  onChooseGrouping,
  confirmedSummaries = [],
  onConfirmPathway,
  confirmBlockedReason = null,
}: StepPathwayConditionsProps) {
  const { items, hasCluster } = useMemo(() => buildPathwayRows(boundary), [boundary]);

  const unresolvedCount = useMemo(() => {
    if (!getRowResolution) return 0;
    return countUnresolvedRows(items, getRowResolution);
  }, [items, getRowResolution]);

  const groupingUndecided = hasCluster && !clusterGrouping;
  const blockedReason =
    confirmBlockedReason ??
    (groupingUndecided
      ? STEP_PATHWAY_CONDITIONS.clusterPrompt
      : unresolvedCount > 0
        ? STEP_PATHWAY_CONDITIONS.unresolvedBlockedReason(unresolvedCount)
        : null);

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {STEP_PATHWAY_CONDITIONS.situationProgress(
            pathwayLetter,
            pathwayIndex,
            pathwayCount,
          )}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {STEP_PATHWAY_CONDITIONS.helper}
        </Typography>
      </Box>

      {confirmedSummaries.length > 0 && (
        <ConfirmedSoFar summaries={confirmedSummaries} />
      )}

      <ListRecommendationView
        items={items}
        getRowResolution={getRowResolution}
        onRowClick={onRowClick}
      />

      {hasCluster && (
        <ClusterGroupingChoice
          grouping={clusterGrouping}
          onChoose={onChooseGrouping}
        />
      )}

      <Box>
        {blockedReason && (
          <Typography
            variant="caption"
            color="text.secondary"
            role="status"
            display="block"
            sx={{ mb: 0.75 }}
          >
            {blockedReason}
          </Typography>
        )}
        <Button
          variant="contained"
          size="small"
          disabled={!!blockedReason}
          onClick={onConfirmPathway}
        >
          {STEP_PATHWAY_CONDITIONS.confirmLabel(pathwayLetter, nextPathwayLetter)}
        </Button>
      </Box>
    </Stack>
  );
}

function ConfirmedSoFar({
  summaries,
}: {
  summaries: Array<{ letter: string; summary: string }>;
}) {
  return (
    <Stack spacing={0.5}>
      <Typography
        variant="caption"
        sx={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "text.secondary" }}
      >
        {STEP_PATHWAY_CONDITIONS.confirmedHeading}
      </Typography>
      {summaries.map((s) => (
        <Stack
          key={s.letter}
          direction="row"
          spacing={0.75}
          alignItems="center"
          data-testid={`confirmed-pathway-${s.letter}`}
        >
          <CheckCircleIcon fontSize="small" sx={{ color: "#16A34A" }} />
          <Typography variant="body2">
            {s.letter}: {s.summary}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

function ClusterGroupingChoice({
  grouping,
  onChoose,
}: {
  grouping?: ClusterGrouping;
  onChoose?: (grouping: ClusterGrouping) => void;
}) {
  if (grouping) {
    return (
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="body2" color="text.secondary">
          {grouping === "AT_LEAST"
            ? STEP_PATHWAY_CONDITIONS.groupingConfirmedOnlyOne
            : STEP_PATHWAY_CONDITIONS.groupingConfirmedAll}
        </Typography>
        <Button size="small" onClick={() => onChoose?.(grouping === "AT_LEAST" ? "AND" : "AT_LEAST")}>
          {STEP_PATHWAY_CONDITIONS.changeLabel}
        </Button>
      </Stack>
    );
  }
  return (
    <Box role="group" aria-label={STEP_PATHWAY_CONDITIONS.clusterPrompt} sx={{ p: 1.5, borderRadius: 1.5, bgcolor: "grey.50" }}>
      <Typography variant="body2" sx={{ mb: 1 }}>
        {STEP_PATHWAY_CONDITIONS.clusterPrompt}
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
        <Button variant="contained" size="small" onClick={() => onChoose?.("AT_LEAST")}>
          {STEP_PATHWAY_CONDITIONS.onlyOneLabel}
        </Button>
        <Button variant="outlined" size="small" onClick={() => onChoose?.("AND")}>
          {STEP_PATHWAY_CONDITIONS.allMustMatchLabel}
        </Button>
      </Stack>
    </Box>
  );
}
