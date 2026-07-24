/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Pure helpers for the "highlight a word, assign one or more SNOMED codes"
 * picker (MultiConceptPicker.tsx).
 *
 * Unlike the legacy single-pick ConceptSearchPanel flow -- where an unset
 * ``distance_child`` silently compiles to a rule-level default of 3
 * (guideline_compiler.py's ``_compile_concept_leaf``) -- this picker asks
 * the reviewer for a depth explicitly, and that depth defaults to 0
 * (exact-match-only). See ``.cursor`` conversation history for the
 * rationale: silent descendant-fuzzy matching is exactly the kind of
 * unreviewed behaviour the rest of this wizard was built to surface, not
 * hide.
 */
import type { ConceptSearchHit, LogicCriterion, LogicSeed } from "./types";

/** Depth asked of the reviewer when none is set. 0 = exact match only. */
export const DEFAULT_CONCEPT_DEPTH = 0;

/**
 * Build one synonym-set seed from a search hit and an explicit depth.
 *
 * Depth 0 is represented as ``include_descendants: false`` (the same
 * exact-match representation the API forces for local concepts), rather
 * than ``include_descendants: true, distance_child: 0`` -- both compile to
 * the same bitmap closure, but the ``false`` form is the canonical "exact
 * match" shape already used elsewhere in this codebase, so a seed built
 * here round-trips identically through SynonymChipEditor's toggle.
 */
export function seedFromHit(hit: ConceptSearchHit, depth: number): LogicSeed {
  const clamped = Math.max(0, Math.floor(depth || 0));
  return {
    snomed_concept_id: hit.snomed_concept_id,
    preferred_term: hit.term,
    semantic_tag: hit.semantic_tag,
    include_descendants: clamped > 0,
    distance_child: clamped > 0 ? clamped : null,
  };
}

/**
 * Build a full ``LogicCriterion`` from one or more picked seeds, ready to
 * dispatch as an ``add_concept`` NodeUpdate. The first seed is the primary
 * (supplies the chip's headline label via the legacy top-level fields),
 * matching ``treeOps.ts``'s ``ensureSeeds``/``syncLegacyFields`` behaviour
 * so a multi-seed pick from this picker is indistinguishable, once saved,
 * from one built up incrementally via SynonymChipEditor's "add seed".
 */
export function buildMultiSeedCriterion(seeds: LogicSeed[]): LogicCriterion {
  if (seeds.length === 0) {
    throw new Error("buildMultiSeedCriterion requires at least one seed");
  }
  const primary = seeds[0];
  return {
    snomed_concept_id: primary.snomed_concept_id,
    preferred_term: primary.preferred_term,
    semantic_tag: primary.semantic_tag,
    seeds,
    primary_concept_id: primary.snomed_concept_id,
    excluded_concept_ids: [],
  };
}
