/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Maps terminology-search hits for one "Ask LEO" term into a review row.
 * Auto-picks when there is exactly one hit; leaves the choice open when
 * there are several; flags when there are none. SNOMED IDs always come
 * from the search index, never from the LLM.
 */
import type { ConceptSearchHit, LogicCriterion } from "./types";

export type TermResolveStatus = "matched" | "needs_pick" | "unmatched";

export interface ResolvedTermRow {
  term: string;
  status: TermResolveStatus;
  hits: ConceptSearchHit[];
  selectedId: string | null;
}

export function buildResolvedTermRow(
  term: string,
  hits: ConceptSearchHit[],
): ResolvedTermRow {
  const safeHits = Array.isArray(hits) ? hits : [];
  if (safeHits.length === 0) {
    return { term, status: "unmatched", hits: [], selectedId: null };
  }
  if (safeHits.length === 1) {
    return {
      term,
      status: "matched",
      hits: safeHits,
      selectedId: safeHits[0].snomed_concept_id,
    };
  }
  return {
    term,
    status: "needs_pick",
    hits: safeHits,
    selectedId: safeHits[0].snomed_concept_id,
  };
}

export function rowToCriterion(row: ResolvedTermRow): LogicCriterion | null {
  if (!row.selectedId) return null;
  const hit = row.hits.find((h) => h.snomed_concept_id === row.selectedId);
  if (!hit) return null;
  return {
    snomed_concept_id: hit.snomed_concept_id,
    preferred_term: hit.term,
    semantic_tag: hit.semantic_tag,
    term: hit.term,
  };
}

export function criteriaFromResolvedRows(
  rows: ResolvedTermRow[],
): LogicCriterion[] {
  return rows
    .map(rowToCriterion)
    .filter((c): c is LogicCriterion => c !== null);
}
