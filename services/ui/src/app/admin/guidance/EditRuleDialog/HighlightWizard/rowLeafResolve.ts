/**
 * Resolve a Step 3 structure row to an existing pathway leaf without
 * relying only on recommendation-text span geometry.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 *
 * AI-drafted CONCEPT leaves often carry a SNOMED preferred term
 * ("Dyspnea (finding)") or a UK surface form ("dyspnoea") that does
 * not sit at the same offsets as the guideline list row ("shortness
 * of breath"). Span-overlap matching alone then leaves the row
 * unresolved even though the leaf is the right clinical concept.
 */
import { friendlyTerm } from "../copy";
import type { RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";
import {
  findBestTextMatch,
  type TextMatchRange,
} from "../SentenceEditor/recommendationTextMatch";
import type { EditableLogicNode } from "../types";

/** Minimum score for a direct row-text match to count as resolved. */
const MIN_DIRECT_ROW_SCORE = 0.85;

/** Fraction of the cleaned row a candidate must cover. */
const MIN_DIRECT_ROW_COVERAGE = 0.7;

/**
 * Common NICE NG12 surface-form / SNOMED preferred-term pairs that
 * share meaning but almost no tokens. Keep this list short and
 * guideline-driven -- it is not a general medical thesaurus.
 */
const CLINICAL_SYNONYM_GROUPS: string[][] = [
  ["shortness of breath", "dyspnoea", "dyspnea", "breathlessness"],
  ["appetite loss", "loss of appetite", "decreased appetite"],
  ["weight loss", "weight decreased", "loss of weight"],
  ["reflux", "acid reflux"],
  ["dyspepsia", "indigestion"],
  ["haemoptysis", "hemoptysis"],
];

function normalisePhrase(raw: string): string {
  return raw
    .normalize("NFKC")
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** Strip NICE citation tails and leading "have/are/with" scaffolding. */
export function clinicalRowCore(rowText: string): string {
  let text = normalisePhrase(rowText);
  text = text.replace(/\s*\[[^\]]*]\s*\.?$/g, "").trim();
  text = text.replace(/[.,;:]+$/g, "").trim();
  text = text.replace(/^(have|has|are|is|with|and)\s+/g, "").trim();
  return text;
}

function contentTokens(phrase: string): string[] {
  return normalisePhrase(phrase)
    .split(/[^a-z0-9']+/)
    .filter((t) => t && !STOPWORDS.has(t));
}

const STOPWORDS = new Set([
  "a",
  "an",
  "the",
  "of",
  "with",
  "and",
  "or",
  "in",
  "to",
  "for",
  "is",
  "are",
  "any",
  "following",
  "these",
  "that",
  "have",
  "has",
]);

function tokenSetKey(tokens: string[]): string {
  return [...tokens].sort().join("|");
}

function synonymKey(phrase: string): string | null {
  const core = clinicalRowCore(phrase);
  if (!core) return null;
  for (let i = 0; i < CLINICAL_SYNONYM_GROUPS.length; i++) {
    const group = CLINICAL_SYNONYM_GROUPS[i];
    if (group.some((entry) => normalisePhrase(entry) === core)) {
      return `syn:${i}`;
    }
  }
  return null;
}

/** Candidate phrases a CONCEPT leaf may use to claim a structure row. */
export function leafMatchCandidates(node: EditableLogicNode): string[] {
  if (node.kind === "DEMOGRAPHIC") {
    const value = node.value != null ? String(node.value) : "";
    if (!value) return [];
    if (node.field === "sex") return [String(node.value)];
    return [`aged ${value}`, value];
  }
  if (node.kind !== "CONCEPT" || !node.criterion) return [];
  const c = node.criterion;
  const out: string[] = [];
  const push = (raw: string | null | undefined) => {
    if (!raw || !raw.trim()) return;
    const friendly = friendlyTerm(raw);
    if (friendly) out.push(friendly);
    if (raw.trim() !== friendly) out.push(raw.trim());
  };
  push(c.term);
  push(c.preferred_term);
  for (const seed of c.seeds ?? []) push(seed.preferred_term);
  return out;
}

function candidateCoversCore(candidate: string, core: string): boolean {
  if (!core || !candidate) return false;
  const candNorm = normalisePhrase(friendlyTerm(candidate) || candidate);
  if (!candNorm) return false;
  if (candNorm === core) return true;

  const coreTokens = contentTokens(core);
  const candTokens = contentTokens(candNorm);
  if (coreTokens.length === 0 || candTokens.length === 0) return false;
  if (tokenSetKey(coreTokens) === tokenSetKey(candTokens)) return true;

  const coreSyn = synonymKey(core);
  const candSyn = synonymKey(candNorm);
  if (coreSyn && candSyn && coreSyn === candSyn) return true;

  const match = findBestTextMatch(core, candNorm);
  if (!match) return false;
  if (match.strategy !== "exact" && match.score < MIN_DIRECT_ROW_SCORE) {
    return false;
  }
  const coreLen = Math.max(1, core.length);
  const overlap =
    Math.min(match.end, core.length) - Math.max(match.start, 0);
  return overlap / coreLen >= MIN_DIRECT_ROW_COVERAGE;
}

/**
 * True when `node` is the leaf that already answers this structure row,
 * judged from the row's own wording rather than quote-panel offsets.
 */
export function leafResolvesRowText(
  node: EditableLogicNode,
  row: RecommendationStructureItem,
): boolean {
  if (node.source_row_text && node.source_row_text === row.text) return true;
  const core = clinicalRowCore(row.text);
  if (!core) return false;
  return leafMatchCandidates(node).some((candidate) =>
    candidateCoversCore(candidate, core),
  );
}

/**
 * Whether a recommendation-text match is strong enough to auto-resolve
 * `row`, using the cleaned clinical core for coverage so citation
 * tails like "[2015, amended 2025]" do not block a real hit.
 */
export function matchCoversClinicalRow(
  match: TextMatchRange,
  row: RecommendationStructureItem,
): boolean {
  const core = clinicalRowCore(row.text);
  if (!core) return false;
  const overlap =
    Math.min(match.end, row.end) - Math.max(match.start, row.start);
  if (overlap <= 0) return false;
  // Measure coverage against the cleaned core length so short clinical
  // hits ("dysphagia", "dyspepsia") are not punished by "have " / citations.
  if (overlap / Math.max(1, core.length) >= MIN_DIRECT_ROW_COVERAGE) return true;
  const rowLen = Math.max(1, row.end - row.start);
  if (overlap / rowLen >= MIN_DIRECT_ROW_COVERAGE) return true;
  const tokens = (match.matchedText ?? "").trim().split(/\s+/).filter(Boolean);
  if (tokens.length >= 2 && overlap >= 10) return true;
  const matchedNorm = normalisePhrase(match.matchedText ?? "");
  return (
    match.strategy === "exact" &&
    (matchedNorm === core || core.endsWith(matchedNorm)) &&
    overlap >= matchedNorm.length
  );
}
