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
import AddRoundedIcon from "@mui/icons-material/AddRounded";

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
import {
  ExpandedConditionEditors,
  WeightedChecklistSection,
  type WeightedChecklistView,
} from "./PathwayConditionsExtras";
import type { EditableLogicNode, LogicCriterion, NodeUpdate } from "../types";
import { STEP_PATHWAY_CONDITIONS, WIZARD_TOOLTIPS } from "./copy";
import PathwayDemographicsPanel, {
  type PathwayDemographicField,
} from "./PathwayDemographicsPanel";
import ProblemNodeRow from "./ProblemNodeRow";
import { ShouldNotHaveButton, ShouldNotHaveSection } from "./ShouldNotHaveSection";
import RowMultiCodeHighlight from "./RowMultiCodeHighlight";
import { buildPathwayRows, countUnresolvedRows } from "./wizardMapping";
import type { ClusterGrouping } from "./wizardMapping";

export type { ClusterGrouping };

export interface StepPathwayConditionsProps {
  /** 1-based position among the confirmed pathways. */
  pathwayIndex: number;
  pathwayCount: number;
  pathwayLetter: string;
  /** Letter of the next pathway, if any -- drives "Confirm situation B, next -> C". */
  nextPathwayLetter?: string | null;
  boundary: PathwayTextBoundary;
  /** Optional full recommendation sentence so split-row highlights can reach shared lead words. */
  recommendationText?: string | null;
  getRowResolution?: (
    item: RecommendationStructureItem,
  ) => ListRowResolution | undefined;
  onRowClick: (item: RecommendationStructureItem, anchor: HTMLElement) => void;
  /** Renders "Highlight text for more codes" when provided. */
  onAddMultiConcept?: (
    item: RecommendationStructureItem,
    criterion: LogicCriterion,
    selectedText?: string,
  ) => void;
  /** Undefined means "not yet asked" for a trailing cluster. */
  clusterGrouping?: ClusterGrouping;
  /** Second arg is AT_LEAST.min (1 for only-one, N for at-least-N). */
  onChooseGrouping?: (grouping: ClusterGrouping, min?: number) => void;
  clusterMin?: number;
  suggestedClusterMin?: number;
  clusterTermCount?: number;
  onSetClusterMin?: (min: number) => void;
  /** Separate marker-less lead-or cluster ahead of the trailing list. */
  leadClusterGrouping?: ClusterGrouping;
  onChooseLeadGrouping?: (grouping: ClusterGrouping) => void;
  confirmedSummaries?: Array<{ letter: string; summary: string }>;
  onConfirmPathway: () => void;
  /** Non-null disables "Confirm situation X" and shows this reason. */
  confirmBlockedReason?: string | null;
  /** One-time copy offer from an earlier matching situation. */
  copyAcrossOffer?: { sourceLetter: string; count: number } | null;
  onAcceptCopyAcross?: () => void;
  onDismissCopyAcross?: () => void;
  /** Direct DEMOGRAPHIC children of this pathway AND. */
  pathwayDemographics?: EditableLogicNode[];
  onAddPathwayDemographic?: (field: PathwayDemographicField) => void;
  onUpdatePathway?: (update: NodeUpdate) => void;
  /** Non-DEMOGRAPHIC leaves on this pathway not already represented by a text row. */
  confirmedLeaves?: EditableLogicNode[];
  onEditConfirmedLeaf?: (node: EditableLogicNode) => void;
  onRemoveConfirmedLeaf?: (node: EditableLogicNode) => void;
  /** Adds a blank lab-value condition attached to this pathway only. */
  onAddPathwayObservation?: () => void;
  /** Findings inside a NOT group on this pathway. */
  shouldNotHaveLeaves?: EditableLogicNode[];
  /** Adds a must-not-have finding for this situation only. */
  onAddPathwayShouldNotHave?: (anchor?: HTMLElement) => void;
  /** Resolved DEMOGRAPHIC leaf whose inline age/sex editor is expanded. */
  expandedDemographicNode?: EditableLogicNode | null;
  /** Resolved OBSERVATION leaf whose inline operator/value/unit editor is expanded. */
  expandedObservationNode?: EditableLogicNode | null;
  /** Chip click inside the expanded ObservationRow to swap the observable. */
  onSelectObservation?: (nodeId: string, anchor?: HTMLElement | null) => void;
  /** Tree problems in this pathway with no guideline text row of their own. */
  problemIssues?: ValidationIssue[];
  onRemoveProblem?: (nodeId: string) => void;
  /** NG12 1.7.1 weighted companion checklist on this boundary. */
  weightedChecklist?: WeightedChecklistView | null;
  onExpandWeightedChecklist?: () => void;
}

