/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
// Shared encounter search relevance helpers (DI-LEO-AI-520).
//
// Mirrors the deterministic part of the server's encounter query
// understanding (services/analytics_api/app/services/
// encounter_query_understanding.py) so the patient-detail drawer's
// in-memory search uses the same vocabulary -- typo correction,
// synonym expansion, and the same match-rationale shape -- as the
// host search on /care/encounters.
//
// The drawer already loads the full encounter set for the timeline,
// so client-side scoring is cheaper than a per-keystroke server hop.
// This module gives both surfaces the same notion of "term hit" and
// "expanded term" without changing what the host fetches from the
// backend.
//
// Do NOT mirror the LLM-driven Haiku rewrite here -- that path is
// optional on the server and only surfaces extra `clinical_synonyms`
// for highlighting. Drawer parity covers the deterministic floor.

const TOKEN_RE = /[A-Za-z0-9]+/g;
const MIN_TERM_LEN = 2;
const MAX_TERMS = 12;
const MAX_EXPANDED = MAX_TERMS * 3;

// Keep these in lock-step with `_TYPO_MAP` in the server module.
const TYPO_MAP: Record<string, string> = {
  breat: "breast",
  wight: "weight",
  lums: "lumps",
  tumor: "tumour",
};

// Keep these in lock-step with `_SYNONYM_MAP` in the server module.
const SYNONYM_MAP: Record<string, string[]> = {
  breast: ["breast", "mammary"],
  lump: ["lump", "mass", "swelling", "nodule"],
  weight: ["weight", "weightloss", "weight_loss", "cachexia"],
  loss: ["loss", "losing", "reduced"],
  cough: ["cough", "coughing"],
  bleeding: ["bleeding", "blood_loss", "haemorrhage", "hemorrhage"],
};

function normaliseTokens(rawQuery: string): string[] {
  const tokens = (rawQuery.toLowerCase().match(TOKEN_RE) ?? []).map(
    (tok) => TYPO_MAP[tok] ?? tok,
  );
  return tokens.filter((tok) => tok.length >= MIN_TERM_LEN);
}

/**
 * Deterministically expand the reviewer's free-text query into the
 * set of terms used to score and highlight encounter text. Tokens
 * shorter than {@link MIN_TERM_LEN} characters are dropped, common
 * typos are corrected, and the configured synonym map is applied.
 *
 * Returns an empty list when the query is blank or only whitespace.
 */
export function expandSearchTerms(query: string | undefined): string[] {
  if (!query) return [];
  const tokens = normaliseTokens(query).slice(0, MAX_TERMS);
  if (tokens.length === 0) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const tok of tokens) {
    const expansions = SYNONYM_MAP[tok] ?? [tok];
    for (const term of expansions) {
      if (seen.has(term)) continue;
      seen.add(term);
      out.push(term);
      if (out.length >= MAX_EXPANDED) return out;
    }
  }
  return out;
}

export interface MatchRationale {
  termHits: number;
  hitTerms: string[];
  termCoverage: number;
}

/**
 * Mirror of the server's `feature_match_rationale` for client use.
 * Returns the set of expanded terms found in `text` (case-insensitive,
 * substring), capped at 8 hit terms to keep chip rows readable.
 */
export function computeMatchRationale(
  text: string | null | undefined,
  expandedTerms: string[],
): MatchRationale {
  if (!expandedTerms.length || !text) {
    return { termHits: 0, hitTerms: [], termCoverage: 0 };
  }
  const haystack = text.toLowerCase();
  const hits: string[] = [];
  for (const term of expandedTerms) {
    if (!term) continue;
    if (haystack.includes(term.toLowerCase())) hits.push(term);
  }
  return {
    termHits: hits.length,
    hitTerms: hits.slice(0, 8),
    termCoverage: hits.length / Math.max(1, expandedTerms.length),
  };
}

/**
 * True when at least one expanded term is found in `text`. Used by
 * `applyCommonFilters` to keep an encounter visible when its text
 * matches the query OR any of the deterministic synonyms.
 */
export function hasAnyExpandedHit(
  text: string | null | undefined,
  expandedTerms: string[],
): boolean {
  if (!expandedTerms.length) return true;
  if (!text) return false;
  const haystack = text.toLowerCase();
  for (const term of expandedTerms) {
    if (term && haystack.includes(term.toLowerCase())) return true;
  }
  return false;
}
