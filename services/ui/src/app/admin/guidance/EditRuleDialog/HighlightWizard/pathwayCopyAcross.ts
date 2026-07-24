/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Detects when two pathways in the SAME rule ask about the exact same
 * set of findings -- e.g. NG12 1.2.9's pathway C ("... with any of
 * the following: nausea, vomiting, weight loss, reflux, dyspepsia,
 * upper abdominal pain") and pathway D ("nausea or vomiting with any
 * of the following: weight loss, reflux, dyspepsia, upper abdominal
 * pain") both need the same six findings, just split differently into
 * a lead-or cluster plus a smaller trailing cluster.
 *
 * Builds a plan to copy an EARLIER, already-confirmed pathway's
 * resolved SNOMED codes onto a LATER pathway's matching rows, so a
 * reviewer never has to search for "vomiting" twice in the same rule.
 *
 * This is a ONE-TIME, author-time copy, not a live shared reference:
 * once applied, the two pathways own fully independent LogicCriterion
 * nodes and can drift apart if a reviewer edits one later. A live
 * shared "named symptom set" entity was considered and explicitly
 * deferred as separate, larger scope (new Neo4j entity, compiler
 * dereference, retrofit of existing duplicated rules) -- this plan
 * only ever touches the pathway the reviewer is currently building.
 */
import type { EditableLogicNode, LogicCriterion } from "../types";
import type { PathwayTextBoundary, RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";
import {
  buildPathwayRows,
  buildRowResolver,
  isClusterChildRow,
  isLeadClusterChildRow,
  pathwayTextWindow as pathwayTextWindowByLength,
  type ClusterGrouping,
} from "./wizardMapping";

function normaliseItemText(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, " ");
}

/** Convenience wrapper over the canonical `pathwayTextWindow` in
 *  wizardMapping -- accepts the recommendation string and derives
 *  length. Prefer importing from wizardMapping when you already have
 *  a numeric length. */
export function pathwayTextWindow(
  boundaries: PathwayTextBoundary[],
  index: number,
  recommendationText: string | null | undefined,
): { start: number; end: number } | undefined {
  const boundary = boundaries[index];
  if (!boundary) return undefined;
  return pathwayTextWindowByLength(
    boundaries,
    index,
    recommendationText?.length ?? boundary.end,
  );
}

/** Every row this pathway's cluster(s) ask about, in document order,
 *  regardless of whether they render nested under a lead row or flat
 *  alongside a lead-or cluster (see `buildPathwayRows`'s doc comment
 *  for why the shape differs between those two cases). */
function clusterRowsOf(boundary: PathwayTextBoundary): RecommendationStructureItem[] {
  const { items, hasCluster, leadCluster } = buildPathwayRows(boundary);
  if (!hasCluster && !leadCluster) return [];
  const nested = items[0]?.children;
  const trailing = nested ?? items.slice(leadCluster?.items.length ?? 0);
  return [...(leadCluster?.items ?? []), ...trailing];
}

/** Normalised, sorted signature of the findings this pathway's
 *  cluster(s) ask about -- null when there is nothing worth matching
 *  on (no cluster, or fewer than two items, mirroring namedSets.ts's
 *  own >=2 threshold for "a set worth naming"). Two pathways with the
 *  same signature are asking about the same findings even if one
 *  splits them into a lead-or cluster and the other does not. */
export function pathwayClusterSignature(boundary: PathwayTextBoundary): string | null {
  const texts = clusterRowsOf(boundary)
    .map((row) => normaliseItemText(row.text))
    .filter(Boolean);
  if (texts.length < 2) return null;
  return texts.slice().sort().join("|");
}

/** The index of the first EARLIER pathway whose cluster(s) share
 *  `targetIndex`'s exact signature, or null when there is no
 *  duplicate. Only earlier indices are considered: the wizard always
 *  confirms pathways in order, so any earlier pathway is guaranteed
 *  to already be fully resolved. */
export function findCopyAcrossSource(
  boundaries: PathwayTextBoundary[],
  targetIndex: number,
): number | null {
  const targetSignature = pathwayClusterSignature(boundaries[targetIndex]);
  if (!targetSignature) return null;
  for (let i = 0; i < targetIndex; i += 1) {
    if (pathwayClusterSignature(boundaries[i]) === targetSignature) return i;
  }
  return null;
}

/**
 * Strips per-occurrence AI-confidence and human-review provenance
 * before a criterion is copied onto a different leaf. Those fields
 * describe THIS specific leaf's own review history (see
 * `LogicCriterion.human_reviewed_at`'s doc comment) -- copying them
 * onto a brand new leaf the reviewer has not individually reviewed
 * would misrepresent that leaf's audit trail. The copy action itself
 * (a reviewer clicking "Copy them across") is a deliberate human
 * decision, but it is a decision about the SOURCE leaf's mapping,
 * not a review of the new leaf, so the new leaf starts clean -- the
 * same state a fresh manual SNOMED pick would produce.
 */
