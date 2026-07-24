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
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ListRecommendationView, {
  type ListRowResolution,
} from "../SentenceEditor/ListRecommendationView";
import type {
  PathwayTextBoundary,
  RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";
import type { EditableLogicNode, LogicCriterion, NodeUpdate } from "../types";
import { STEP_PATHWAY_CONDITIONS } from "./copy";
import PathwayDemographicsPanel, {
  type PathwayDemographicField,
} from "./PathwayDemographicsPanel";
import RowMultiCodeHighlight from "./RowMultiCodeHighlight";
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
  onRowClick: (item: RecommendationStructureItem, anchor: HTMLElement) => void;
  /**
   * When supplied, every row gets a "Highlight text for more codes"
   * affordance (RowMultiCodeHighlight) alongside the normal whole-row
   * click -- for the case where a row's text bundles more than one
   * clinical idea and the reviewer wants to code a specific sub-phrase,
   * possibly with more than one SNOMED code. Omitted entirely (no
   * affordance rendered) when this prop is not passed.
   */
  onAddMultiConcept?: (
    item: RecommendationStructureItem,
    criterion: LogicCriterion,
  ) => void;
  /** Undefined means "not yet asked" -- only relevant when this
   *  pathway has a detected trailing "any of the following" cluster. */
  clusterGrouping?: ClusterGrouping;
  onChooseGrouping?: (grouping: ClusterGrouping) => void;
  /**
   * Same as `clusterGrouping`/`onChooseGrouping` but for a SEPARATE,
   * marker-less lead-or cluster detected ahead of the trailing one
   * (see `buildPathwayRows`'s `leadCluster` -- e.g. "nausea or
   * vomiting" ahead of "any of the following: ..."). Asked
   * independently: both clusters apply to the same pathway ANDed
   * together, but the reviewer decides each one's own AT_LEAST-vs-AND
   * grouping separately, never inferred from which cluster it is.
   */
  leadClusterGrouping?: ClusterGrouping;
  onChooseLeadGrouping?: (grouping: ClusterGrouping) => void;
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
  /**
   * Set only when an EARLIER pathway asked about the exact same
   * findings and has already been resolved (see
   * `useCopyAcrossOffer`/`pathwayCopyAcross.ts`). Offering this is a
   * one-time copy, never a silent auto-fill -- the reviewer must
   * click to accept, and can still change any grouping or code
   * afterwards exactly as if they had picked it themselves.
   */
  copyAcrossOffer?: { sourceLetter: string; count: number } | null;
  onAcceptCopyAcross?: () => void;
  onDismissCopyAcross?: () => void;
  /** Direct DEMOGRAPHIC children of this pathway AND. */
  pathwayDemographics?: EditableLogicNode[];
  onAddPathwayDemographic?: (field: PathwayDemographicField) => void;
  onUpdatePathway?: (update: NodeUpdate) => void;
}

