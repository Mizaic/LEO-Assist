/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * The glue between the wizard's ephemeral text-boundary state (Step
 * 2's proposed pathways, Step 3's rows) and the real, persisted
 * EditableLogicNode tree that every other surface (LogicTreeEditor,
 * SentenceEditor, the compiler) reads. Kept as plain functions, no
 * React, so the "does this row already have a matching leaf" and
 * "how do I turn N confirmed boundaries into N tree pathway groups"
 * decisions are unit-testable without mounting any component.
 *
 * Materialization never deletes or reorders existing tree content --
 * only ever appends. Reviewing an AI-drafted tree whose OR already
 * has the right number of pathway children is a pure read (no
 * mutation at all, so already-confirmed SNOMED matches inside those
 * pathways are always preserved); building from scratch, or an OR
 * with too few pathways, only ever adds the missing empty groups.
 */
import { findPathwaySplit } from "../pathwayDetection";
import { freshNodeId, mintPathwayKey } from "../treeOps";
import { conceptText, demographicToText, observationToText } from "../treeToSentence";
import type { EditableLogicNode, LogicNodeKind, NodeUpdate } from "../types";
import {
  cleanPathwayText,
  resolveAtLeastCluster,
  type PathwayTextBoundary,
  type RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";
import type { ListRowResolution } from "../SentenceEditor/ListRecommendationView";
import type { TextMatchRange } from "../SentenceEditor/recommendationTextMatch";
import { leafTextMatch } from "./leafTextMatch";

const LEAF_KINDS = new Set<LogicNodeKind>(["CONCEPT", "DEMOGRAPHIC", "OBSERVATION"]);

/** Whether a pathway's own "any of the following" cluster requires
 *  only one match (AT_LEAST, min=1) or every item (plain AND). The
 *  reviewer always confirms this explicitly in Step 3 -- see
 *  STEP_PATHWAY_CONDITIONS.clusterPrompt -- it is never inferred
 *  silently from the wording alone. Canonical home for this type is
 *  here (the pure logic layer); StepPathwayConditions re-exports it
 *  for backward-compatible imports from that file. */
export type ClusterGrouping = "AT_LEAST" | "AND";

const PATHWAY_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

/** Cosmetic A/B/C label for the pathway at this 0-based index --
 *  purely positional (see EditableLogicNode.pathway_key's own doc
 *  comment: the letter is NOT the pathway's stable identity). */
export function pathwayLetterAt(index: number): string {
  return PATHWAY_LETTERS[index % PATHWAY_LETTERS.length];
}

function collectLeaves(node: EditableLogicNode): EditableLogicNode[] {
  const leaves: EditableLogicNode[] = [];
  const walk = (n: EditableLogicNode): void => {
    if (LEAF_KINDS.has(n.kind)) {
      leaves.push(n);
      return;
    }
    for (const child of n.children ?? []) walk(child);
  };
  walk(node);
  return leaves;
}

/** Short plain-English label for one leaf's own value, reusing the
 *  same phrase-building as the prose canvas rather than a third copy
 *  of "how do we describe a DEMOGRAPHIC/OBSERVATION/CONCEPT leaf". */
export function leafDisplayTerm(node: EditableLogicNode): string {
  if (node.kind === "CONCEPT") return conceptText(node);
  if (node.kind === "DEMOGRAPHIC") return demographicToText(node);
  if (node.kind === "OBSERVATION" && node.observation) {
    return observationToText(node.observation);
  }
  return "";
}

/** Comma-joined summary of a pathway's own leaves, for Step 3's
 *  "Already confirmed: A: ..." rows once a pathway is done. */
export function pathwaySummaryText(pathwayNode: EditableLogicNode): string {
  const terms = collectLeaves(pathwayNode)
    .map(leafDisplayTerm)
    .filter((t) => t.length > 0);
  return terms.length > 0 ? terms.join(", ") : "(no conditions yet)";
}

/** The "Already confirmed" list for Step 3: every pathway strictly
 *  before `uptoIndex`, lettered in order. */
export function buildConfirmedSummaries(
  pathwayNodes: EditableLogicNode[],
  uptoIndex: number,
): Array<{ letter: string; summary: string }> {
  return pathwayNodes.slice(0, uptoIndex).map((node, i) => ({
    letter: pathwayLetterAt(i),
    summary: pathwaySummaryText(node),
  }));
}

function rangesOverlap(
  a: { start: number; end: number },
  b: { start: number; end: number },
): boolean {
  return a.start < b.end && b.start < a.end;
}

/**
 * Builds a `getRowResolution` closure for one pathway: does this row
 * (by its own `[start, end)` span in the shared recommendation text)
 * already have a matching leaf anywhere under this pathway node,
 * regardless of how deeply nested (a cluster's own AT_LEAST subgroup,
 * or a plain top-level AND leaf)? Computed once per pathway/text pair
 * rather than per row, since every row resolution needs the same scan.
 */
export function buildRowResolver(
  pathwayNode: EditableLogicNode,
  recommendationText: string | null | undefined,
): (row: RecommendationStructureItem) => ListRowResolution | undefined {
  const matches = collectLeaves(pathwayNode)
    .map((node) => ({ node, match: leafTextMatch(recommendationText, node) }))
    .filter(
      (entry): entry is { node: EditableLogicNode; match: TextMatchRange } =>
        !!entry.match,
    );

  return (row) => {
    const hit = matches.find((entry) => rangesOverlap(entry.match, row));
    if (!hit) return undefined;
    return {
      nodeId: hit.node.node_id,
      criterion: hit.node.criterion ?? null,
      preferredTerm: leafDisplayTerm(hit.node) || null,
    };
  };
}

/** True once every top-level row (and every nested cluster child) in
 *  `items` resolves to a real leaf -- the gate Step 3's "Confirm
 *  situation X" button checks before letting the reviewer move on. */
export function countUnresolvedRows(
  items: RecommendationStructureItem[],
  getRowResolution: (item: RecommendationStructureItem) => ListRowResolution | undefined,
): number {
  const flat: RecommendationStructureItem[] = [];
  const walk = (list: RecommendationStructureItem[]): void => {
    for (const item of list) {
      flat.push(item);
      if (item.children?.length) walk(item.children);
    }
  };
  walk(items);
  return flat.filter((item) => {
    const resolution = getRowResolution(item);
    return !(resolution?.criterion || resolution?.preferredTerm);
  }).length;
}

/**
 * Read-only: the pathway container nodes to hand to Step 3, in
 * boundary order, when the tree's OR already has at least
 * `boundaryCount` children. Returns `[]` when a tree mutation is
 * needed first (see `materializePathways`) -- the caller re-derives
 * this on the next render once that mutation lands.
 */
export function readMaterializedPathways(
  tree: EditableLogicNode,
  boundaryCount: number,
): EditableLogicNode[] {
  const split = findPathwaySplit(tree);
  const existing = split?.orNode.children ?? [];
  return existing.length >= boundaryCount ? existing.slice(0, boundaryCount) : [];
}

/**
 * Constructs a brand new OR-of-pathways skeleton, preserving whatever
 * the tree already contains as a sibling prerequisite rather than
 * discarding it. Used only the first time a rule with no pathway
 * split at all confirms 2+ boundaries in Step 2.
 */
export function buildRootWithFreshPathways(
  tree: EditableLogicNode,
  boundaryCount: number,
): EditableLogicNode {
  const pathways: EditableLogicNode[] = Array.from({ length: boundaryCount }, () => ({
    node_id: freshNodeId(),
    kind: "AND" as const,
    children: [],
    pathway_key: mintPathwayKey(),
  }));
  const or: EditableLogicNode = { node_id: freshNodeId(), kind: "OR", children: pathways };
  if (tree.kind === "AND") {
    return { ...tree, children: [...(tree.children ?? []), or] };
  }
  return { node_id: freshNodeId(), kind: "AND", children: [tree, or] };
}

/**
 * Ensures at least `boundaryCount` pathway groups exist, emitting the
 * minimum NodeUpdate(s) needed and nothing else. Returns the
 * immediately-available pathway nodes (non-empty only when nothing
 * needed to change); when a mutation was emitted, the caller must
 * wait for the next tree prop update and call
 * `readMaterializedPathways` again.
 */
export function materializePathways(
  tree: EditableLogicNode,
  boundaryCount: number,
  onUpdate: (update: NodeUpdate) => void,
): EditableLogicNode[] {
  const already = readMaterializedPathways(tree, boundaryCount);
  if (already.length > 0) return already;

  const split = findPathwaySplit(tree);
  if (split) {
    const missing = boundaryCount - (split.orNode.children?.length ?? 0);
    for (let i = 0; i < missing; i += 1) {
      onUpdate({ kind: "add_group", parentNodeId: split.orNode.node_id, groupKind: "AND" });
    }
    return [];
  }

  onUpdate({ kind: "replace_root", node: buildRootWithFreshPathways(tree, boundaryCount) });
  return [];
}

/** Re-finds a node by id in the CURRENT tree -- needed whenever a
 *  previously-captured node reference may now be stale (its parent's
 *  `children` array changed shape since that render, e.g. right
 *  after a lazily-created cluster subgroup lands). */
export function findNodeById(
  node: EditableLogicNode,
  nodeId: string,
): EditableLogicNode | null {
  if (node.node_id === nodeId) return node;
  for (const child of node.children ?? []) {
    const found = findNodeById(child, nodeId);
    if (found) return found;
  }
  return null;
}

/** The single AT_LEAST child of a pathway, if a cluster grouping
 *  choice has already materialized one -- lets the orchestrator know
 *  whether a fresh subgroup still needs creating for "only one needs
 *  to match" before routing new cluster-row adds into it. */
export function findClusterSubgroup(
  pathwayNode: EditableLogicNode,
): EditableLogicNode | null {
  return pathwayNode.children?.find((c) => c.kind === "AT_LEAST") ?? null;
}

/** Scan forward from the end of the previous match so repeated item
 *  text (e.g. two pathways both listing "weight loss") still gets a
 *  distinct, stable local offset instead of colliding on the first
 *  occurrence every time. */
function locateClusterItems(
  text: string,
  baseOffset: number,
  items: string[],
): RecommendationStructureItem[] {
  let cursor = 0;
  return items.map((itemText) => {
    const idx = text.indexOf(itemText, cursor);
    const localStart = idx >= 0 ? idx : cursor;
    const localEnd = localStart + itemText.length;
    cursor = Math.max(cursor, localEnd);
    return { text: itemText, start: baseOffset + localStart, end: baseOffset + localEnd };
  });
}

export interface PathwayRows {
  /** Row(s) to render -- either one plain leaf, or one lead row with
   *  the detected cluster nested as its children. */
  items: RecommendationStructureItem[];
  /** True when a "some of these" cluster was detected under this
   *  pathway, so the AT_LEAST-vs-AND grouping question applies. */
  hasCluster: boolean;
}

/**
 * Build one pathway's own resolvable rows from its text boundary.
 * Structure-sourced children keep their real ingestion offsets;
 * heuristic-sourced items get locally-scoped offsets (stable and
 * unique within this one render, not meaningful outside it). Shared
 * by StepPathwayConditions (rendering) and the wizard orchestrator
 * (deciding which parent a clicked row's leaf should attach under).
 */
export function buildPathwayRows(boundary: PathwayTextBoundary): PathwayRows {
  const cluster = resolveAtLeastCluster(boundary);
  if (!cluster) {
    const text = cleanPathwayText(boundary.text);
    return {
      items: [{ text, start: boundary.start, end: boundary.start + text.length }],
      hasCluster: false,
    };
  }

  const clusterRows =
    boundary.source === "structure" && boundary.structureChildren
      ? boundary.structureChildren
      : locateClusterItems(boundary.text, boundary.start, cluster.items);

  if (!cluster.leadText) {
    return { items: clusterRows, hasCluster: clusterRows.length > 0 };
  }
  const leadRow: RecommendationStructureItem = {
    text: cluster.leadText,
    start: boundary.start,
    end: boundary.start + cluster.leadText.length,
    children: clusterRows.length > 0 ? clusterRows : undefined,
  };
  return { items: [leadRow], hasCluster: clusterRows.length > 0 };
}

/** Whether `item` is one of the nested cluster children (as opposed
 *  to the lead row or a plain non-cluster leaf) -- decides whether a
 *  new leaf created from this row should attach under the pathway's
 *  AT_LEAST subgroup (when the reviewer chose "only one needs to
 *  match") rather than directly under the pathway itself. Matches by
 *  offset, not object identity, since the orchestrator and
 *  StepPathwayConditions each derive their own `buildPathwayRows()`
 *  call from the same boundary. */
export function isClusterChildRow(
  boundary: PathwayTextBoundary,
  item: RecommendationStructureItem,
): boolean {
  const { items, hasCluster } = buildPathwayRows(boundary);
  if (!hasCluster) return false;
  const clusterRows = items[0]?.children ?? items;
  return clusterRows.some((row) => row.start === item.start && row.end === item.end);
}

/** Where a Step 3 row click should go, decided once and purely so
 *  the orchestrator's own click handler is a thin dispatch over this
 *  result rather than re-deriving the same branching inline. */
export type RowClickDecision =
  | { action: "select"; nodeId: string }
  | { action: "add"; parentNodeId: string; text: string }
  | { action: "create_subgroup_then_add"; pathwayNodeId: string; text: string };

export function decideRowClickTarget(
  pathwayNode: EditableLogicNode,
  boundary: PathwayTextBoundary,
  item: RecommendationStructureItem,
  resolution: ListRowResolution | undefined,
  grouping: ClusterGrouping | undefined,
): RowClickDecision {
  if (resolution?.nodeId) return { action: "select", nodeId: resolution.nodeId };
  if (grouping === "AT_LEAST" && isClusterChildRow(boundary, item)) {
    const subgroup = findClusterSubgroup(pathwayNode);
    return subgroup
      ? { action: "add", parentNodeId: subgroup.node_id, text: item.text }
      : { action: "create_subgroup_then_add", pathwayNodeId: pathwayNode.node_id, text: item.text };
  }
  return { action: "add", parentNodeId: pathwayNode.node_id, text: item.text };
}
