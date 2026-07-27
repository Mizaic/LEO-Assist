/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Shared "is this an editable pathway split?" heuristic.
 *
 * An OR near the top of the tree with 2+ *branch* children is the
 * "patient must match one of these pathways" pattern (NICE
 * recommendations like NG12 routinely split into independent
 * symptom-set branches). Anything deeper than depth 1 is treated as a
 * regular nested OR so a card never recurses into another card layer.
 *
 * Critical distinction (NG12 1.1.3): a flat OR of leaf concepts under
 * age -- `AND[DEMOGRAPHIC(age>=40), OR[finding, finding, ...]]` -- is
 * ONE situation ("any of these findings"), not five pathways. Only
 * treat the OR as a pathway split when at least one child is itself a
 * group (AND / AT_LEAST / nested OR / NOT), which is the multi-branch
 * shape of NG12 1.1.2 / 1.2.9.
 *
 * This single definition is imported by every surface that needs to
 * agree on what counts as a pathway split:
 *  - RuleLogicView.tsx (read-only Check & approve view)
 *  - SentenceEditor/index.tsx (Simple prose canvas)
 *  - LogicTreeEditor/index.tsx (Advanced tree canvas)
 *
 * Before this extraction, LogicTreeEditor had its own narrower
 * literal-root-only check (`isPathwayRoot`) that missed pathway splits
 * nested one level down inside a demographic AND (for example NG12
 * 1.2.9's `AND[DEMOGRAPHIC(age>=55), OR[6 pathways]]`), so the same
 * rule could render as 6 lettered cards in one view and one nested
 * blob in another. Use this function everywhere instead of
 * re-implementing the check.
 */

/** Minimal structural shape both LogicTreeNode and EditableLogicNode satisfy. */
export interface PathwaySplitNode {
  kind: string;
  children?: PathwaySplitNode[];
}

const LEAF_KINDS = new Set(["CONCEPT", "DEMOGRAPHIC", "OBSERVATION"]);

function isGroupBranch(node: PathwaySplitNode): boolean {
  const kind = String(node.kind || "").toUpperCase();
  return kind === "AND" || kind === "OR" || kind === "AT_LEAST" || kind === "NOT";
}

function isLeafBranch(node: PathwaySplitNode): boolean {
  return LEAF_KINDS.has(String(node.kind || "").toUpperCase());
}

export function isPathwaySplit(node: PathwaySplitNode, depth: number): boolean {
  const kind = String(node.kind || "").toUpperCase();
  if (kind !== "OR") return false;
  if (depth > 1) return false;
  const children = node.children ?? [];
  if (children.length < 2) return false;
  // Flat OR of leaves = alternatives inside one situation (1.1.3).
  // Pathway split needs at least one grouped branch (1.1.2 / 1.2.9).
  if (children.every(isLeafBranch)) return false;
  return children.some(isGroupBranch);
}

/** Where the pathway-split OR lives within a tree, plus any sibling
 *  prerequisites (e.g. a demographic age check) that apply to every
 *  pathway and must render once, above the list, instead of inside
 *  pathway card A. */
export interface PathwaySplitLocation<T extends PathwaySplitNode> {
  /** The OR node to hand to the pathway list. */
  orNode: T;
  /** Sibling nodes that apply to every pathway below. */
  prerequisites: T[];
}

/**
 * Finds the pathway-split OR to render, whether it is the literal root
 * or nested one level inside a wrapping AND alongside prerequisite
 * siblings (NG12 1.2.9's shape). Returns null when the tree is not a
 * pathway split at all. Shared by LogicTreeEditor/index.tsx and
 * SentenceEditor/index.tsx so both canvases agree on the split point.
 */
export function findPathwaySplit<T extends PathwaySplitNode>(root: T): PathwaySplitLocation<T> | null {
  if (isPathwaySplit(root, 0)) {
    return { orNode: root, prerequisites: [] };
  }
  if (String(root.kind || "").toUpperCase() !== "AND") return null;
  const children = (root.children ?? []) as T[];
  const orIndex = children.findIndex((c) => isPathwaySplit(c, 1));
  if (orIndex < 0) return null;
  return {
    orNode: children[orIndex],
    prerequisites: children.filter((_, i) => i !== orIndex),
  };
}