export default function StepPathwayConditions({
  pathwayIndex,
  pathwayCount,
  pathwayLetter,
  nextPathwayLetter = null,
  boundary,
  getRowResolution,
  onRowClick,
  onAddMultiConcept,
  clusterGrouping,
  onChooseGrouping,
  leadClusterGrouping,
  onChooseLeadGrouping,
  confirmedSummaries = [],
  onConfirmPathway,
  confirmBlockedReason = null,
  copyAcrossOffer = null,
  onAcceptCopyAcross,
  onDismissCopyAcross,
  pathwayDemographics = [],
  onAddPathwayDemographic,
  onUpdatePathway,
}: StepPathwayConditionsProps) {
  const { items, hasCluster, leadCluster } = useMemo(
    () => buildPathwayRows(boundary),
    [boundary],
  );

  const trailingClusterTerms = useMemo(() => {
    if (!hasCluster) return [] as string[];
    if (leadCluster) {
      return items.slice(leadCluster.items.length).map((i) => i.text);
    }
    return (items[0]?.children ?? []).map((i) => i.text);
  }, [hasCluster, leadCluster, items]);

  const unresolvedCount = useMemo(() => {
    if (!getRowResolution) return 0;
    return countUnresolvedRows(items, getRowResolution);
  }, [items, getRowResolution]);

  const leadGroupingUndecided = !!leadCluster && !leadClusterGrouping;
  const trailingGroupingUndecided = hasCluster && !clusterGrouping;
  const leadClusterPrompt = leadCluster
    ? STEP_PATHWAY_CONDITIONS.leadClusterPrompt(leadCluster.items.map((i) => i.text))
    : null;
  const trailingClusterPrompt = hasCluster
    ? STEP_PATHWAY_CONDITIONS.clusterPrompt(trailingClusterTerms)
    : null;
  // Do not echo the prompt card's own wording under Confirm -- that
  // read as a second stacked question. Use a short "choose above" hint.
  const blockedReason =
    confirmBlockedReason ??
    (leadGroupingUndecided || trailingGroupingUndecided
      ? STEP_PATHWAY_CONDITIONS.groupingChoiceRequired
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

      {copyAcrossOffer && (
        <CopyAcrossBanner
          offer={copyAcrossOffer}
          onAccept={onAcceptCopyAcross}
          onDismiss={onDismissCopyAcross}
        />
      )}

      {confirmedSummaries.length > 0 && (
        <ConfirmedSoFar summaries={confirmedSummaries} />
      )}

      {onAddPathwayDemographic && onUpdatePathway && (
        <PathwayDemographicsPanel
          demographics={pathwayDemographics}
          onAdd={onAddPathwayDemographic}
          onUpdate={onUpdatePathway}
        />
      )}

      <ListRecommendationView
        items={items}
        getRowResolution={getRowResolution}
        onRowClick={onRowClick}
        renderRowExtra={
          onAddMultiConcept
            ? (item) => (
                <RowMultiCodeHighlight
                  item={item}
                  onAddCriterion={(criterion) => onAddMultiConcept(item, criterion)}
                />
              )
            : undefined
        }
      />

      {leadCluster && leadClusterPrompt && (
        <ClusterGroupingChoice
          prompt={leadClusterPrompt}
          grouping={leadClusterGrouping}
          onChoose={onChooseLeadGrouping}
        />
      )}

      {hasCluster && trailingClusterPrompt && (
        <ClusterGroupingChoice
          prompt={trailingClusterPrompt}
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

function CopyAcrossBanner({
  offer,
  onAccept,
  onDismiss,
}: {
  offer: { sourceLetter: string; count: number };
  onAccept?: () => void;
  onDismiss?: () => void;
}) {
  return (
    <Alert
      severity="info"
      icon={<ContentCopyRoundedIcon fontSize="small" />}
      aria-label={STEP_PATHWAY_CONDITIONS.copyAcrossAriaLabel}
      action={
        <Stack direction="row" spacing={1} sx={{ pt: 0.25 }}>
          <Button size="small" variant="contained" onClick={onAccept}>
            {STEP_PATHWAY_CONDITIONS.copyAcrossAcceptLabel}
          </Button>
          <Button size="small" onClick={onDismiss}>
            {STEP_PATHWAY_CONDITIONS.copyAcrossDismissLabel}
          </Button>
        </Stack>
      }
    >
      {STEP_PATHWAY_CONDITIONS.copyAcrossOffer(offer.sourceLetter, offer.count)}
    </Alert>
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
  prompt,
  grouping,
  onChoose,
}: {
  prompt: string;
  grouping?: ClusterGrouping;
  onChoose?: (grouping: ClusterGrouping) => void;
}) {
  if (grouping) {
    return (
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        role="group"
        aria-label={prompt}
      >
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
    <Box role="group" aria-label={prompt} sx={{ p: 1.5, borderRadius: 1.5, bgcolor: "grey.50" }}>
      <Typography variant="body2" sx={{ mb: 1 }}>
        {prompt}
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
