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
 * Materialization keeps existing pathway containers only when the OR
 * child count exactly matches the confirmed boundary count (a pure
 * read -- already-confirmed SNOMED matches inside those pathways are
 * preserved). When counts disagree -- too few OR too many, e.g. an
 * AI draft with 6 pathways against a correct 4-situation Step 2 --
 * the OR is rebuilt to exactly N empty AND shells so orphan E/F
 * leaves cannot leak into Review. Prerequisites outside the OR are
 * always preserved.
 */
import { findPathwaySplit } from "../pathwayDetection";
import { freshNodeId, mintPathwayKey } from "../treeOps";
import { conceptText, demographicToText, observationToText } from "../treeToSentence";
import type { EditableLogicNode, LogicNodeKind, NodeUpdate } from "../types";
import {
  cleanPathwayText,
  looksLikeWithAnd,
  resolveAtLeastCluster,
  type PathwayTextBoundary,
  type RecommendationStructureItem,
} from "../SentenceEditor/pathwayTextSplit";
import type { ListRowResolution } from "../SentenceEditor/ListRecommendationView";
import type { TextMatchRange } from "../SentenceEditor/recommendationTextMatch";
import { leafTextMatch } from "./leafTextMatch";

/** Minimum token-overlap score before an AI/Advanced-editor leaf may
 *  auto-resolve a Step 3 row. Exact / source_row_text matches always
 *  win; weak fuzzy preferred-term hits must stay unresolved. */
const MIN_ROW_AUTO_RESOLVE_SCORE = 0.85;

/** Fraction of the ROW's own span a fuzzy match must cover before that
 *  leaf may auto-resolve it. Stops a short preferred-term hit (e.g.
 *  exact "weight" inside "weight loss", or "platelet count" inside a
 *  longer lead phrase) from silently marking the whole row matched. */
const MIN_ROW_COVERAGE = 0.7;

function matchCoversRowWell(
  match: TextMatchRange,
  row: RecommendationStructureItem,
): boolean {
  const rowLen = Math.max(1, row.end - row.start);
  const overlap =
    Math.min(match.end, row.end) - Math.max(match.start, row.start);
  if (overlap / rowLen >= MIN_ROW_COVERAGE) return true;
  // A full multi-word preferred-term hit nested inside a longer lead
  // clause (e.g. "weight loss" inside "aged 55 or over with weight
  // loss") is strong enough -- reject only single-token fragments
  // that leave most of the row unmatched (e.g. "weight" vs "weight loss").
  const tokens = (match.matchedText ?? "").trim().split(/\s+/).filter(Boolean);
  return tokens.length >= 2 && overlap >= 10;
}

const LEAF_KINDS = new Set<LogicNodeKind>(["CONCEPT", "DEMOGRAPHIC", "OBSERVATION"]);

/**
 * The text span that "belongs" to pathway `index` for matching and
 * highlight scoping. A structural boundary's own `[start, end)` covers
 * only the lead `<li>` sentence -- nested `<ul>` cluster items sit at
 * later offsets, past `boundary.end`. Extending to the next pathway's
 * start (or end of text for the last pathway) keeps those nested words
 * inside the owning situation instead of being treated as prerequisites.
 *
 * Shared by PathwayConditionsStage (row resolution) and
 * GuidelineQuotePanel (highlight scoping) so the two cannot drift.
 */
export function pathwayTextWindow(
  boundaries: PathwayTextBoundary[],
  index: number,
  textLength: number,
): { start: number; end: number } | undefined {
  if (boundaries.length <= 1 || index < 0 || index >= boundaries.length) {
    return undefined;
  }
  const boundary = boundaries[index];
  const nextStart = boundaries[index + 1]?.start;
  // Fall back to the structural end when textLength is unknown/0 so a
  // last-pathway window never collapses to an empty or inverted range.
  return {
    start: boundary.start,
    end: nextStart ?? Math.max(textLength, boundary.end),
  };
}

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

/**
 * The key `clusterGroupings`/`leadClusterGroupings` (and the
 * copy-across "dismissed" set) are stored under -- the pathway's own
 * `pathway_key` when it has one, which is every real materialized
 * pathway. Falls back to a positional key only for a pathway node
 * that genuinely has none: the `boundaries.length === 1` "doesn't
 * split" case (the whole tree, not an OR child) and hand-built test
 * fixtures that never went through `ensurePathwayKeys`. Keying by
 * `pathway_key` instead of the raw array index means a grouping
 * choice recorded for "Situation C" stays attached to Situation C
 * even after a merge/split in Step 2 changes which index it lives at
 * -- see the wizard state-machine stability plan section.
 */
