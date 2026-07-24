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

import type { LogicCriterion, NodeUpdate } from "../types";
import type { RecommendationStructureItem, PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import StepPathwayConditions, { type ClusterGrouping } from "./StepPathwayConditions";
import {
  buildConfirmedSummaries,
  buildRowResolver,
  decideRowClickTarget,
  findClusterSubgroupByRole,
  findNodeById,
  pathwayLetterAt,
  readMaterializedPathways,
} from "./wizardMapping";
import { useCopyAcrossOffer } from "./useCopyAcrossOffer";
import type { EditableLogicNode } from "../types";

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
  onConfirmPathway: () => void;
}

/** `boundaries.length === 1` only ever comes from Step 2's "No, it
 *  applies the same way to everyone" exit (see wizardState.ts's
 *  CONFIRM_NO_SPLIT) -- there is no OR to read pathways from, the
 *  whole tree IS the one situation. */
function resolvePathwayNodes(
  tree: EditableLogicNode,
  boundaryCount: number,
): EditableLogicNode[] {
  return boundaryCount === 1 ? [tree] : readMaterializedPathways(tree, boundaryCount);
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
  onConfirmPathway,
}: Props) {
  const pathwayNodes = useMemo(
    () => resolvePathwayNodes(tree, boundaries.length),
    [tree, boundaries.length],
  );
  const pathwayNode = pathwayNodes[pathwayIndex];
  const boundary = boundaries[pathwayIndex];
  const [, setPendingClusterAdd] = usePendingClusterAdd(tree, onRequestAdd);

  // A structural boundary's own [start, end) covers only the pathway's
  // OWN lead-in sentence -- a nested cluster's child items (e.g.
  // "nausea"/"vomiting" under pathway C) sit at LATER offsets, past
  // `boundary.end`, since NICE's flattened text places a `<li>`'s
  // nested `<ul>` after that `<li>`'s own paragraph. So the row-match
  // window must extend to wherever the NEXT pathway starts (or the
  // end of the text, for the last pathway), not just `boundary.end` --
  // otherwise a cluster child's own leaf would fall outside the
  // window and never resolve. See `buildRowResolver`'s doc comment for
  // why a window is needed here at all.
  const textWindow = useMemo(() => {
    if (boundaries.length <= 1 || !boundary) return undefined;
    const nextStart = boundaries[pathwayIndex + 1]?.start;
    return { start: boundary.start, end: nextStart ?? recommendationText?.length ?? boundary.end };
  }, [boundary, boundaries, pathwayIndex, recommendationText]);

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

  // A highlighted sub-phrase is an explicit "add one more, independent of
  // whatever this row already resolved to" action -- it always lands as a
  // new sibling directly under the pathway, never through the AT_LEAST
  // cluster routing handleRowClick below uses for whole-row picks.
  function handleAddMultiConcept(
    item: RecommendationStructureItem,
    criterion: LogicCriterion,
  ) {
    onUpdate({
      kind: "add_concept",
      parentNodeId: pathwayNode.node_id,
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
      onSelectNode(decision.nodeId, anchor);
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
      onChooseGrouping={(g) => onSetClusterGrouping(pathwayIndex, g)}
      leadClusterGrouping={leadClusterGroupings[pathwayIndex]}
      onChooseLeadGrouping={(g) => onSetLeadClusterGrouping(pathwayIndex, g)}
      confirmedSummaries={buildConfirmedSummaries(pathwayNodes, pathwayIndex)}
      onConfirmPathway={onConfirmPathway}
      copyAcrossOffer={
        copyAcrossOffer
          ? { sourceLetter: pathwayLetterAt(copyAcrossOffer.sourceIndex), count: copyAcrossOffer.count }
          : null
      }
      onAcceptCopyAcross={acceptOffer}
      onDismissCopyAcross={dismissOffer}
    />
  );
}
