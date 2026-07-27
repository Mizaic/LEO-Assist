/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * When a reviewer reopens a rule that already has situations filled in,
 * land on Review instead of forcing Step 1 again. Wizard session state
 * is not persisted -- only the logic tree is -- so we reconstruct a
 * Review-ready state from the tree + guideline wording.
 */
import { findPathwaySplit } from "../pathwayDetection";
import {
  splitPathways,
  type PathwayTextBoundary,
  type RecommendationStructure,
} from "../SentenceEditor/pathwayTextSplit";
import type { EditableLogicNode } from "../types";
import { INITIAL_WIZARD_STATE, type WizardState } from "./wizardState";
import type { ClusterGrouping } from "./StepPathwayConditions";
import { findClusterSubgroupByRole, pathwayGroupingKey } from "./wizardMapping";

function groupHasLeaves(node: EditableLogicNode): boolean {
  if (
    node.kind === "CONCEPT" ||
    node.kind === "DEMOGRAPHIC" ||
    node.kind === "OBSERVATION"
  ) {
    return true;
  }
  return (node.children ?? []).some(groupHasLeaves);
}

/**
 * Reconstructs `clusterGroupings`/`leadClusterGroupings` from the tree
 * itself so reopening a rule (or going Back from Review) does not
 * re-show "choose grouping" for a pathway that already has a real
 * AT_LEAST subgroup -- the map otherwise starts empty every session,
 * which risked the reviewer picking "AND" a second time for what
 * looked like a fresh decision and silently orphaning the existing
 * subgroup's leaves from row-matching (see wizard state-machine
 * stability plan section). Deliberately does NOT try to infer "AND"
 * for a subgroup-less pathway -- a genuinely undecided pathway (no
 * subgroup, no cluster leaves yet) must still prompt the reviewer,
 * and guessing wrong there is a worse outcome than asking once more.
 */
function inferGroupingsFromTree(
  pathways: EditableLogicNode[],
): Pick<WizardState, "clusterGroupings" | "leadClusterGroupings"> {
  const clusterGroupings: Record<string, ClusterGrouping> = {};
  const leadClusterGroupings: Record<string, ClusterGrouping> = {};
  pathways.forEach((pathwayNode, index) => {
    const key = pathwayGroupingKey(pathwayNode, index);
    if (findClusterSubgroupByRole(pathwayNode, "trailing")) {
      clusterGroupings[key] = "AT_LEAST";
    }
    if (findClusterSubgroupByRole(pathwayNode, "lead")) {
      leadClusterGroupings[key] = "AT_LEAST";
    }
  });
  return { clusterGroupings, leadClusterGroupings };
}

function synthesiseBoundaries(count: number): PathwayTextBoundary[] {
  return Array.from({ length: count }, (_, i) => ({
    text: `Situation ${String.fromCharCode(65 + i)}`,
    start: 0,
    end: 0,
    source: "heuristic" as const,
  }));
}

/**
 * Returns Review when every pathway already has at least one leaf;
 * otherwise the normal Step 1 start.
 */
export function buildInitialWizardState(
  tree: EditableLogicNode,
  recommendationText?: string | null,
  recommendationStructure?: RecommendationStructure | null,
): WizardState {
  const split = findPathwaySplit(tree);
  // Flat / single-situation trees still start at Step 1 -- only a
  // filled multi-pathway split is treated as "already built".
  if (!split) return INITIAL_WIZARD_STATE;

  const pathways = split.orNode.children ?? [];
  if (pathways.length === 0) return INITIAL_WIZARD_STATE;
  if (!pathways.every(groupHasLeaves)) return INITIAL_WIZARD_STATE;

  const detected = splitPathways(recommendationText, recommendationStructure);
  const boundaries =
    detected && detected.length === pathways.length
      ? detected
      : synthesiseBoundaries(pathways.length);

  return {
    ...INITIAL_WIZARD_STATE,
    ...inferGroupingsFromTree(pathways),
    step: "review",
    pathwayIndex: Math.max(0, boundaries.length - 1),
    boundaries,
  };
}
