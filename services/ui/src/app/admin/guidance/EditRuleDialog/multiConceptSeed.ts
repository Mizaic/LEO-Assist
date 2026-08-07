/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-C21AE387 / DI-42246DA7
 *   DO: DO-AA74E9A6 / DO-F8C56339
 *   VT: VT-5632FA0D
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-C21AE387")
 */


/**
 * Pure helpers for the "highlight a word, assign one or more SNOMED codes"
 * picker (MultiConceptPicker.tsx).
 *
 * Unlike the legacy single-pick ConceptSearchPanel flow -- where an unset
 * ``distance_child`` silently compiles to a rule-level default of 3
 * (guideline_compiler.py's ``_compile_concept_leaf``) -- this picker asks
 * the reviewer for a depth explicitly, and that depth defaults to 0
 * (exact-match-only).
 *
 * Observable hits also carry optional operator / value / unit. When the
 * reviewer fills a value on a single selected observable, confirm
 * creates an OBSERVATION leaf; otherwise confirm stays a CONCEPT
 * presence check (depth still applies).
 */
import { isLikelyObservable } from "./observableHit";
import type {
  ConceptSearchHit,
  EditableObservationPayload,
  LogicCriterion,
  LogicSeed,
  ObservationOperator,
} from "./types";

/** Depth asked of the reviewer when none is set. 0 = exact match only. */
export const DEFAULT_CONCEPT_DEPTH = 0;

/** Per-pick threshold fields shown for observable_entity hits. */
export interface ObservableThresholdDraft {
  operator: ObservationOperator;
  value: string;
  value2: string;
  unit: string;
}

export const DEFAULT_OBS_THRESHOLD: ObservableThresholdDraft = {
  operator: ">=",
  value: "",
  value2: "",
  unit: "",
};

const PHRASE_VALUE_RE =
  /\b(\d+(?:\.\d+)?)\s*(mm|cm|kg|g|%|mmol(?:\/[lL])?|years?|days?)?\b/i;

/** Seed threshold fields from guideline phrasing like "7 mm or more". */
export function guessThresholdFromPhrase(
  phrase: string | null | undefined,
): Partial<ObservableThresholdDraft> {
  if (!phrase) return {};
  const m = PHRASE_VALUE_RE.exec(phrase);
  if (!m) return {};
  const out: Partial<ObservableThresholdDraft> = { value: m[1] };
  if (m[2]) out.unit = m[2].toLowerCase();
  if (/\bor\s+more\b|\bat\s+least\b|>=/i.test(phrase)) out.operator = ">=";
  else if (/\bor\s+less\b|\bat\s+most\b|<=/i.test(phrase)) out.operator = "<=";
  return out;
}

export function emptyThresholdForHit(
  hit: ConceptSearchHit,
  phrase?: string | null,
): ObservableThresholdDraft {
  if (!isLikelyObservable(hit)) return { ...DEFAULT_OBS_THRESHOLD };
  return { ...DEFAULT_OBS_THRESHOLD, ...guessThresholdFromPhrase(phrase) };
}

export function draftHasNumericValue(draft: ObservableThresholdDraft): boolean {
  const n = Number(draft.value);
  return draft.value.trim() !== "" && Number.isFinite(n);
}

/**
 * Build an OBSERVATION seed when one measurable hit has a filled value.
 * Returns null when confirm should stay on the CONCEPT path.
 */
export function observationSeedFromPick(
  hit: ConceptSearchHit,
  draft: ObservableThresholdDraft,
): Partial<EditableObservationPayload> | null {
  if (!isLikelyObservable(hit) || !draftHasNumericValue(draft)) return null;
  const lo = Number(draft.value);
  const unit = draft.unit.trim();
  if (draft.operator === "between") {
    const hi = Number(draft.value2);
    if (!Number.isFinite(hi)) return null;
    return {
      observable_id: hit.snomed_concept_id,
      observable_term: hit.term,
      operator: "between",
      value: [lo, hi],
      unit,
    };
  }
  return {
    observable_id: hit.snomed_concept_id,
    observable_term: hit.term,
    operator: draft.operator,
    value: lo,
    unit,
  };
}

/** True when multi-select plus a filled value would drop the threshold. */
export function isConflictingObsMultiPick(
  selectedCount: number,
  drafts: Iterable<ObservableThresholdDraft>,
): boolean {
  if (selectedCount <= 1) return false;
  for (const d of drafts) {
    if (draftHasNumericValue(d)) return true;
  }
  return false;
}

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
