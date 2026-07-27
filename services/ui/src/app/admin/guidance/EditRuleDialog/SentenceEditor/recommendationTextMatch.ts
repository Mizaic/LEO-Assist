/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Fuzzy text matcher: given the guideline's verbatim recommendation text
 * and a candidate phrase (a leaf's ``term`` / ``preferred_term`` /
 * ``original_phrase``, or a free-typed search query), find the best
 * matching span of the *original* text so the wizard can draw a
 * highlight over it.
 *
 * No character-offset provenance exists anywhere in the persisted rule
 * (see the plan's "Feasibility already confirmed" section) -- this is a
 * live, read-only, client-side match computed fresh on every render
 * against whatever text the leaf already carries. Nothing is persisted.
 *
 * Strategy, cheapest first:
 *   1. Exact (case-insensitive, whitespace-normalised) substring match.
 *   2. Token-overlap: slide a window of the candidate's own token count
 *      across the text's tokens, score each window by how many of the
 *      candidate's tokens it contains, return the highest-scoring window
 *      above a minimum threshold.
 *
 * No heavy NLP dependency -- both passes are plain string/array ops, safe
 * to run on every keystroke or render.
 */

export type TextMatchStrategy = "exact" | "token-overlap";

export interface TextMatchRange {
  /** Start offset into the ORIGINAL (un-normalised) recommendationText. */
  start: number;
  /** End offset (exclusive) into the ORIGINAL recommendationText. */
  end: number;
  /** The literal substring of recommendationText spanned by [start, end). */
  matchedText: string;
  strategy: TextMatchStrategy;
  /** 1.0 for an exact match; 0..1 token-overlap ratio otherwise. */
  score: number;
}

interface Token {
  /** Lowercased word text, punctuation stripped. */
  text: string;
  start: number;
  end: number;
}

/** Minimum token-overlap ratio for a fallback match to be usable at all. */
export const MIN_TOKEN_OVERLAP_SCORE = 0.5;

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
]);

/**
 * Tokenise text into lowercase word tokens with offsets into the
 * ORIGINAL string. Punctuation is stripped from token text but not
 * from the surrounding string, so offsets stay accurate for
 * highlighting purposes.
 */
function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  const re = /[A-Za-z0-9']+/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    tokens.push({
      text: match[0].toLowerCase(),
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  return tokens;
}

function normaliseForCompare(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, " ");
}

/**
 * Fast path: case-insensitive, whitespace-normalised substring search.
 * Returns null when the candidate does not appear verbatim (modulo
 * whitespace/case) anywhere in the text.
 */
function exactMatch(text: string, candidate: string): TextMatchRange | null {
  const needle = normaliseForCompare(candidate);
  if (!needle) return null;

  // Build a lowercased, whitespace-collapsed copy of `text` while
  // tracking, for every character in the collapsed copy, the offset
  // it came from in the original -- so a match in the collapsed
  // string can be mapped back to real offsets.
  const collapsed: string[] = [];
  const offsets: number[] = [];
  let lastWasSpace = true; // treat leading whitespace as already-collapsed
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const isSpace = /\s/.test(ch);
    if (isSpace) {
      if (lastWasSpace) continue;
      collapsed.push(" ");
      offsets.push(i);
      lastWasSpace = true;
    } else {
      collapsed.push(ch.toLowerCase());
      offsets.push(i);
      lastWasSpace = false;
    }
  }
  const haystack = collapsed.join("");
  const idx = haystack.indexOf(needle);
  if (idx < 0) return null;

  const start = offsets[idx];
  const lastIdx = idx + needle.length - 1;
  // offsets[lastIdx] is the original index of the last matched char;
  // the exclusive end is one past that character's own length (1, since
  // collapsed chars map 1:1 to a single original char each).
  const end = offsets[lastIdx] + 1;
  return {
    start,
    end,
    matchedText: text.slice(start, end),
    strategy: "exact",
    score: 1,
  };
}

/**
 * Fallback: slide a window across the text's tokens, sized to the
 * candidate's own token count (+/- a little slack for phrasing drift),
 * and score each window by the fraction of candidate tokens it
 * contains (stopwords excluded from both sides so "with" / "the" /
 * "or" never drive a match on their own).
 */
