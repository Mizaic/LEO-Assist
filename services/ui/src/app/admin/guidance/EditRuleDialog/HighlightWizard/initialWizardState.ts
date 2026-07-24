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
    step: "review",
    pathwayIndex: Math.max(0, boundaries.length - 1),
    boundaries,
  };
}