export function pathwayGroupingKey(
  pathwayNode: EditableLogicNode | null | undefined,
  index: number,
): string {
  return pathwayNode?.pathway_key ?? `pathway-index-${index}`;
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
 * Re-anchors a whole-text match's offsets into `window`'s own local
 * coordinate space -- i.e. runs `leafTextMatch` against ONLY the
 * substring `[window.start, window.end)` of `recommendationText`,
 * then shifts the result back to whole-text offsets. Confines a
 * pathway's own leaf lookup to that pathway's own span of text, so
 * `exactMatch`'s "first occurrence in the whole document" behaviour
 * (see recommendationTextMatch.ts) can never resolve a leaf onto a
 * DIFFERENT pathway's identically-worded text -- e.g. NG12 1.2.9's
 * pathway D repeats "nausea"/"vomiting", already used by pathway C:
 * without windowing, a search for D's "Nausea" leaf across the whole
 * text would find C's earlier occurrence first, so D's own row would
 * never resolve even after the reviewer picked a concept for it.
 */
function leafTextMatchInWindow(
  recommendationText: string | null | undefined,
  node: EditableLogicNode,
  window: { start: number; end: number } | undefined,
): TextMatchRange | null {
  if (!window || !recommendationText) return leafTextMatch(recommendationText, node);
  const windowed = leafTextMatch(recommendationText.slice(window.start, window.end), node);
  if (!windowed) return null;
  return {
    ...windowed,
    start: windowed.start + window.start,
    end: windowed.end + window.start,
  };
}

/**
 * Builds a `getRowResolution` closure for one pathway: does this row
 * (by its own `[start, end)` span in the shared recommendation text)
 * already have a matching leaf anywhere under this pathway node,
 * regardless of how deeply nested (a cluster's own AT_LEAST subgroup,
 * or a plain top-level AND leaf)? Computed once per pathway/text pair
 * rather than per row, since every row resolution needs the same scan.
 *
 * `textWindow` (typically the pathway's own boundary `[start, end)`)
 * confines the text search to this pathway's own span -- see
 * `leafTextMatchInWindow`'s doc comment for why that matters whenever
 * two pathways share identical wording (e.g. two "any of the
 * following" clusters both listing "nausea"/"vomiting"). Omit it only
 * for the single-pathway case (`boundaries.length === 1`, no OR to
 * scope within).
 */
function resolutionFor(node: EditableLogicNode): ListRowResolution {
  return {
    nodeId: node.node_id,
    criterion: node.criterion ?? null,
    preferredTerm: leafDisplayTerm(node) || null,
  };
}

export function buildRowResolver(
  pathwayNode: EditableLogicNode,
  recommendationText: string | null | undefined,
  textWindow?: { start: number; end: number },
): (row: RecommendationStructureItem) => ListRowResolution | undefined {
  const leaves = collectLeaves(pathwayNode);

  // Exact-provenance leaves first: a leaf the wizard itself added for
  // THIS row (see EditableLogicNode.source_row_text's doc comment) is
  // matched by the exact string it was added for, not by re-guessing
  // from the picked SNOMED term's own wording -- which very often
  // shares no words at all with the row (e.g. "Indigestion" picked
  // for a row that reads "treatment-resistant dyspepsia"). Without
  // this, the row would never show as resolved even though the leaf
  // really was added, which reads to the reviewer as "nothing
  // happened" when they pick a code.
  const byRowText = new Map<string, EditableLogicNode>();
  for (const node of leaves) {
    if (node.source_row_text) byRowText.set(node.source_row_text, node);
  }

  // Fuzzy text-match fallback covers everything else: AI-drafted
  // leaves from before this field existed, and leaves authored via
  // the Advanced/Sentence editor, neither of which carry provenance.
  // Reject weak overlaps so a preferred term that only covers half a
  // row cannot silently mark that row "matched".
  const fuzzyMatches = leaves
    .map((node) => ({
      node,
      match: leafTextMatchInWindow(recommendationText, node, textWindow),
    }))
    .filter(
      (entry): entry is { node: EditableLogicNode; match: TextMatchRange } =>
        !!entry.match &&
        (entry.match.strategy === "exact" ||
          entry.match.score >= MIN_ROW_AUTO_RESOLVE_SCORE),
    );

  return (row) => {
    const exact = byRowText.get(row.text);
    if (exact) return resolutionFor(exact);
    const hit = fuzzyMatches.find(
      (entry) =>
        rangesOverlap(entry.match, row) && matchCoversRowWell(entry.match, row),
    );
    return hit ? resolutionFor(hit.node) : undefined;
  };
}

/** Every top-level row plus every nested cluster child, in one flat
 *  list -- shared by `countUnresolvedRows` and callers that need to
 *  know which tree nodes a pathway's rows already cover (e.g. "jump to
 *  issue" filtering out problems that already have a visible row). */
export function flattenPathwayItems(
  items: RecommendationStructureItem[],
): RecommendationStructureItem[] {
  const flat: RecommendationStructureItem[] = [];
  const walk = (list: RecommendationStructureItem[]): void => {
    for (const item of list) {
      flat.push(item);
      if (item.children?.length) walk(item.children);
    }
  };
  walk(items);
  return flat;
}

/** True once every top-level row (and every nested cluster child) in
 *  `items` resolves to a real leaf -- the gate Step 3's "Confirm
 *  situation X" button checks before letting the reviewer move on. */
export function countUnresolvedRows(
  items: RecommendationStructureItem[],
  getRowResolution: (item: RecommendationStructureItem) => ListRowResolution | undefined,
): number {
  return flattenPathwayItems(items).filter((item) => {
    const resolution = getRowResolution(item);
    return !(resolution?.criterion || resolution?.preferredTerm);
  }).length;
}

/**
 * Read-only: the pathway container nodes to hand to Step 3, in
 * boundary order, when the tree's OR already has EXACTLY
 * `boundaryCount` children. Returns `[]` when a tree mutation is
 * needed first (see `materializePathways`) -- the caller re-derives
 * this on the next render once that mutation lands. A too-long OR
 * (e.g. AI draft with 6 pathways vs 4 confirmed situations) is NOT
 * treated as ready -- slicing would leave orphan E/F containers in
 * the tree and corrupt Review / "Already confirmed" summaries.
 */
export function readMaterializedPathways(
  tree: EditableLogicNode,
  boundaryCount: number,
): EditableLogicNode[] {
  const split = findPathwaySplit(tree);
  const existing = split?.orNode.children ?? [];
  return existing.length === boundaryCount ? existing : [];
}

/**
 * Re-anchors an existing OR node's pathway containers to the
 * wizard's own text boundaries by CONTENT, not raw array position.
 *
 * `readMaterializedPathways` (and every caller of it) has always
 * assumed `orNode.children[i]` already corresponds to `boundaries[i]`
 * -- i.e. that whichever pathway container an AI extraction (or an
 * earlier edit) put first in the tree is also the guideline's own
 * first-listed situation. Nothing enforces that: an extraction
 * pipeline orders `OR` children however it built them, independently
 * of this wizard's own `pathwayTextSplit` boundary detector, so a
 * container holding, say, situation C's leaves can end up at array
 * index 0 -- and every downstream read (that pathway's own rows, its
 * "Already confirmed: A: ..." summary, its cluster-grouping choice)
 * then gets shown under the wrong letter. Reported directly against
 * NG12 1.2.9 in production: situation B's "Already confirmed"
 * summary showed situation C's whole 6-item cluster mislabelled "A".
 *
 * A container with at least one already-resolved leaf carries real
 * evidence of which boundary it belongs to: `leafTextMatch` that leaf
 * against the WHOLE `recommendationText` (unwindowed -- the boundary
 * a leaf belongs to is exactly what this function is solving for, so
 * it cannot window by boundary first) and see which boundary's own
 * `[start, end)` span contains the match. A container with no leaves
 * yet (freshly materialized, still empty) carries no evidence either
 * way and keeps its relative position among the remaining, unclaimed
 * slots -- there is nothing to re-anchor it by.
 *
 * Two containers double-claiming the same boundary (bad underlying
 * data) resolves in original-order-wins: the first container to
 * reach that boundary keeps it, the second falls back to an
 * unclaimed slot rather than silently overwriting the first claim.
 */
export function orderPathwayNodesByBoundary(
  containers: EditableLogicNode[],
  boundaries: PathwayTextBoundary[],
  recommendationText: string | null | undefined,
): EditableLogicNode[] {
  if (!recommendationText || containers.length !== boundaries.length) {
    return containers;
  }

  const boundaryIndexFor = (offset: number): number => {
    for (let i = boundaries.length - 1; i >= 0; i -= 1) {
      if (offset >= boundaries[i].start) return i;
    }
    return 0;
  };

  const claimedBoundaries = new Map<number, EditableLogicNode>();
  const unclaimedContainers: EditableLogicNode[] = [];

  for (const container of containers) {
    const claim = collectLeaves(container)
      .map((leaf) => leafTextMatch(recommendationText, leaf))
      .find((match): match is TextMatchRange => !!match);
    const boundaryIndex = claim ? boundaryIndexFor(claim.start) : null;
    if (boundaryIndex !== null && !claimedBoundaries.has(boundaryIndex)) {
      claimedBoundaries.set(boundaryIndex, container);
    } else {
      unclaimedContainers.push(container);
    }
  }

  return boundaries.map(
    (_, i) => claimedBoundaries.get(i) ?? unclaimedContainers.shift()!,
  );
}

/** Mint N empty pathway AND shells with fresh pathway_keys. */
function freshEmptyPathways(boundaryCount: number): EditableLogicNode[] {
  return Array.from({ length: boundaryCount }, () => ({
    node_id: freshNodeId(),
    kind: "AND" as const,
    children: [],
    pathway_key: mintPathwayKey(),
  }));
}

/**
 * Constructs a brand new OR-of-pathways skeleton, preserving whatever
 * the tree already contains as a sibling prerequisite rather than
 * discarding it. Used the first time a rule with no pathway split at
 * all confirms 2+ boundaries in Step 2.
 */
export function buildRootWithFreshPathways(
  tree: EditableLogicNode,
  boundaryCount: number,
): EditableLogicNode {
  const or: EditableLogicNode = {
    node_id: freshNodeId(),
    kind: "OR",
    children: freshEmptyPathways(boundaryCount),
  };
  if (tree.kind === "AND") {
    return { ...tree, children: [...(tree.children ?? []), or] };
  }
  return { node_id: freshNodeId(), kind: "AND", children: [tree, or] };
}

/**
 * Rebuilds the pathway-split OR to exactly `boundaryCount` empty AND
 * shells, keeping every prerequisite outside that OR. Used when an
 * existing AI (or earlier) draft has the wrong number of pathway
 * children relative to the reviewer's confirmed Step 2 situations.
 */
export function rebuildPathwayOr(
  tree: EditableLogicNode,
  boundaryCount: number,
): EditableLogicNode {
  const split = findPathwaySplit(tree);
  const or: EditableLogicNode = {
    node_id: freshNodeId(),
    kind: "OR",
    children: freshEmptyPathways(boundaryCount),
  };
  if (!split) return buildRootWithFreshPathways(tree, boundaryCount);
  if (tree.node_id === split.orNode.node_id) return or;
  return {
    ...tree,
    children: (tree.children ?? []).map((child) =>
      child.node_id === split.orNode.node_id ? or : child,
    ),
  };
}

/**
 * Ensures exactly `boundaryCount` pathway groups exist. When the OR
 * already has that many children, returns them immediately (no
 * mutation). When counts disagree -- or there is no split yet --
 * emits a single `replace_root` that rebuilds the OR to N empty
 * shells (prerequisites preserved). Returns `[]` after a mutation so
 * the caller waits for the next tree prop and re-reads.
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
    onUpdate({ kind: "replace_root", node: rebuildPathwayOr(tree, boundaryCount) });
    return [];
  }

  onUpdate({ kind: "replace_root", node: buildRootWithFreshPathways(tree, boundaryCount) });
  return [];
}

/**
 * True when confirming `newBoundaryCount` in Step 2 would force the
 * `materializePathways` call above down the `rebuildPathwayOr` path,
 * which replaces every pathway container with an EMPTY shell --
 * discarding leaf conditions the reviewer already resolved in Step 3
 * under the previous count. Lets the orchestrator warn first instead
 * of silently wiping already-confirmed work (e.g. Back to Step 2,
 * merge two rows together, re-confirm -- see the wizard confusion
 * audit's merge/split section). A brand-new split with no existing
 * pathway containers at all has nothing to lose, so this is false.
 */
export function splitWouldDiscardPathwayLeaves(
  tree: EditableLogicNode,
  newBoundaryCount: number,
): boolean {
  const split = findPathwaySplit(tree);
  if (!split) return false;
  const existing = split.orNode.children ?? [];
  if (existing.length === newBoundaryCount) return false;
  return existing.some((container) => (container.children?.length ?? 0) > 0);
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
 *  to match" before routing new cluster-row adds into it. For a
 *  pathway with TWO clusters (see `PathwayRows.leadCluster`), prefer
 *  `findClusterSubgroupByRole` so a click routes to the correct one
 *  instead of always the first AT_LEAST child found. */
export function findClusterSubgroup(
  pathwayNode: EditableLogicNode,
): EditableLogicNode | null {
  return pathwayNode.children?.find((c) => c.kind === "AT_LEAST") ?? null;
}

/** The AT_LEAST child tagged for `role` (see
 *  `EditableLogicNode.cluster_role`'s doc comment) -- an untagged
 *  AT_LEAST child counts as "trailing", the overwhelmingly common
 *  single-cluster case, so a legacy pathway with one unmarked
 *  subgroup keeps resolving correctly with no data migration. Use
 *  this instead of `findClusterSubgroup` whenever the pathway may
 *  have both a lead-or and a trailing cluster. */
export function findClusterSubgroupByRole(
  pathwayNode: EditableLogicNode,
  role: "lead" | "trailing",
): EditableLogicNode | null {
  return (
    pathwayNode.children?.find(
      (c) => c.kind === "AT_LEAST" && (c.cluster_role ?? "trailing") === role,
    ) ?? null
  );
}

/** Scan forward from `startCursor` so repeated item text (e.g. two
 *  pathways both listing "weight loss", or a lead cluster and a
 *  trailing cluster searched one after the other) still gets a
 *  distinct, stable local offset instead of colliding on an earlier
 *  occurrence. Returns the cursor position after the last match so a
 *  caller can chain a second search to start looking only from there. */
function locateItemsFrom(
  text: string,
  baseOffset: number,
  items: string[],
  startCursor: number,
): { rows: RecommendationStructureItem[]; cursor: number } {
  let cursor = startCursor;
  const rows = items.map((itemText) => {
    const idx = text.indexOf(itemText, cursor);
    const localStart = idx >= 0 ? idx : cursor;
    const localEnd = localStart + itemText.length;
    cursor = Math.max(cursor, localEnd);
    return { text: itemText, start: baseOffset + localStart, end: baseOffset + localEnd };
  });
  return { rows, cursor };
}

function locateClusterItems(
  text: string,
  baseOffset: number,
  items: string[],
): RecommendationStructureItem[] {
  return locateItemsFrom(text, baseOffset, items, 0).rows;
}

/** One AT_LEAST-vs-AND cluster's own member rows -- everything that
 *  ONE grouping-choice question in Step 3 applies to. */
export interface PathwayCluster {
  items: RecommendationStructureItem[];
}

export interface PathwayRows {
  /** Row(s) to render -- either one plain leaf, one lead row with the
   *  trailing cluster nested as its children, or (when `leadCluster`
   *  is also set) both clusters' own member rows flattened at the
   *  front, each individually clickable in its own right. */
  items: RecommendationStructureItem[];
  /** True when a trailing "any of the following" cluster was detected
   *  under this pathway, so the AT_LEAST-vs-AND grouping question
   *  applies to it. */
  hasCluster: boolean;
  /**
   * Present only when a second, marker-less "A or B" alternative
   * cluster was ALSO detected ahead of the trailing cluster (see
   * `AtLeastClusterSplit.leadCluster`'s doc comment) -- e.g. "nausea
   * or vomiting" ahead of "any of the following: weight loss, ...".
   * Both clusters apply to the SAME pathway, ANDed together, but each
   * gets its OWN AT_LEAST-vs-AND grouping question: the reviewer, not
   * the wording, decides whether an "or" phrase should really only
   * require one match. Its member rows are also included, flat, in
   * `items` -- this field exists purely so a caller (Step 3's UI, the
   * click-routing helpers below) can tell which rows belong to which
   * cluster; a caller that does not care can ignore it and still see
   * every row via `items`.
   */
  leadCluster?: PathwayCluster;
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
    // Situation B ("upper abdominal pain with low haemoglobin levels"):
    // no AT_LEAST marker, but a clinical " with " joining two short
    // findings that each need their own SNOMED / observation pick.
    const withParts = looksLikeWithAnd(text);
    if (withParts) {
      const located = locateClusterItems(text, boundary.start, withParts);
      return { items: located, hasCluster: false };
    }
    return {
      items: [{ text, start: boundary.start, end: boundary.start + text.length }],
      hasCluster: false,
    };
  }

  const leadClusterRows = cluster.leadCluster
    ? locateClusterItems(boundary.text, boundary.start, cluster.leadCluster)
    : [];
  const leadCluster: PathwayCluster | undefined =
    leadClusterRows.length > 0 ? { items: leadClusterRows } : undefined;
  // Once a lead cluster has consumed the front of the text, resume
  // searching for trailing items only from where it left off -- keeps
  // a trailing item whose text happens to also appear earlier (inside
  // the lead cluster's own span) from matching the wrong occurrence.
  const trailingSearchStart =
    leadClusterRows.length > 0
      ? leadClusterRows[leadClusterRows.length - 1].end - boundary.start
      : 0;

  const clusterRows =
    boundary.source === "structure" && boundary.structureChildren
      ? boundary.structureChildren
      : locateItemsFrom(boundary.text, boundary.start, cluster.items, trailingSearchStart).rows;

  if (!cluster.leadText) {
    return {
      items: [...leadClusterRows, ...clusterRows],
      hasCluster: clusterRows.length > 0,
      leadCluster,
    };
  }
  const leadRow: RecommendationStructureItem = {
    text: cluster.leadText,
    start: boundary.start,
    end: boundary.start + cluster.leadText.length,
    children: clusterRows.length > 0 ? clusterRows : undefined,
  };
  return { items: [leadRow], hasCluster: clusterRows.length > 0, leadCluster };
}

/** Whether `item` is one of the TRAILING cluster's nested children (as
 *  opposed to the lead row, a lead-cluster member, or a plain
 *  non-cluster leaf) -- decides whether a new leaf created from this
 *  row should attach under the pathway's AT_LEAST subgroup (when the
 *  reviewer chose "only one needs to match") rather than directly
 *  under the pathway itself. Matches by offset, not object identity,
 *  since the orchestrator and StepPathwayConditions each derive their
 *  own `buildPathwayRows()` call from the same boundary. */
export function isClusterChildRow(
  boundary: PathwayTextBoundary,
  item: RecommendationStructureItem,
): boolean {
  const { items, hasCluster, leadCluster } = buildPathwayRows(boundary);
  if (!hasCluster) return false;
  const clusterRows = items[0]?.children ?? items;
  const isLeadMember = leadCluster?.items.some(
    (row) => row.start === item.start && row.end === item.end,
  );
  if (isLeadMember) return false;
  return clusterRows.some((row) => row.start === item.start && row.end === item.end);
}

/** Whether `item` is one of the LEAD cluster's own member rows (e.g.
 *  "nausea" or "vomiting" in "nausea or vomiting with any of the
 *  following: ..."). Mirrors `isClusterChildRow` for the second
 *  cluster so click-routing can tell the two apart. */
export function isLeadClusterChildRow(
  boundary: PathwayTextBoundary,
  item: RecommendationStructureItem,
): boolean {
  const { leadCluster } = buildPathwayRows(boundary);
  if (!leadCluster) return false;
  return leadCluster.items.some((row) => row.start === item.start && row.end === item.end);
}

/** Where a Step 3 row click should go, decided once and purely so
 *  the orchestrator's own click handler is a thin dispatch over this
 *  result rather than re-deriving the same branching inline. */
export type RowClickDecision =
  | { action: "select"; nodeId: string }
  | { action: "add"; parentNodeId: string; text: string }
  | {
      action: "create_subgroup_then_add";
      pathwayNodeId: string;
      text: string;
      /** See `EditableLogicNode.cluster_role`'s doc comment -- which
       *  of the (up to two) subgroups this fresh AT_LEAST is for. */
      role: "lead" | "trailing";
    };

/** Route a cluster-child row to its existing subgroup, or signal that
 *  a fresh one needs creating first -- shared by both the lead and
 *  trailing branches of `decideRowClickTarget` below. */
function routeToClusterSubgroup(
  pathwayNode: EditableLogicNode,
  role: "lead" | "trailing",
  text: string,
): RowClickDecision {
  const subgroup = findClusterSubgroupByRole(pathwayNode, role);
  return subgroup
    ? { action: "add", parentNodeId: subgroup.node_id, text }
    : { action: "create_subgroup_then_add", pathwayNodeId: pathwayNode.node_id, text, role };
}

/**
 * Routes a Step 3 row click to the correct parent. Lead-cluster rows
 * are checked first (see `PathwayRows.leadCluster`). For either
 * cluster, an undecided grouping follows the Recommended default
 * (AT_LEAST) so nausea/vomiting cannot silently land as flat AND
 * children before the reviewer answers the prompt -- only an explicit
 * "All must match" choice attaches under the pathway itself.
 */
export function decideRowClickTarget(
  pathwayNode: EditableLogicNode,
  boundary: PathwayTextBoundary,
  item: RecommendationStructureItem,
  resolution: ListRowResolution | undefined,
  grouping: ClusterGrouping | undefined,
  leadGrouping?: ClusterGrouping,
): RowClickDecision {
  if (resolution?.nodeId) return { action: "select", nodeId: resolution.nodeId };
  if (isLeadClusterChildRow(boundary, item)) {
    if (leadGrouping === "AND") {
      return { action: "add", parentNodeId: pathwayNode.node_id, text: item.text };
    }
    return routeToClusterSubgroup(pathwayNode, "lead", item.text);
  }
  if (isClusterChildRow(boundary, item)) {
    if (grouping === "AND") {
      return { action: "add", parentNodeId: pathwayNode.node_id, text: item.text };
    }
    return routeToClusterSubgroup(pathwayNode, "trailing", item.text);
  }
  return { action: "add", parentNodeId: pathwayNode.node_id, text: item.text };
}

function normaliseMatchText(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/\.?\s*\[\d{4}\]\s*\.?$/i, "")
    .replace(/\.$/, "")
    .replace(/\s+/g, " ");
}