function tokenOverlapMatch(
  text: string,
  candidate: string,
): TextMatchRange | null {
  const candidateTokens = tokenize(candidate)
    .map((t) => t.text)
    .filter((t) => !STOPWORDS.has(t));
  if (candidateTokens.length === 0) return null;
  const candidateSet = new Set(candidateTokens);

  const textTokens = tokenize(text);
  if (textTokens.length === 0) return null;

  const windowSize = Math.max(1, candidateTokens.length);
  let best: { score: number; startIdx: number; endIdx: number } | null =
    null;

  // Try windows from windowSize-1 up to windowSize+2 tokens so a
  // slightly longer or shorter guideline phrasing still matches (e.g.
  // "acid reflux (heartburn)" candidate vs. plain "heartburn" in text).
  for (let size = Math.max(1, windowSize - 1); size <= windowSize + 2; size++) {
    for (let i = 0; i + size <= textTokens.length; i++) {
      const windowTokens = textTokens.slice(i, i + size);
      const windowWords = windowTokens
        .map((t) => t.text)
        .filter((t) => !STOPWORDS.has(t));
      if (windowWords.length === 0) continue;
      const windowSet = new Set(windowWords);
      let hits = 0;
      for (const w of windowSet) {
        if (candidateSet.has(w)) hits += 1;
      }
      // Symmetric-ish score: how much of the candidate is covered,
      // penalised a little for a window that's mostly extra words.
      const coverage = hits / candidateSet.size;
      const precision = hits / windowSet.size;
      const score = (coverage + precision) / 2;
      if (!best || score > best.score) {
        best = { score, startIdx: i, endIdx: i + size - 1 };
      }
    }
  }

  if (!best || best.score < MIN_TOKEN_OVERLAP_SCORE) return null;

  const startToken = textTokens[best.startIdx];
  const endToken = textTokens[best.endIdx];
  return {
    start: startToken.start,
    end: endToken.end,
    matchedText: text.slice(startToken.start, endToken.end),
    strategy: "token-overlap",
    score: best.score,
  };
}

/**
 * Find the best matching span of `recommendationText` for `candidate`.
 * Tries an exact substring match first, then falls back to token
 * overlap. Returns null when nothing scores above the usable threshold
 * (the caller should show the leaf as "no clean textual anchor" per
 * the wireframes' fallback state, not force a low-quality highlight).
 */
export function findBestTextMatch(
  recommendationText: string | null | undefined,
  candidate: string | null | undefined,
): TextMatchRange | null {
  if (!recommendationText || !candidate) return null;
  const exact = exactMatch(recommendationText, candidate);
  if (exact) return exact;
  return tokenOverlapMatch(recommendationText, candidate);
}

/**
 * Convenience wrapper for a criterion-shaped leaf: tries
 * ``preferred_term``, then ``term``, in that order (the friendlier
 * clinical label is usually closer to the guideline's own wording than
 * the raw search query that produced it).
 */
export function findBestTextMatchForCriterion(
  recommendationText: string | null | undefined,
  criterion: { preferred_term?: string; term?: string } | null | undefined,
): TextMatchRange | null {
  if (!criterion) return null;
  const byPreferred = findBestTextMatch(
    recommendationText,
    criterion.preferred_term,
  );
  if (byPreferred) return byPreferred;
  return findBestTextMatch(recommendationText, criterion.term);
}

/**
 * Every non-overlapping match for a criterion that may bundle several
 * alternative findings into one chip ("Add another code that means
 * the same" -- e.g. one CONCEPT leaf covering "abnormal blood test",
 * "hemoglobin below reference range", "raised ESR", ...). Reviewers
 * need to see EVERY one of those words light up in the guideline
 * quote, not just the chip's headline term -- otherwise a leaf that
 * has genuinely captured ten findings looks like it only captured
 * one or two, which is exactly the "why is barely anything
 * highlighted" confusion this fixes.
 */
export function findAllTextMatchesForCriterion(
  recommendationText: string | null | undefined,
  criterion:
    | {
        preferred_term?: string;
        term?: string;
        seeds?: Array<{ preferred_term?: string }>;
      }
    | null
    | undefined,
): TextMatchRange[] {
  if (!recommendationText || !criterion) return [];
  const candidates = [
    criterion.preferred_term,
    criterion.term,
    ...(criterion.seeds ?? []).map((seed) => seed.preferred_term),
  ].filter((c): c is string => Boolean(c && c.trim()));

  const matches: TextMatchRange[] = [];
  for (const candidate of candidates) {
    const match = findBestTextMatch(recommendationText, candidate);
    if (!match) continue;
    const overlapsExisting = matches.some(
      (existing) => match.start < existing.end && match.end > existing.start,
    );
    if (!overlapsExisting) matches.push(match);
  }
  return matches;
}

/**
 * Given a set of already-matched ranges (sorted or not), returns the
 * gaps between them as plain (unmatched) spans, plus any leading/
 * trailing gap -- used by ``HighlightableRecommendationText`` to render
 * confirmed highlights, candidate highlights, and plain text without
 * overlap.
 */
export function computeTextSegments(
  text: string,
  ranges: TextMatchRange[],
): Array<{ start: number; end: number; text: string; range: TextMatchRange | null }> {
  const sorted = [...ranges].sort((a, b) => a.start - b.start);
  const segments: Array<{
    start: number;
    end: number;
    text: string;
    range: TextMatchRange | null;
  }> = [];
  let cursor = 0;
  for (const r of sorted) {
    if (r.start > cursor) {
      segments.push({ start: cursor, end: r.start, text: text.slice(cursor, r.start), range: null });
    }
    if (r.start >= cursor) {
      segments.push({ start: r.start, end: r.end, text: text.slice(r.start, r.end), range: r });
      cursor = r.end;
    }
    // Overlapping range (start < cursor): skip it -- first-come-first-served,
    // the caller is responsible for not feeding in overlapping ranges when
    // it matters which one wins.
  }
  if (cursor < text.length) {
    segments.push({ start: cursor, end: text.length, text: text.slice(cursor), range: null });
  }
  return segments;
}
