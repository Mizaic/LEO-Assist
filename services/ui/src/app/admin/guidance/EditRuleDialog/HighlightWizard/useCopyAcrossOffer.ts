/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * React glue for `pathwayCopyAcross.ts`'s pure plan-building: decides
 * whether to show the "copy across" offer for the pathway currently
 * on screen, and applies it once accepted.
 *
 * Applying a plan needs two tree updates in sequence when the target
 * pathway does not yet have a matching AT_LEAST subgroup: create the
 * subgroup(s) first, then -- once they exist in the next `tree` prop
 * update -- add each copied criterion under the right one. This
 * mirrors `PathwayConditionsStage`'s existing `usePendingClusterAdd`
 * pattern for a single manual add, generalised to a batch of items
 * that may target up to two different subgroups (a lead-or cluster
 * and a trailing "any of the following" cluster) plus the pathway
 * itself directly.
 */
import { useEffect, useMemo, useState } from "react";

import type { EditableLogicNode, LogicCriterion, NodeUpdate } from "../types";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import {
  buildCopyAcrossPlan,
  findCopyAcrossSource,
  type CopyAcrossMatch,
} from "./pathwayCopyAcross";
import {
  findClusterSubgroupByRole,
  findNodeById,
  pathwayGroupingKey,
  type ClusterGrouping,
} from "./wizardMapping";

interface PendingCopyItem {
  criterion: LogicCriterion;
  role: CopyAcrossMatch["role"];
}

interface PendingCopy {
  pathwayNodeId: string;
  items: PendingCopyItem[];
}

export interface CopyAcrossOffer {
  sourceIndex: number;
  count: number;
}

interface Params {
  tree: EditableLogicNode;
  boundaries: PathwayTextBoundary[];
  pathwayIndex: number;
  /** The TARGET pathway's own `pathwayGroupingKey` -- see that
   *  helper's doc comment. The SOURCE pathway's key is resolved
   *  internally from `pathwayNodes[sourceIndex]` since the source
   *  varies with `plan`. */
  pathwayKey: string;
  pathwayNodes: EditableLogicNode[];
  targetPathwayNode: EditableLogicNode;
  recommendationText: string | null | undefined;
  clusterGroupings: Record<string, ClusterGrouping>;
  leadClusterGroupings: Record<string, ClusterGrouping>;
  onSetClusterGrouping: (pathwayKey: string, grouping: ClusterGrouping) => void;
  onSetLeadClusterGrouping: (pathwayKey: string, grouping: ClusterGrouping) => void;
  dismissedCopyAcrossOffers: Set<string>;
  onDismissCopyAcrossOffer: (pathwayKey: string) => void;
  onUpdate: (update: NodeUpdate) => void;
}

function ensureSubgroup(
  targetPathwayNode: EditableLogicNode,
  role: "lead" | "trailing",
  onUpdate: (update: NodeUpdate) => void,
): void {
  if (findClusterSubgroupByRole(targetPathwayNode, role)) return;
  onUpdate({
    kind: "add_group",
    parentNodeId: targetPathwayNode.node_id,
    groupKind: "AT_LEAST",
    clusterRole: role,
  });
}

export function useCopyAcrossOffer({
  tree,
  boundaries,
  pathwayIndex,
  pathwayKey,
  pathwayNodes,
  targetPathwayNode,
  recommendationText,
  clusterGroupings,
  leadClusterGroupings,
  onSetClusterGrouping,
  onSetLeadClusterGrouping,
  dismissedCopyAcrossOffers,
  onDismissCopyAcrossOffer,
  onUpdate,
}: Params): {
  offer: CopyAcrossOffer | null;
  acceptOffer: () => void;
  dismissOffer: () => void;
} {
  const [pending, setPending] = useState<PendingCopy | null>(null);

  const plan = useMemo(() => {
    const sourceIndex = findCopyAcrossSource(boundaries, pathwayIndex);
    const sourcePathwayNode = sourceIndex === null ? null : pathwayNodes[sourceIndex];
    if (sourceIndex === null || !sourcePathwayNode) return null;
    const sourceKey = pathwayGroupingKey(sourcePathwayNode, sourceIndex);
    return buildCopyAcrossPlan({
      boundaries,
      targetIndex: pathwayIndex,
      sourcePathwayNode,
      recommendationText,
      sourceGrouping: clusterGroupings[sourceKey],
      sourceLeadGrouping: leadClusterGroupings[sourceKey],
    });
  }, [boundaries, pathwayIndex, pathwayNodes, recommendationText, clusterGroupings, leadClusterGroupings]);

  // Only offer on a pathway the reviewer has not touched yet -- once
  // any row is resolved or a grouping choice is made, the reviewer
  // is already working through it manually and a copy prompt would
  // just be noise (and could clobber an intentionally different
  // choice for what looks like, but is not, the same situation).
  const targetHasProgress =
    (targetPathwayNode.children?.length ?? 0) > 0 ||
    clusterGroupings[pathwayKey] !== undefined ||
    leadClusterGroupings[pathwayKey] !== undefined;

  const offer: CopyAcrossOffer | null =
    plan && !dismissedCopyAcrossOffers.has(pathwayKey) && !targetHasProgress
      ? { sourceIndex: plan.sourceIndex, count: plan.matches.length }
      : null;

  useEffect(() => {
    if (!pending) return;
    const pathway = findNodeById(tree, pending.pathwayNodeId);
    if (!pathway) return;
    const remaining: PendingCopyItem[] = [];
    for (const item of pending.items) {
      const parent = item.role === "direct" ? pathway : findClusterSubgroupByRole(pathway, item.role);
      if (!parent) {
        remaining.push(item);
        continue;
      }
      onUpdate({ kind: "add_concept", parentNodeId: parent.node_id, criterion: item.criterion });
    }
    setPending(remaining.length > 0 ? { ...pending, items: remaining } : null);
  }, [tree, pending, onUpdate]);

  function acceptOffer() {
    if (!plan) return;
    if (plan.groupingToApply) onSetClusterGrouping(pathwayKey, plan.groupingToApply);
    if (plan.leadGroupingToApply) onSetLeadClusterGrouping(pathwayKey, plan.leadGroupingToApply);

    const items: PendingCopyItem[] = plan.matches.map((m) => ({
      criterion: m.criterion,
      role: m.role,
    }));
    const neededRoles = new Set(items.map((i) => i.role));
    if (neededRoles.has("trailing")) ensureSubgroup(targetPathwayNode, "trailing", onUpdate);
    if (neededRoles.has("lead")) ensureSubgroup(targetPathwayNode, "lead", onUpdate);
    setPending({ pathwayNodeId: targetPathwayNode.node_id, items });
  }

  function dismissOffer() {
    onDismissCopyAcrossOffer(pathwayKey);
  }

  return { offer, acceptOffer, dismissOffer };
}
