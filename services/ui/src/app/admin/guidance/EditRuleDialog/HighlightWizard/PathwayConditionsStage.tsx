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

import { findValidationError } from "../treeOps";
import type { LogicCriterion, NodeUpdate } from "../types";
import type { RecommendationStructureItem, PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import {
  pathwayDemographicChildren,
  type PathwayDemographicField,
} from "./PathwayDemographicsPanel";
import StepPathwayConditions, { type ClusterGrouping } from "./StepPathwayConditions";
import {
  buildConfirmedSummaries,
  buildRowResolver,
  decideRowClickTarget,
  findClusterSubgroupByRole,
  findNodeById,
  orderPathwayNodesByBoundary,
  pathwayLetterAt,
  pathwayTextWindow,
  readMaterializedPathways,
  withReifiedPathwayClusters,
} from "./wizardMapping";
import { useCopyAcrossOffer } from "./useCopyAcrossOffer";
import type { EditableLogicNode } from "../types";

function pathwayDemographicBlockReason(
  demographics: EditableLogicNode[],
): string | null {
  for (const demo of demographics) {
    const err = findValidationError(demo);
    if (err) return err;
  }
  return null;
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
  clusterGroupings: Record<number, ClusterGrouping>;
  onSetClusterGrouping: (pathwayIndex: number, grouping: ClusterGrouping) => void;
  /** Same as `clusterGroupings`/`onSetClusterGrouping` but for a
   *  SEPARATE lead-or cluster (see StepPathwayConditions's
   *  `leadClusterGrouping` prop doc comment). */
  leadClusterGroupings: Record<number, ClusterGrouping>;
  onSetLeadClusterGrouping: (pathwayIndex: number, grouping: ClusterGrouping) => void;
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
function resolvePathwayNodes(
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
      onRequestAdd(subgroup.node_id, pending.anchor, pending.text, true);
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
  const [, setPendingClusterAdd] = usePendingClusterAdd(tree, onRequestAdd);

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
    pathwayNodes,
    targetPathwayNode: pathwayNode ?? tree,
    recommendationText,
    clusterGroupings,
    leadClusterGroupings,
    onSetClusterGrouping,
    onSetLeadClusterGrouping,
    onUpdate,
  });

  if (!pathwayNode || !boundary) return null;

  const pathwayDemographics = pathwayDemographicChildren(pathwayNode);
  const demographicBlockedReason = pathwayDemographicBlockReason(pathwayDemographics);

  function handleAddPathwayDemographic(field: PathwayDemographicField) {
    onUpdate({
      kind: "add_demographic",
      parentNodeId: pathwayNode.node_id,
      field,
    });
  }

  function parentForClusterAdd(item: RecommendationStructureItem): string {
    const decision = decideRowClickTarget(
      pathwayNode,
      boundary,
      item,
      undefined,
      clusterGroupings[pathwayIndex],
      leadClusterGroupings[pathwayIndex],
    );
    if (decision.action === "add") return decision.parentNodeId;
    if (decision.action === "create_subgroup_then_add") {
      onUpdate({
        kind: "add_group",
        parentNodeId: decision.pathwayNodeId,
        groupKind: "AT_LEAST",
        clusterRole: decision.role,
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
      clusterGroupings[pathwayIndex],
      leadClusterGroupings[pathwayIndex],
    );
    if (decision.action === "select") {
      // A CONCEPT leaf gets the full add/remove/depth editor -- see
      // `onEditConcept`'s doc comment. Any other already-resolved
      // leaf kind (DEMOGRAPHIC, OBSERVATION) has no synonym set of
      // its own, so it keeps the existing single-pick swap.
      const existing = findNodeById(tree, decision.nodeId);
      if (existing?.kind === "CONCEPT") {
        onEditConcept(decision.nodeId);
      } else {
        onSelectNode(decision.nodeId, anchor);
      }
    } else if (decision.action === "add") {
      onRequestAdd(decision.parentNodeId, anchor, decision.text, true);
    } else {
      onUpdate({
        kind: "add_group",
        parentNodeId: decision.pathwayNodeId,
        groupKind: "AT_LEAST",
        clusterRole: decision.role,
      });
      setPendingClusterAdd({
        pathwayNodeId: decision.pathwayNodeId,
        text: decision.text,
        role: decision.role,
        anchor,
      });
    }
  }

  function ensureClusterSubgroup(role: "lead" | "trailing") {
    if (findClusterSubgroupByRole(pathwayNode, role)) return;
    onUpdate({
      kind: "add_group",
      parentNodeId: pathwayNode.node_id,
      groupKind: "AT_LEAST",
      clusterRole: role,
    });
  }

  function handleChooseGrouping(grouping: ClusterGrouping) {
    onSetClusterGrouping(pathwayIndex, grouping);
    // Create the trailing shell as soon as Recommended is chosen so
    // Situation C's symptom picks attach under AT_LEAST(1), not the
    // pathway AND, without waiting for the first row click.
    if (grouping === "AT_LEAST") ensureClusterSubgroup("trailing");
  }

  function handleChooseLeadGrouping(grouping: ClusterGrouping) {
    onSetLeadClusterGrouping(pathwayIndex, grouping);
    if (grouping === "AT_LEAST") ensureClusterSubgroup("lead");
  }

  function handleConfirmPathway() {
    // One atomic replace_root so lead/trailing leaves coded under the
    // pathway AND (before grouping was chosen, or via multi-code add)
    // are moved into the right AT_LEAST shells for Situations C and D.
    onUpdate({
      kind: "replace_root",
      node: withReifiedPathwayClusters(
        tree,
        pathwayNode.node_id,
        boundary,
        clusterGroupings[pathwayIndex],
        leadClusterGroupings[pathwayIndex],
        recommendationText,
      ),
    });
    onConfirmPathway();
  }

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
      clusterGrouping={clusterGroupings[pathwayIndex]}
      onChooseGrouping={handleChooseGrouping}
      leadClusterGrouping={leadClusterGroupings[pathwayIndex]}
      onChooseLeadGrouping={handleChooseLeadGrouping}
      confirmedSummaries={buildConfirmedSummaries(pathwayNodes, pathwayIndex)}
      onConfirmPathway={handleConfirmPathway}
      confirmBlockedReason={demographicBlockedReason}
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
    />
  );
}
