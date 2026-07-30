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
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import DemographicRow from "../LogicTreeEditor/DemographicRow";
import ObservationRow from "../LogicTreeEditor/ObservationRow";
import ListRecommendationView, {
  type ListRowResolution,
} from "../SentenceEditor/ListRecommendationView";
import type {
  PathwayTextBoundary,
  RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";
import type { ValidationIssue } from "../treeOps";
import {
  ClusterGroupingChoice,
  ConfirmedPathwayConditions,
  ConfirmedSoFar,
  CopyAcrossBanner,
} from "./PathwayConditionsChrome";
import type { EditableLogicNode, LogicCriterion, NodeUpdate } from "../types";
import { STEP_PATHWAY_CONDITIONS, WIZARD_TOOLTIPS } from "./copy";
import PathwayDemographicsPanel, {
  type PathwayDemographicField,
} from "./PathwayDemographicsPanel";
import ProblemNodeRow from "./ProblemNodeRow";
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
  /** Second arg is the AT_LEAST.min to apply (1 for only-one, N for
   *  "at least N"). Ignored when grouping is AND. */
  onChooseGrouping?: (grouping: ClusterGrouping, min?: number) => void;
  /** Live AT_LEAST.min on the trailing subgroup (after a choice). */
  clusterMin?: number;
  /** Guideline-suggested min ("2 or more" -> 2). Drives Recommended. */
  suggestedClusterMin?: number;
  /** Term count for the trailing cluster -- clamps the min stepper. */
  clusterTermCount?: number;
  onSetClusterMin?: (min: number) => void;
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
  /**
   * Non-DEMOGRAPHIC leaves already captured on this pathway with no
   * guideline quote to derive a `ListRecommendationView` row from (see
   * `pathwayConfirmedLeaves`'s doc comment) -- rendered as its own
   * reviewable/removable list so a tree-rehydrated situation's existing
   * CONCEPT/OBSERVATION conditions are never silently invisible.
   */
  confirmedLeaves?: EditableLogicNode[];
  onEditConfirmedLeaf?: (node: EditableLogicNode) => void;
  onRemoveConfirmedLeaf?: (node: EditableLogicNode) => void;
  /**
   * The DEMOGRAPHIC leaf (from the main condition list, NOT
   * `pathwayDemographics` above) whose inline age/sex editor should
   * currently render, toggled by re-clicking its row (see
   * `PathwayConditionsStage.handleRowClick`). Passed as the resolved
   * node itself -- not looked up via `getRowResolution` -- because
   * editing the value can change its own display text enough that it
   * stops fuzzy-matching the original guideline wording, which would
   * otherwise cause the editor to vanish mid-edit. Null/undefined
   * means none is expanded.
   */
  expandedDemographicNode?: EditableLogicNode | null;
  /**
   * The OBSERVATION leaf whose inline operator/value/unit editor
   * should currently render, toggled by re-clicking its row (see
   * `PathwayConditionsStage.handleRowClick`). Passed as the resolved
   * node itself for the same mid-edit stability reason as
   * `expandedDemographicNode`. Null/undefined means none is expanded.
   */
  expandedObservationNode?: EditableLogicNode | null;
  /** Chip click inside the expanded ObservationRow -- swaps the
   *  observable via the existing concept-search popover. */
  onSelectObservation?: (nodeId: string, anchor?: HTMLElement | null) => void;
  /**
   * Tree problems in this pathway with no guideline text of their own
   * to anchor a normal row to (almost always an empty group) -- see
   * `PathwayConditionsStage`'s `pathwayProblemIssues` doc comment.
   * Rendered as its own always-visible row so "jump to issue" always
   * has somewhere real to land.
   */
  problemIssues?: ValidationIssue[];
  onRemoveProblem?: (nodeId: string) => void;
  /** NG12 1.7.1 weighted companion checklist on this boundary. */
  weightedChecklist?: {
    title: string;
    threshold: number;
    expanded: boolean;
    scorePhrase: string | null;
    majors: string[];
    minors: string[];
  } | null;
  onExpandWeightedChecklist?: () => void;
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
  clusterMin,
  suggestedClusterMin,
  clusterTermCount = 0,
  onSetClusterMin,
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
  confirmedLeaves = [],
  onEditConfirmedLeaf,
  onRemoveConfirmedLeaf,
  expandedDemographicNode = null,
  expandedObservationNode = null,
  onSelectObservation,
  problemIssues = [],
  onRemoveProblem,
  weightedChecklist = null,
  onExpandWeightedChecklist,
}: StepPathwayConditionsProps) {
  const { items: rawItems, hasCluster, leadCluster, suggestedMin } = useMemo(
    () => buildPathwayRows(boundary),
    [boundary],
  );
  // Hide the score-instrument phrase while Expand is still available --
  // coding that phrase as a bare CONCEPT is the escape hatch, not the
  // happy path for a weighted companion checklist.
  const items = useMemo(() => {
    if (!weightedChecklist || weightedChecklist.expanded) return rawItems;
    const score = (weightedChecklist.scorePhrase || "").toLowerCase();
    if (!score) return rawItems;
    return rawItems.filter((i) => i.text.toLowerCase() !== score);
  }, [rawItems, weightedChecklist]);
  const effectiveSuggestedMin = suggestedClusterMin ?? suggestedMin ?? 1;
  const effectiveClusterMin = clusterMin ?? effectiveSuggestedMin;

  const trailingClusterTerms = useMemo(() => {
    if (!hasCluster) return [] as string[];
    if (leadCluster) {
      return items.slice(leadCluster.items.length).map((i) => i.text);
    }
    // Flat shared quantifier lists (NG12 1.1.2) put cluster rows on
    // `items` itself with no lead wrapper -- fall back like
    // `isClusterChildRow` does, so the prompt names the symptoms.
    // Nested lead + children ("ever smoked" + symptoms) uses children.
    return (items[0]?.children ?? items).map((i) => i.text);
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
    ? STEP_PATHWAY_CONDITIONS.clusterPrompt(
        trailingClusterTerms,
        effectiveSuggestedMin,
      )
    : null;
  const termCount = clusterTermCount || trailingClusterTerms.length;
  // Do not echo the prompt card's own wording under Confirm -- that
  // read as a second stacked question. Use a short "choose above" hint.
  const blockedReason =
    confirmBlockedReason ??
    (leadGroupingUndecided || trailingGroupingUndecided
      ? STEP_PATHWAY_CONDITIONS.groupingChoiceRequired
      : unresolvedCount > 0
        ? STEP_PATHWAY_CONDITIONS.unresolvedBlockedReason(unresolvedCount)
        : null);

  // Nested lead + either/or children (NG12 1.3.1 E). Split so the
  // required lead stays above the grouping card and cannot be misread
  // as part of "only one needs to match".
  const leadItem = items[0];
  const nestedLeadEitherOf =
    hasCluster && !leadCluster && !!leadItem?.children?.length;
  const leadRowAlone: RecommendationStructureItem | null = leadItem
    ? { ...leadItem, children: undefined }
    : null;
  const eitherOfChildren = leadItem?.children ?? [];
  const rowExtra = onAddMultiConcept
    ? (item: RecommendationStructureItem) => (
        <RowMultiCodeHighlight
          item={item}
          onAddCriterion={(criterion) => onAddMultiConcept(item, criterion)}
        />
      )
    : undefined;

  return (
    <Stack spacing={2} data-tour="er-05-conditions">
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

      {onEditConfirmedLeaf && (
        <ConfirmedPathwayConditions
          leaves={confirmedLeaves}
          onEditLeaf={onEditConfirmedLeaf}
          onRemoveLeaf={onRemoveConfirmedLeaf}
        />
      )}

      {onAddPathwayDemographic && onUpdatePathway && (
        <PathwayDemographicsPanel
          demographics={pathwayDemographics}
          onAdd={onAddPathwayDemographic}
          onUpdate={onUpdatePathway}
        />
      )}

      {weightedChecklist && !weightedChecklist.expanded && onExpandWeightedChecklist && (
        <Box
          sx={{
            p: 1.5,
            borderRadius: 1.5,
            border: "1px dashed",
            borderColor: "primary.main",
          }}
          data-testid="weighted-checklist-expand"
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
            {weightedChecklist.title}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {STEP_PATHWAY_CONDITIONS.weightedChecklistExpandHint}
          </Typography>
          <Tooltip title={STEP_PATHWAY_CONDITIONS.weightedChecklistExpandHint}>
            <Button
              variant="contained"
              size="small"
              onClick={onExpandWeightedChecklist}
              aria-label={STEP_PATHWAY_CONDITIONS.weightedChecklistExpand(
                weightedChecklist.threshold,
              )}
            >
              {STEP_PATHWAY_CONDITIONS.weightedChecklistExpand(
                weightedChecklist.threshold,
              )}
            </Button>
          </Tooltip>
        </Box>
      )}

      {weightedChecklist?.expanded && (
        <Typography variant="body2" color="text.secondary">
          Major features ({weightedChecklist.majors.length}) and minor features (
          {weightedChecklist.minors.length}). Score at least {weightedChecklist.threshold}{" "}
          means any two majors, or one major plus one minor, or three minors.
        </Typography>
      )}

      {/* Lead finding outside an either/or group (e.g. NG12 1.3.1 E
          rectal bleeding) renders above the grouping card so it cannot
          scroll away under "Only one of these needs to match". */}
      {nestedLeadEitherOf ? (
        <Stack spacing={1} data-testid="lead-either-of-layout">
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
            {STEP_PATHWAY_CONDITIONS.leadRequiredCaption}
          </Typography>
          <ListRecommendationView
            items={[leadRowAlone!]}
            getRowResolution={getRowResolution}
            onRowClick={onRowClick}
            renderRowExtra={rowExtra}
          />
          {trailingClusterPrompt && (
            <ClusterGroupingChoice
              prompt={trailingClusterPrompt}
              grouping={clusterGrouping}
              onChoose={onChooseGrouping}
              suggestedMin={effectiveSuggestedMin}
              clusterMin={effectiveClusterMin}
              termCount={termCount}
              confirmedTerms={trailingClusterTerms}
              onSetClusterMin={onSetClusterMin}
            />
          )}
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
            {STEP_PATHWAY_CONDITIONS.eitherOfHeading}
          </Typography>
          <ListRecommendationView
            items={eitherOfChildren}
            getRowResolution={getRowResolution}
            onRowClick={onRowClick}
            renderRowExtra={rowExtra}
          />
        </Stack>
      ) : (
        <ListRecommendationView
          items={items}
          getRowResolution={getRowResolution}
          onRowClick={onRowClick}
          renderRowExtra={rowExtra}
        />
      )}

      {onRemoveProblem &&
        problemIssues.map((issue) => (
          <ProblemNodeRow key={issue.nodeId} issue={issue} onRemove={onRemoveProblem} />
        ))}

      {expandedDemographicNode && onUpdatePathway && (
        <Box sx={{ p: 1.5, borderRadius: 1.5, border: "1px solid", borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
            {STEP_PATHWAY_CONDITIONS.editingDemographicHeading}
          </Typography>
          <DemographicRow node={expandedDemographicNode} onUpdate={onUpdatePathway} />
        </Box>
      )}

      {expandedObservationNode && onUpdatePathway && onSelectObservation && (
        <Box sx={{ p: 1.5, borderRadius: 1.5, border: "1px solid", borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.75 }}>
            {STEP_PATHWAY_CONDITIONS.editingObservationHeading}
          </Typography>
          <ObservationRow
            node={expandedObservationNode}
            onUpdate={onUpdatePathway}
            onSelect={onSelectObservation}
          />
        </Box>
      )}

      {leadCluster && leadClusterPrompt && (
        <ClusterGroupingChoice
          prompt={leadClusterPrompt}
          grouping={leadClusterGrouping}
          onChoose={onChooseLeadGrouping}
        />
      )}

      {!nestedLeadEitherOf && hasCluster && trailingClusterPrompt && (
        <ClusterGroupingChoice
          prompt={trailingClusterPrompt}
          grouping={clusterGrouping}
          onChoose={onChooseGrouping}
          suggestedMin={effectiveSuggestedMin}
          clusterMin={effectiveClusterMin}
          termCount={termCount}
          confirmedTerms={trailingClusterTerms}
          onSetClusterMin={onSetClusterMin}
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
        <Tooltip title={WIZARD_TOOLTIPS.confirmSituation}>
          <span>
            <Button
              variant="contained"
              size="small"
              disabled={!!blockedReason}
              onClick={onConfirmPathway}
            >
              {STEP_PATHWAY_CONDITIONS.confirmLabel(pathwayLetter, nextPathwayLetter)}
            </Button>
          </span>
        </Tooltip>
      </Box>
    </Stack>
  );
}
