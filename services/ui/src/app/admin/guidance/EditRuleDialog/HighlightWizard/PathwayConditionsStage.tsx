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

import { findAllValidationErrors, findValidationError } from "../treeOps";
import type { LogicCriterion, NodeUpdate } from "../types";
import type { RecommendationStructureItem, PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
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
  pathwayGroupingKey,
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
  dismissedCopyAcrossOffers,
  onDismissCopyAcrossOffer,
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
  // Which DEMOGRAPHIC leaf's inline age/sex editor (see
  // `StepPathwayConditions`'s `expandedDemographicNodeId` prop) is
  // currently open -- a DEMOGRAPHIC row has no synonym set or search
  // swap to hand off to, so re-clicking it toggles this instead of
  // calling `onSelectNode` (which has nothing to open for it).
  const [expandedDemographicNodeId, setExpandedDemographicNodeId] = useState<string | null>(
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

  const pathwayDemographics = pathwayDemographicChildren(pathwayNode);
  const demographicBlockedReason = pathwayDemographicBlockReason(pathwayDemographics);
  const problemIssues = pathwayProblemIssues(
    pathwayNode,
    boundary,
    getRowResolution,
    pathwayDemographics,
  );

  function handleAddPathwayDemographic(field: PathwayDemographicField) {
    onUpdate({
      kind: "add_demographic",
      parentNodeId: pathwayNode.node_id,
      field,
    });
  }

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
      // a synonym set nor a search-swap flow to hand off to -- it
      // toggles the same inline age/sex editor Step 1's prerequisite
      // rows use (see `StepPathwayConditions`'s `renderRowExtra`).
      // OBSERVATION is the only kind left with the single-pick swap.
      const existing = findNodeById(tree, decision.nodeId);
      if (existing?.kind === "CONCEPT") {
        onEditConcept(decision.nodeId);
      } else if (existing?.kind === "DEMOGRAPHIC") {
        setExpandedDemographicNodeId((prev) => (prev === decision.nodeId ? null : decision.nodeId));
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
    onSetClusterGrouping(pathwayKey, grouping);
    // Create the trailing shell as soon as Recommended is chosen so
    // Situation C's symptom picks attach under AT_LEAST(1), not the
    // pathway AND, without waiting for the first row click.
    if (grouping === "AT_LEAST") ensureClusterSubgroup("trailing");
  }

  function handleChooseLeadGrouping(grouping: ClusterGrouping) {
    onSetLeadClusterGrouping(pathwayKey, grouping);
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
        clusterGroupings[pathwayKey],
        leadClusterGroupings[pathwayKey],
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
      clusterGrouping={clusterGroupings[pathwayKey]}
      onChooseGrouping={handleChooseGrouping}
      leadClusterGrouping={leadClusterGroupings[pathwayKey]}
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
      problemIssues={problemIssues}
      onRemoveProblem={handleRemoveProblem}
      expandedDemographicNode={
        expandedDemographicNodeId ? findNodeById(tree, expandedDemographicNodeId) : null
      }
    />
  );
}
