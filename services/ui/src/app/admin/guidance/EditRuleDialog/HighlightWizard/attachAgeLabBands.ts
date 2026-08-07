/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-E5B04297
 *   DO: DO-C38E6184
 *   VT: VT-409A9A74
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-E5B04297")
 *
 * Attach an age x lab OR tree beside Always-true prerequisites.
 * Situations are only the age/lab bands; shared symptoms stay on Step 1.
 */

import { findPathwaySplit } from "../pathwayDetection";
import { freshNodeId } from "../treeOps";
import type { EditableLogicNode } from "../types";

/**
 * Merge a filled age/lab OR into the existing rule tree without wiping
 * Always-true (prerequisite) leaves. Replaces an existing pathway OR
 * when one is already present.
 */
export function attachAgeLabBandOr(
  tree: EditableLogicNode,
  bandOr: EditableLogicNode,
): EditableLogicNode {
  const split = findPathwaySplit(tree);
  if (split) {
    if (tree.node_id === split.orNode.node_id) return bandOr;
    return {
      ...tree,
      children: (tree.children ?? []).map((child) =>
        child.node_id === split.orNode.node_id ? bandOr : child,
      ),
    };
  }
  if (tree.kind === "AND") {
    return { ...tree, children: [...(tree.children ?? []), bandOr] };
  }
  return {
    node_id: freshNodeId(),
    kind: "AND",
    children: [tree, bandOr],
  };
}