const MATCH_STOPWORDS = new Set([
  "a",
  "an",
  "the",
  "of",
  "with",
  "and",
  "or",
  "any",
  "following",
  "has",
  "have",
]);

function contentTokens(text: string): Set<string> {
  return new Set(
    normaliseMatchText(text)
      .split(/\s+/)
      .filter((t) => t.length > 2 && !MATCH_STOPWORDS.has(t)),
  );
}

/** True when preferred-term wording and guideline row wording clearly
 *  name the same finding -- e.g. "Weight decreased" vs "weight loss",
 *  "Platelet count above reference range" vs "a raised platelet count".
 *  Kept looser than Step 3 auto-resolve: Confirm reify must still
 *  regroup leaves the reviewer already picked, even when SNOMED labels
 *  drift from the NICE phrasing. */
function significantTokenOverlap(a: string, b: string): boolean {
  const ta = contentTokens(a);
  const tb = contentTokens(b);
  if (ta.size === 0 || tb.size === 0) return false;
  let shared = 0;
  for (const t of ta) {
    if (tb.has(t)) shared += 1;
  }
  if (shared === 0) return false;
  return (
    shared >= 2 ||
    shared / ta.size >= 0.5 ||
    shared / tb.size >= 0.5
  );
}

function leafMatchesClusterRow(
  leaf: EditableLogicNode,
  row: RecommendationStructureItem,
): boolean {
  const rowNorm = normaliseMatchText(row.text);
  if (
    leaf.source_row_text &&
    normaliseMatchText(leaf.source_row_text) === rowNorm
  ) {
    return true;
  }
  const term = leaf.criterion?.preferred_term ?? leaf.observation?.observable_term ?? "";
  if (!term) return false;
  const a = normaliseMatchText(term);
  if (a === rowNorm || a.includes(rowNorm) || rowNorm.includes(a)) return true;
  return significantTokenOverlap(term, row.text);
}

