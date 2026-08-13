/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

import type { ConceptSearchHit, LogicSeed } from "./types";

/**
 * Heuristic: does this SNOMED hit look like an observable / measurement
 * that can carry a numeric threshold? Based on the SNOMED top-level
 * semantic tags the terminology search can return today.
 *
 * Known observable-ish tags (SNOMED CT US/UK editions):
 *   - "observable entity"     -- e.g. "Platelet count"
 *   - "measurement"           -- e.g. "Haemoglobin A1c measurement"
 *   - "procedure"             -- covers "Blood pressure measurement"
 *   - "laboratory test"       -- covers "Serum creatinine test"
 *
 * Anything else (finding, disorder, substance, physical object, ...)
 * is treated as a plain concept.
 */
function tagLooksObservable(tag: string, term: string): boolean {
  const t = tag.toLowerCase().trim();
  if (!t) return false;
  return (
    t.includes("observable") ||
    t.includes("measurement") ||
    t.includes("laboratory") ||
    (t === "procedure" && /\b(pressure|rate|level|count|ratio)\b/i.test(term))
  );
}

export function isLikelyObservable(hit: ConceptSearchHit): boolean {
  return tagLooksObservable(hit.semantic_tag ?? "", hit.term);
}

/** Same heuristic as `isLikelyObservable`, for an already-picked seed. */
export function isLikelyObservableSeed(seed: LogicSeed | undefined): boolean {
  if (!seed) return false;
  return tagLooksObservable(seed.semantic_tag ?? "", seed.preferred_term ?? "");
}