export function cloneCriterionForCopy(criterion: LogicCriterion): LogicCriterion {
  const {
    confidence: _confidence,
    needs_human_review: _needsHumanReview,
    human_reviewed_at: _humanReviewedAt,
    human_reviewed_by: _humanReviewedBy,
    ...rest
  } = criterion;
  return {
    ...rest,
    seeds: criterion.seeds ? criterion.seeds.map((seed) => ({ ...seed })) : undefined,
  };
}

/** Every already-resolved row under `sourcePathwayNode`, keyed by its
 *  own normalised row text, ready to be copied onto a matching row in
 *  a later pathway. */
function collectResolvedCriteriaByText(
  sourceBoundary: PathwayTextBoundary,
  sourcePathwayNode: EditableLogicNode,
  recommendationText: string | null | undefined,
  sourceTextWindow: { start: number; end: number } | undefined,
): Map<string, LogicCriterion> {
  const resolve = buildRowResolver(sourcePathwayNode, recommendationText, sourceTextWindow);
  const map = new Map<string, LogicCriterion>();
  for (const row of clusterRowsOf(sourceBoundary)) {
    const resolution = resolve(row);
    if (resolution?.criterion) {
      map.set(normaliseItemText(row.text), cloneCriterionForCopy(resolution.criterion));
    }
  }
  return map;
}

export interface CopyAcrossMatch {
  item: RecommendationStructureItem;
  criterion: LogicCriterion;
  /** Which of the target pathway's (up to two) subgroups this match's
   *  new leaf needs to attach under, or "direct" for a plain leaf
   *  under the pathway itself. */
  role: "lead" | "trailing" | "direct";
}

export interface CopyAcrossPlan {
  sourceIndex: number;
  matches: CopyAcrossMatch[];
  /** Pre-filled default for the target's trailing cluster, carried
   *  over from whichever grouping the source pathway settled on --
   *  never applied silently: the reviewer sees it via the normal
   *  "Change" affordance StepPathwayConditions already offers for any
   *  grouping choice. */
  groupingToApply?: ClusterGrouping;
  leadGroupingToApply?: ClusterGrouping;
}

/**
 * Builds the copy-across plan for the pathway at `targetIndex`, or
 * null when there is nothing to offer (no duplicate, or the earlier
 * duplicate has no resolved rows yet -- should not happen for a
 * genuinely earlier pathway, since the wizard requires full
 * resolution before "Confirm", but defended anyway).
 */
export function buildCopyAcrossPlan(params: {
  boundaries: PathwayTextBoundary[];
  targetIndex: number;
  sourcePathwayNode: EditableLogicNode;
  recommendationText: string | null | undefined;
  sourceGrouping?: ClusterGrouping;
  sourceLeadGrouping?: ClusterGrouping;
}): CopyAcrossPlan | null {
  const { boundaries, targetIndex, sourcePathwayNode, recommendationText } = params;
  const sourceIndex = findCopyAcrossSource(boundaries, targetIndex);
  if (sourceIndex === null) return null;

  const byText = collectResolvedCriteriaByText(
    boundaries[sourceIndex],
    sourcePathwayNode,
    recommendationText,
    pathwayTextWindow(boundaries, sourceIndex, recommendationText),
  );
  if (byText.size === 0) return null;

  const targetBoundary = boundaries[targetIndex];
  const { hasCluster: targetHasTrailing, leadCluster: targetLeadCluster } =
    buildPathwayRows(targetBoundary);

  const matches: CopyAcrossMatch[] = [];
  for (const row of clusterRowsOf(targetBoundary)) {
    const criterion = byText.get(normaliseItemText(row.text));
    if (!criterion) continue;
    const role: CopyAcrossMatch["role"] = isLeadClusterChildRow(targetBoundary, row)
      ? "lead"
      : isClusterChildRow(targetBoundary, row)
        ? "trailing"
        : "direct";
    matches.push({ item: row, criterion, role });
  }
  if (matches.length === 0) return null;

  return {
    sourceIndex,
    matches,
    groupingToApply: targetHasTrailing
      ? (params.sourceGrouping ?? params.sourceLeadGrouping)
      : undefined,
    // Target D's lead-or has no counterpart on source C -- still
    // default the Recommended AT_LEAST so copy-across cannot leave
    // nausea/vomiting as flat AND siblings under the pathway.
    leadGroupingToApply: targetLeadCluster
      ? (params.sourceLeadGrouping ?? params.sourceGrouping ?? "AT_LEAST")
      : undefined,
  };
}