function takeMatchingLeaves(
  pool: EditableLogicNode[],
  rows: RecommendationStructureItem[],
  resolve?: (row: RecommendationStructureItem) => ListRowResolution | undefined,
): EditableLogicNode[] {
  const taken: EditableLogicNode[] = [];
  for (const row of rows) {
    let idx = pool.findIndex((leaf) => leafMatchesClusterRow(leaf, row));
    if (idx < 0 && resolve) {
      const resolution = resolve(row);
      if (resolution?.nodeId) {
        idx = pool.findIndex((leaf) => leaf.node_id === resolution.nodeId);
      }
    }
    if (idx < 0) continue;
    taken.push(pool.splice(idx, 1)[0]);
  }
  return taken;
}

function makeAtLeastGroup(
  role: "lead" | "trailing",
  children: EditableLogicNode[],
): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind: "AT_LEAST",
    min: 1,
    cluster_role: role,
    children,
  };
}

/**
 * Rebuilds one pathway's children so lead/trailing cluster leaves sit
 * under the right AT_LEAST subgroups (or stay as AND siblings when the
 * reviewer chose "All must match"). Used on Confirm so a pathway that
 * was coded before the grouping cards were answered -- or via the
 * multi-code highlighter that used to always parent under the pathway
 * -- still lands as nausea OR vomiting AND AT_LEAST(trailing), not a
 * flat "must have ALL" of every symptom.
 *
 * Returns a new root tree (single `replace_root`-ready value) so the
 * rematerialization cannot be lost to batched multi-`onUpdate` races.
 */
