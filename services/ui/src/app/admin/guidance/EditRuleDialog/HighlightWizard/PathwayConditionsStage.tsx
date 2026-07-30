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
 * Wires StepPathwayConditions (presentation) to the real tree for one
 * pathway at a time: resolves each row against the pathway's own
 * leaves, routes a click to either "edit the existing leaf" or "open
 * the add flow pre-filled from this row's text", and lazily
 * materializes an AT_LEAST subgroup the first time a cluster grouping
 * choice actually needs one -- deferring that one leaf's own add
 * until the subgroup lands in the next `tree` prop update, via
 * `pendingClusterAdd`, rather than requiring a second click.
 */
import { useEffect, useMemo, useState } from "react";

import { canHaveChildren, findAllValidationErrors, findValidationError } from "../treeOps";
import type { LogicCriterion, NodeUpdate } from "../types";
import type { RecommendationStructureItem, PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import { detectVaguePhrase } from "../vaguePhrases";
import {
  pathwayDemographicChildren,
  type PathwayDemographicField,
} from "./PathwayDemographicsPanel";
import StepPathwayConditions, { type ClusterGrouping } from "./StepPathwayConditions";
import {
  buildConfirmedSummaries,
  buildPathwayRows,
  buildRowResolver,
  decideRowClickTarget,
  findClusterSubgroupByRole,
  findNodeById,
  flattenPathwayItems,
  orderPathwayNodesByBoundary,
  pathwayConfirmedLeaves,
  pathwayGroupingKey,
  pathwayLetterAt,
  pathwayTextWindow,
  readMaterializedPathways,
  withReifiedPathwayClusters,
} from "./wizardMapping";
import { withReifiedWeightedChecklist } from "./weightedChecklist";
import { useCopyAcrossOffer } from "./useCopyAcrossOffer";
import type { EditableLogicNode } from "../types";
import { STEP_PATHWAY_CONDITIONS } from "./copy";

/** Concrete findings keep multi-pick; vague phrases open ConceptSearchPanel
 *  so "Ask LEO for ideas" is available (NG12 1.7.2 dermoscopy). */
function useMultiPickForRowText(text: string): boolean {
  return !detectVaguePhrase(text).isVague;
}

function pathwayDemographicBlockReason(
  demographics: EditableLogicNode[],
): string | null {
  for (const demo of demographics) {
    const err = findValidationError(demo);
    if (err) return err;
  }
  return null;
}

/**
 * Problems in this pathway's own subtree that have no visible row of
 * their own -- almost always an empty AT_LEAST subgroup a reviewer
 * created (e.g. via "only one needs to match") and then backed out of
 * before adding anything to it. `buildPathwayRows` only produces rows
 * from guideline TEXT, so a leaf-less group like this never gets one;
 * without this, the problem is invisible even though Save is blocked
 * on it. Filters out:
 *   - anything a row already resolves to (a normal unresolved row is
 *     never double-reported -- `ListRecommendationView` already shows
 *     its own "+ add" affordance for it);
 *   - anything covered by `PathwayDemographicsPanel`'s own rows/caption;
 *   - the pathway container's OWN emptiness -- a freshly materialized,
 *     not-yet-filled-in pathway is always "empty" in tree terms, but
 *     `boundary`'s guideline text always has its own row(s), so
 *     `unresolvedBlockedReason` already tells the reviewer exactly
 *     that ("N rows still need a code"). Reporting it again here would
 *     fire on every ordinary in-progress pathway, not just genuine
 *     leftovers.
 */
function pathwayProblemIssues(
  pathwayNode: EditableLogicNode,
  boundary: PathwayTextBoundary,
  getRowResolution: (item: RecommendationStructureItem) => { nodeId?: string | null } | undefined,
  pathwayDemographics: EditableLogicNode[],
) {
  const { items } = buildPathwayRows(boundary);
  const alreadyVisibleIds = new Set([
    pathwayNode.node_id,
    ...flattenPathwayItems(items)
      .map((item) => getRowResolution(item)?.nodeId)
      .filter((id): id is string => !!id),
    ...pathwayDemographics.map((d) => d.node_id),
  ]);
  return findAllValidationErrors(pathwayNode).filter(
    (issue) => issue.nodeId && !alreadyVisibleIds.has(issue.nodeId),
  );
}

interface PendingClusterAdd {
  pathwayNodeId: string;
  text: string;
  /** See `EditableLogicNode.cluster_role`'s doc comment. */
  role: "lead" | "trailing";
  /** The row click that triggered this deferred add -- replayed once
   *  the fresh AT_LEAST subgroup lands, so the search popover still
   *  opens next to what the reviewer actually clicked instead of a
   *  default position. */
  anchor: HTMLElement;
}

interface Props {
  tree: EditableLogicNode;
  recommendationText?: string | null;
  boundaries: PathwayTextBoundary[];
  pathwayIndex: number;
  /** Keyed by `pathwayGroupingKey` (the pathway's own stable
   *  `pathway_key`, not the raw array index) -- see that helper's
   *  doc comment. */
  clusterGroupings: Record<string, ClusterGrouping>;
  onSetClusterGrouping: (pathwayKey: string, grouping: ClusterGrouping) => void;
  /** Same as `clusterGroupings`/`onSetClusterGrouping` but for a
   *  SEPARATE lead-or cluster (see StepPathwayConditions's
   *  `leadClusterGrouping` prop doc comment). */
  leadClusterGroupings: Record<string, ClusterGrouping>;
  onSetLeadClusterGrouping: (pathwayKey: string, grouping: ClusterGrouping) => void;
  /** See `WizardState.dismissedCopyAcrossOffers`'s doc comment --
   *  lifted out of a local hook useState so it survives remounts of
   *  this component within the same wizard session. */
  dismissedCopyAcrossOffers: Set<string>;
  onDismissCopyAcrossOffer: (pathwayKey: string) => void;
  /** Expand a weighted companion checklist into major/minor feature rows. */
  onExpandWeightedChecklist?: () => void;
  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
    initialQuery?: string,
    multiPick?: boolean,
  ) => void;
  /**
   * Opens the add/remove/depth synonym editor (ConceptSynonymDialog)
   * for a CONCEPT leaf that already has a matched code. Clicking an
   * already-resolved row is the wizard's only "edit this" affordance
   * -- unlike a chip in the Advanced editor, there is no separate
   * "swap" vs "tune" split here, so it must open straight into
   * add/remove rather than a single-pick override that would discard
   * every other code already on the leaf.
   */
  onEditConcept: (nodeId: string) => void;
  onConfirmPathway: () => void;
}

