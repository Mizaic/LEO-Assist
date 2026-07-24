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

import type { NodeUpdate } from "../types";
import type { RecommendationStructureItem, PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import StepPathwayConditions, { type ClusterGrouping } from "./StepPathwayConditions";
import {
  buildConfirmedSummaries,
  buildRowResolver,
  decideRowClickTarget,
  findClusterSubgroup,
  findNodeById,
  pathwayLetterAt,
  readMaterializedPathways,
} from "./wizardMapping";
import type { EditableLogicNode } from "../types";

interface PendingClusterAdd {
  pathwayNodeId: string;
  text: string;
}

interface Props {
  tree: EditableLogicNode;
  recommendationText?: string | null;
  boundaries: PathwayTextBoundary[];
  pathwayIndex: number;
  clusterGroupings: Record<number, ClusterGrouping>;
  onSetClusterGrouping: (pathwayIndex: number, grouping: ClusterGrouping) => void;
  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null, initialQuery?: string) => void;
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
    const subgroup = pathway ? findClusterSubgroup(pathway) : null;
    if (subgroup) {
      onRequestAdd(subgroup.node_id, undefined, pending.text);
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

  const getRowResolution = useMemo(
    () => (pathwayNode ? buildRowResolver(pathwayNode, recommendationText) : () => undefined),
    [pathwayNode, recommendationText],
  );

  if (!pathwayNode || !boundary) return null;

  function handleRowClick(item: RecommendationStructureItem) {
    const decision = decideRowClickTarget(
      pathwayNode,
      boundary,
      item,
      getRowResolution(item),
      clusterGroupings[pathwayIndex],
    );
    if (decision.action === "select") {
      onSelectNode(decision.nodeId);
    } else if (decision.action === "add") {
      onRequestAdd(decision.parentNodeId, undefined, decision.text);
    } else {
      onUpdate({ kind: "add_group", parentNodeId: decision.pathwayNodeId, groupKind: "AT_LEAST" });
      setPendingClusterAdd({ pathwayNodeId: decision.pathwayNodeId, text: decision.text });
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
      clusterGrouping={clusterGroupings[pathwayIndex]}
      onChooseGrouping={(g) => onSetClusterGrouping(pathwayIndex, g)}
      confirmedSummaries={buildConfirmedSummaries(pathwayNodes, pathwayIndex)}
      onConfirmPathway={onConfirmPathway}
    />
  );
}
