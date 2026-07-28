/**
 * Lift DEMOGRAPHIC leaves shared by every pathway AND up to Always true.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
import { findPathwaySplit } from "./pathwayDetection";
import { assignNodeIds } from "./treeOps";
import type { EditableLogicNode } from "./types";

/** Stable identity for a DEMOGRAPHIC leaf shared across pathway ANDs. */
function demographicSignature(node: EditableLogicNode): string | null {
  if (String(node.kind || "").toUpperCase() !== "DEMOGRAPHIC") return null;
  return [
    String(node.field ?? ""),
    String(node.operator ?? ""),
    String(node.value ?? ""),
    String(node.unit ?? ""),
  ].join("|");
}

/**
 * NG12 1.1.2 shape fix.
 *
 * Given:
 *   OR[
 *     AND[age>=40, AT_LEAST(min=2, symptoms)],
 *     AND[ever smoked, AT_LEAST(min=1, symptoms), age>=40],
 *   ]
 * Returns:
 *   AND[
 *     age>=40,
 *     OR[
 *       AND[AT_LEAST(min=2, symptoms)],
 *       AND[ever smoked, AT_LEAST(min=1, symptoms)],
 *     ],
 *   ]
 */
export function liftSharedPathwayDemographics(
  root: EditableLogicNode,
): EditableLogicNode {
  const split = findPathwaySplit(root);
  if (!split || split.prerequisites.length > 0) return root;

  const pathways = split.orNode.children ?? [];
  if (pathways.length < 2) return root;

  const perPathway = pathways.map((pathway) => {
    if (String(pathway.kind || "").toUpperCase() !== "AND") {
      return new Map<string, EditableLogicNode>();
    }
    const map = new Map<string, EditableLogicNode>();
    for (const child of pathway.children ?? []) {
      const sig = demographicSignature(child);
      if (sig && !map.has(sig)) map.set(sig, child);
    }
    return map;
  });

  const sharedSigs: string[] = [];
  for (const sig of perPathway[0].keys()) {
    if (perPathway.every((m) => m.has(sig))) sharedSigs.push(sig);
  }
  if (sharedSigs.length === 0) return root;

  const sharedNodes = sharedSigs.map((sig) => perPathway[0].get(sig)!);
  const sharedSet = new Set(sharedSigs);
  const strippedPathways = pathways.map((pathway) => {
    if (String(pathway.kind || "").toUpperCase() !== "AND") return pathway;
    return {
      ...pathway,
      children: (pathway.children ?? []).filter((child) => {
        const sig = demographicSignature(child);
        return !(sig && sharedSet.has(sig));
      }),
    };
  });
  const newOr: EditableLogicNode = {
    ...split.orNode,
    children: strippedPathways,
  };
  return assignNodeIds({
    kind: "AND",
    children: [...sharedNodes, newOr],
  });
}