/** `boundaries.length === 1` only ever comes from Step 2's "No, it
 *  applies the same way to everyone" exit (see wizardState.ts's
 *  CONFIRM_NO_SPLIT) -- there is no OR to read pathways from, the
 *  whole tree IS the one situation. When there ARE multiple
 *  boundaries, re-anchor the OR's children to those boundaries by
 *  content (see `orderPathwayNodesByBoundary`) so a mis-ordered
 *  AI-drafted tree cannot put situation C's leaves under letter A. */
export function resolvePathwayNodes(
  tree: EditableLogicNode,
  boundaries: PathwayTextBoundary[],
  recommendationText: string | null | undefined,
): EditableLogicNode[] {
  if (boundaries.length === 1) return [tree];
  const containers = readMaterializedPathways(tree, boundaries.length);
  return orderPathwayNodesByBoundary(containers, boundaries, recommendationText);
}

function usePendingClusterAdd(
  tree: EditableLogicNode,
  onRequestAdd: Props["onRequestAdd"],
): [PendingClusterAdd | null, (p: PendingClusterAdd) => void] {
  const [pending, setPending] = useState<PendingClusterAdd | null>(null);
  useEffect(() => {
    if (!pending) return;
    const pathway = findNodeById(tree, pending.pathwayNodeId);
    const subgroup = pathway ? findClusterSubgroupByRole(pathway, pending.role) : null;
    if (subgroup) {
      onRequestAdd(
        subgroup.node_id,
        pending.anchor,
        pending.text,
        useMultiPickForRowText(pending.text),
      );
      setPending(null);
    }
  }, [tree, pending, onRequestAdd]);
  return [pending, setPending];
}