export default function StepPathwayConditions({
  pathwayIndex,
  pathwayCount,
  pathwayLetter,
  nextPathwayLetter = null,
  boundary,
  recommendationText,
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
  onAddPathwayObservation,
  shouldNotHaveLeaves = [],
  onAddPathwayShouldNotHave,
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
  const trimmedQuote = (recommendationText || boundary.text).trim();
  const standaloneHighlightItem: RecommendationStructureItem | null =
    items.length === 0 && onAddMultiConcept && trimmedQuote
      ? { text: trimmedQuote, start: 0, end: trimmedQuote.length }
      : null;
  const rowExtra = onAddMultiConcept
    ? (item: RecommendationStructureItem) => (
        <RowMultiCodeHighlight
          item={item}
          contextText={recommendationText || boundary.text}
          onAddCriterion={(criterion, selectedText) =>
            onAddMultiConcept(item, criterion, selectedText)
          }
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

      <ShouldNotHaveSection
        leaves={shouldNotHaveLeaves}
        onEdit={onEditConfirmedLeaf}
        onRemove={onRemoveConfirmedLeaf ? (id) => {
          const node = shouldNotHaveLeaves.find((leaf) => leaf.node_id === id);
          if (node) onRemoveConfirmedLeaf(node);
        } : undefined}
      />

      {(onAddPathwayObservation || onAddPathwayShouldNotHave) && (
        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
          {onAddPathwayObservation && (
            <Tooltip title={WIZARD_TOOLTIPS.addLabValueSituation}>
              <Button
                variant="outlined"
                size="small"
                startIcon={<AddRoundedIcon fontSize="small" />}
                onClick={onAddPathwayObservation}
                aria-label={STEP_PATHWAY_CONDITIONS.addLabValueAriaLabel}
              >
                {STEP_PATHWAY_CONDITIONS.addLabValueLabel}
              </Button>
            </Tooltip>
          )}
          {onAddPathwayShouldNotHave && (
            <ShouldNotHaveButton
              ariaLabel={STEP_PATHWAY_CONDITIONS.addShouldNotHaveAriaLabel}
              tooltip={WIZARD_TOOLTIPS.addShouldNotHaveSituation}
              onClick={onAddPathwayShouldNotHave}
            />
          )}
        </Stack>
      )}

      {onAddPathwayDemographic && onUpdatePathway && (
        <PathwayDemographicsPanel
          demographics={pathwayDemographics}
          onAdd={onAddPathwayDemographic}
          onUpdate={onUpdatePathway}
        />
      )}

      <WeightedChecklistSection
        weightedChecklist={weightedChecklist}
        onExpandWeightedChecklist={onExpandWeightedChecklist}
      />

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
      ) : items.length > 0 ? (
        <ListRecommendationView
          items={items}
          getRowResolution={getRowResolution}
          onRowClick={onRowClick}
          renderRowExtra={rowExtra}
        />
      ) : (
        standaloneHighlightItem &&
        onAddMultiConcept && (
          <RowMultiCodeHighlight
            item={standaloneHighlightItem}
            contextText={trimmedQuote}
            onAddCriterion={(criterion, selectedText) =>
              onAddMultiConcept(standaloneHighlightItem, criterion, selectedText)
            }
          />
        )
      )}

      {onRemoveProblem &&
        problemIssues.map((issue) => (
          <ProblemNodeRow key={issue.nodeId} issue={issue} onRemove={onRemoveProblem} />
        ))}

      <ExpandedConditionEditors
        expandedDemographicNode={expandedDemographicNode}
        expandedObservationNode={expandedObservationNode}
        onUpdatePathway={onUpdatePathway}
        onSelectObservation={onSelectObservation}
      />

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