export function withReifiedPathwayClusters(
  tree: EditableLogicNode,
  pathwayNodeId: string,
  boundary: PathwayTextBoundary,
  grouping: ClusterGrouping | undefined,
  leadGrouping: ClusterGrouping | undefined,
  recommendationText?: string | null,
): EditableLogicNode {
  const { items, hasCluster, leadCluster } = buildPathwayRows(boundary);
  if (!hasCluster && !leadCluster) return tree;

  const pathway = findNodeById(tree, pathwayNodeId);
  if (!pathway) return tree;

  const pool: EditableLogicNode[] = [];
  const walk = (n: EditableLogicNode): void => {
    if (LEAF_KINDS.has(n.kind)) {
      pool.push(n);
      return;
    }
    for (const child of n.children ?? []) walk(child);
  };
  walk(pathway);

  const resolve = buildRowResolver(pathway, recommendationText);
  const take = (rows: RecommendationStructureItem[]) =>
    takeMatchingLeaves(pool, rows, resolve);

  const leadRows = leadCluster?.items ?? [];
  const trailingRows = leadCluster
    ? items.slice(leadRows.length)
    : (items[0]?.children ?? []);
  // Situation C's own lead finding ("raised platelet count") sits on
  // the parent row -- keep it as a direct AND sibling of the cluster.
  const directLeadRow =
    !leadCluster && items[0] && items[0].children?.length
      ? items[0]
      : undefined;

  const newChildren: EditableLogicNode[] = [];
  if (directLeadRow) {
    newChildren.push(...take([directLeadRow]));
  }

  const effectiveLead = leadGrouping ?? (leadCluster ? "AT_LEAST" : undefined);
  if (leadRows.length > 0) {
    const leadLeaves = take(leadRows);
    if (effectiveLead === "AND") {
      newChildren.push(...leadLeaves);
    } else if (leadLeaves.length > 0) {
      newChildren.push(makeAtLeastGroup("lead", leadLeaves));
    }
  }

  const effectiveTrail = grouping ?? (hasCluster ? "AT_LEAST" : undefined);
  if (trailingRows.length > 0) {
    const trailLeaves = take(trailingRows);
    if (effectiveTrail === "AND") {
      newChildren.push(...trailLeaves);
    } else if (trailLeaves.length > 0) {
      newChildren.push(makeAtLeastGroup("trailing", trailLeaves));
    }
  }

  // Anything unmatched (extra seeds, observations) stays under the pathway.
  newChildren.push(...pool);

  const rebuilt: EditableLogicNode = { ...pathway, children: newChildren };
  const replace = (n: EditableLogicNode): EditableLogicNode => {
    if (n.node_id === pathwayNodeId) return rebuilt;
    if (!n.children?.length) return n;
    return { ...n, children: n.children.map(replace) };
  };
  return replace(tree);
}