export default function PathwayConditionsStage({
  tree,
  recommendationText,
  boundaries,
  pathwayIndex,
  clusterGroupings,
  onSetClusterGrouping,
  leadClusterGroupings,
  onSetLeadClusterGrouping,
  dismissedCopyAcrossOffers,
  onDismissCopyAcrossOffer,
  onExpandWeightedChecklist,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onEditConcept,
  onConfirmPathway,
}: Props) {
  const pathwayNodes = useMemo(
    () => resolvePathwayNodes(tree, boundaries, recommendationText),
    [tree, boundaries, recommendationText],
  );
  const pathwayNode = pathwayNodes[pathwayIndex];
  const boundary = boundaries[pathwayIndex];
  const pathwayKey = pathwayGroupingKey(pathwayNode, pathwayIndex);
  const [, setPendingClusterAdd] = usePendingClusterAdd(tree, onRequestAdd);
  // Which DEMOGRAPHIC / OBSERVATION leaf's inline editor (see
  // `StepPathwayConditions`'s `expandedDemographicNode` /
  // `expandedObservationNode` props) is currently open -- those
  // kinds have no synonym set (and for DEMOGRAPHIC, no search swap)
  // to hand off to, so re-clicking toggles the inline editor instead
  // of calling `onSelectNode`. OBSERVATION still uses onSelectNode
  // from the chip inside ObservationRow to swap the observable.
  const [expandedDemographicNodeId, setExpandedDemographicNodeId] = useState<string | null>(
    null,
  );
  const [expandedObservationNodeId, setExpandedObservationNodeId] = useState<string | null>(
    null,
  );

  // See `pathwayTextWindow` -- nested cluster items sit past a
  // structural lead `<li>`'s own end, so row resolution must use the
  // extended window shared with GuidelineQuotePanel.
  const textWindow = useMemo(
    () =>
      pathwayTextWindow(
        boundaries,
        pathwayIndex,
        recommendationText?.length ?? boundary?.end ?? 0,
      ),
    [boundaries, pathwayIndex, recommendationText, boundary?.end],
  );

  const getRowResolution = useMemo(
    () =>
      pathwayNode ? buildRowResolver(pathwayNode, recommendationText, textWindow) : () => undefined,
    [pathwayNode, recommendationText, textWindow],
  );

  const { offer: copyAcrossOffer, acceptOffer, dismissOffer } = useCopyAcrossOffer({
    tree,
    boundaries,
    pathwayIndex,
    pathwayKey,
    pathwayNodes,
    targetPathwayNode: pathwayNode ?? tree,
    recommendationText,
    clusterGroupings,
    leadClusterGroupings,
    onSetClusterGrouping,
    onSetLeadClusterGrouping,
    dismissedCopyAcrossOffers,
    onDismissCopyAcrossOffer,
    onUpdate,
  });

  if (!pathwayNode || !boundary) return null;

  const pathwayRows = buildPathwayRows(boundary);
  const trailingTermCount = pathwayRows.leadCluster
    ? pathwayRows.items.length - pathwayRows.leadCluster.items.length
    : (pathwayRows.items[0]?.children ?? pathwayRows.items).length;
  const trailingSubgroup = findClusterSubgroupByRole(pathwayNode, "trailing");
  const effectiveClusterMin =
    trailingSubgroup?.min ?? pathwayRows.suggestedMin ?? 1;

  const pathwayDemographics = pathwayDemographicChildren(pathwayNode);
  const demographicBlockedReason = pathwayDemographicBlockReason(pathwayDemographics);
  const problemIssues = pathwayProblemIssues(
    pathwayNode,
    boundary,
    getRowResolution,
    pathwayDemographics,
  );
  // Leaves already represented by a guideline-text row stay out of this
  // list (they would just duplicate the row above). Everything else --
  // tree-rehydrated situations with no text rows at all, OR a CONCEPT /
  // OBSERVATION authored via Advanced/Sentence that never matched a
  // text row (no source_row_text, preferred term shares little wording
  // with the guideline) -- must still be reviewable here, otherwise it
  // silently vanishes from Step 3 even though Review's summary shows it.
  const coveredByRowIds = new Set(
    flattenPathwayItems(pathwayRows.items)
      .map((item) => getRowResolution(item)?.nodeId)
      .filter((id): id is string => !!id),
  );
  const confirmedLeaves = pathwayConfirmedLeaves(pathwayNode).filter(
    (leaf) => !coveredByRowIds.has(leaf.node_id),
  );

  function handleAddPathwayDemographic(field: PathwayDemographicField) {
    onUpdate({
      kind: "add_demographic",
      parentNodeId: pathwayNode.node_id,
      field,
    });
  }

  function handleAddPathwayObservation() {
    onUpdate({ kind: "add_observation", parentNodeId: pathwayNode.node_id });
  }

  function handleEditConfirmedLeaf(node: EditableLogicNode) {
    if (node.kind === "CONCEPT") {
      onEditConcept(node.node_id);
    } else if (node.kind === "OBSERVATION") {
      setExpandedDemographicNodeId(null);
      setExpandedObservationNodeId((prev) => (prev === node.node_id ? null : node.node_id));
    } else {
      onSelectNode(node.node_id);
    }
  }

  function handleRemoveConfirmedLeaf(node: EditableLogicNode) {
    onUpdate({ kind: "remove", nodeId: node.node_id });
  }
  // Removing the pathway's own sole leaf (a bare-leaf situation like
  // NG12 1.3.1's "abdominal mass" pathway, before any child was ever
  // added) would delete the whole situation out from under the
  // reviewer with no confirmation -- there is no wrapping AND left
  // behind to show "this situation now has 0 conditions". Only offer
  // removal once the pathway is a real group with siblings left over
  // afterwards; `appendChildPromotingLeaf` already handles promoting a
  // bare leaf into one the first time something else gets added to it.
  const canRemoveConfirmedLeaves = canHaveChildren(pathwayNode.kind);

  function handleRemoveProblem(nodeId: string) {
    onUpdate({ kind: "remove", nodeId });
  }

  function parentForClusterAdd(item: RecommendationStructureItem): string {
    const decision = decideRowClickTarget(
      pathwayNode,
      boundary,
      item,
      undefined,
      clusterGroupings[pathwayKey],
      leadClusterGroupings[pathwayKey],
    );
    if (decision.action === "add") return decision.parentNodeId;
    if (decision.action === "create_subgroup_then_add") {
      onUpdate({
        kind: "add_group",
        parentNodeId: decision.pathwayNodeId,
        groupKind: "AT_LEAST",
        clusterRole: decision.role,
        min: decision.role === "trailing" ? effectiveClusterMin : 1,
      });
      // Subgroup id is not known until the next tree render -- fall
      // back to the pathway; Confirm's reify step will reparent.
      return pathwayNode.node_id;
    }
    return pathwayNode.node_id;
  }

  // Highlighted sub-phrases follow the same lead/trailing AT_LEAST
  // routing as whole-row picks so Situation D cannot flatten nausea
  // and vomiting under a bare AND via the multi-code highlighter.
  function handleAddMultiConcept(
    item: RecommendationStructureItem,
    criterion: LogicCriterion,
  ) {
    onUpdate({
      kind: "add_concept",
      parentNodeId: parentForClusterAdd(item),
      criterion,
      // See EditableLogicNode.source_row_text's doc comment -- lets
      // this row resolve reliably even when the picked code(s) share
      // no wording with `item.text`.
      sourceRowText: item.text,
    });
  }

  function handleRowClick(item: RecommendationStructureItem, anchor: HTMLElement) {
    const decision = decideRowClickTarget(
      pathwayNode,
      boundary,
      item,
      getRowResolution(item),
      clusterGroupings[pathwayKey],
      leadClusterGroupings[pathwayKey],
    );
    if (decision.action === "select") {
      // A CONCEPT leaf gets the full add/remove/depth editor -- see
      // `onEditConcept`'s doc comment. A DEMOGRAPHIC leaf has neither
      // a synonym set nor a search-swap flow -- it toggles the inline
      // age/sex editor. An OBSERVATION leaf toggles the inline
      // operator/value/unit editor (chip inside still swaps via
      // onSelectNode); other kinds keep the single-pick swap.
      const existing = findNodeById(tree, decision.nodeId);
      if (existing?.kind === "CONCEPT") {
        onEditConcept(decision.nodeId);
      } else if (existing?.kind === "DEMOGRAPHIC") {
        setExpandedObservationNodeId(null);
        setExpandedDemographicNodeId((prev) => (prev === decision.nodeId ? null : decision.nodeId));
      } else if (existing?.kind === "OBSERVATION") {
        setExpandedDemographicNodeId(null);
        setExpandedObservationNodeId((prev) => (prev === decision.nodeId ? null : decision.nodeId));
      } else {
        onSelectNode(decision.nodeId, anchor);
      }
    } else if (decision.action === "add") {
      onRequestAdd(
        decision.parentNodeId,
        anchor,
        decision.text,
        useMultiPickForRowText(decision.text),
      );
    } else {
      onUpdate({
        kind: "add_group",
        parentNodeId: decision.pathwayNodeId,
        groupKind: "AT_LEAST",
        clusterRole: decision.role,
        min: decision.role === "trailing" ? effectiveClusterMin : 1,
      });
      setPendingClusterAdd({
        pathwayNodeId: decision.pathwayNodeId,
        text: decision.text,
        role: decision.role,
        anchor,
      });
    }
  }

  function syncExistingClusterMin(role: "lead" | "trailing", min: number) {
    const existing = findClusterSubgroupByRole(pathwayNode, role);
    if (!existing || existing.min === min) return;
    onUpdate({ kind: "set_min", nodeId: existing.node_id, min });
  }

  function handleChooseGrouping(grouping: ClusterGrouping, min?: number) {
    onSetClusterGrouping(pathwayKey, grouping);
    // Do NOT mint an empty AT_LEAST shell here. An empty shell trips
    // "One of the groups is empty" on Save / the issue banner while
    // the reviewer is still coding rows. The first cluster-row pick
    // creates the subgroup via create_subgroup_then_add; Confirm's
    // reify also builds AT_LEAST only when leaves exist. If a shell
    // already exists (copy-across / prior coding), keep its min in sync.
    if (grouping === "AT_LEAST") {
      syncExistingClusterMin(
        "trailing",
        min ?? pathwayRows.suggestedMin ?? 1,
      );
    }
  }

  function handleChooseLeadGrouping(grouping: ClusterGrouping) {
    onSetLeadClusterGrouping(pathwayKey, grouping);
    if (grouping === "AT_LEAST") syncExistingClusterMin("lead", 1);
  }

  function handleSetClusterMin(min: number) {
    if (!trailingSubgroup) return;
    onUpdate({ kind: "set_min", nodeId: trailingSubgroup.node_id, min });
  }

  function handleConfirmPathway() {
    const checklist = boundary.weightedChecklist;
    if (checklist?.expanded) {
      onUpdate({
        kind: "replace_root",
        node: withReifiedWeightedChecklist(tree, checklist),
      });
      onConfirmPathway();
      return;
    }
    // One atomic replace_root so lead/trailing leaves coded under the
    // pathway AND (before grouping was chosen, or via multi-code add)
    // are moved into the right AT_LEAST shells for Situations C and D.
    onUpdate({
      kind: "replace_root",
      node: withReifiedPathwayClusters(
        tree,
        pathwayNode.node_id,
        boundary,
        clusterGroupings[pathwayKey],
        leadClusterGroupings[pathwayKey],
        recommendationText,
      ),
    });
    onConfirmPathway();
  }

  const checklist = boundary.weightedChecklist;
  const instrumentBlocked =
    checklist && !checklist.expanded
      ? STEP_PATHWAY_CONDITIONS.weightedChecklistInstrumentBlocked
      : null;

  return (
    <StepPathwayConditions
      pathwayIndex={pathwayIndex + 1}
      pathwayCount={boundaries.length}
      pathwayLetter={pathwayLetterAt(pathwayIndex)}
      nextPathwayLetter={
        pathwayIndex + 1 < boundaries.length ? pathwayLetterAt(pathwayIndex + 1) : null
      }
      boundary={boundary}
      getRowResolution={getRowResolution}
      onRowClick={handleRowClick}
      onAddMultiConcept={handleAddMultiConcept}
      clusterGrouping={clusterGroupings[pathwayKey]}
      onChooseGrouping={handleChooseGrouping}
      clusterMin={trailingSubgroup?.min ?? pathwayRows.suggestedMin ?? 1}
      suggestedClusterMin={pathwayRows.suggestedMin ?? 1}
      clusterTermCount={trailingTermCount}
      onSetClusterMin={handleSetClusterMin}
      leadClusterGrouping={leadClusterGroupings[pathwayKey]}
      onChooseLeadGrouping={handleChooseLeadGrouping}
      confirmedSummaries={buildConfirmedSummaries(pathwayNodes, pathwayIndex)}
      onConfirmPathway={handleConfirmPathway}
      confirmBlockedReason={instrumentBlocked ?? demographicBlockedReason}
      onExpandWeightedChecklist={onExpandWeightedChecklist}
      weightedChecklist={checklist ?? null}
      copyAcrossOffer={
        copyAcrossOffer
          ? { sourceLetter: pathwayLetterAt(copyAcrossOffer.sourceIndex), count: copyAcrossOffer.count }
          : null
      }
      onAcceptCopyAcross={acceptOffer}
      onDismissCopyAcross={dismissOffer}
      pathwayDemographics={pathwayDemographics}
      onAddPathwayDemographic={handleAddPathwayDemographic}
      onUpdatePathway={onUpdate}
      confirmedLeaves={confirmedLeaves}
      onEditConfirmedLeaf={confirmedLeaves.length > 0 ? handleEditConfirmedLeaf : undefined}
      onRemoveConfirmedLeaf={canRemoveConfirmedLeaves ? handleRemoveConfirmedLeaf : undefined}
      onAddPathwayObservation={handleAddPathwayObservation}
      problemIssues={problemIssues}
      onRemoveProblem={handleRemoveProblem}
      expandedDemographicNode={
        expandedDemographicNodeId ? findNodeById(tree, expandedDemographicNodeId) : null
      }
      expandedObservationNode={
        expandedObservationNodeId ? findNodeById(tree, expandedObservationNodeId) : null
      }
      onSelectObservation={onSelectNode}
    />
  );
}
