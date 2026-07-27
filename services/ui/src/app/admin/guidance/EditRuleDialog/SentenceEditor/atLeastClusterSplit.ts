/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * "Any of the following" AT_LEAST cluster detection for the
 * highlight-to-build wizard's Step 3 (pathway conditions).
 *
 * Split out of `pathwayTextSplit.ts` (which owns Step 2's top-level
 * pathway boundaries) purely to keep both files under the project's
 * file-length limit -- the two concerns already had a clean seam:
 * Step 2 asks "how many situations are there?"; this module asks
 * "does a single situation's text read as an AT_LEAST(N) list?".
 */
import type { PathwayTextBoundary } from "./pathwayTextSplit";

/**
 * Marks the start of a nested "any of the following" / "with any of" list,
 * OR NICE's equally common numeric-quantifier phrasing ("2 or more of the
 * following unexplained symptoms:", "1 of the following:"). Both mean the
 * same thing -- "match at least N of the items below" -- so both must
 * gate the same AT_LEAST-cluster behaviour; only recognising the word
 * "any" missed NG12 1.1.2's "2 or more of the following unexplained
 * symptoms" entirely.
 *
 * A few descriptive words are allowed between "following" and the colon
 * ("following unexplained symptoms:") since NICE frequently names what
 * kind of list it is; the colon itself stays required whenever those
 * extra words are present, so this cannot fire on ordinary prose that
 * happens to contain "of the following" without actually introducing a
 * list.
 */
const AT_LEAST_MARKER_RE =
  /\b(?:with\s+)?(?:any|(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+or\s+more)?)\s+of\s+the\s+following\b(?:\s+\w+){0,4}:\s*/i;

/**
 * Whether `text` opens with (or contains) an "any of the following" /
 * numeric-quantifier list marker -- see `AT_LEAST_MARKER_RE`'s doc
 * comment. Exposed as a predicate (rather than exporting the regex
 * itself) so `pathwayTextSplit.ts`'s Step 2 boundary detection can gate
 * on the same signal without duplicating the pattern.
 */
export function hasAtLeastQuantifierMarker(text: string | null | undefined): boolean {
  return AT_LEAST_MARKER_RE.test(text ?? "");
}

/**
 * `splitPathwaysByOrHeuristic` (in `pathwayTextSplit.ts`) keeps its own
 * boundary slicing lossless (every character of the original text
 * belongs to exactly one segment) by attaching the trailing ", or "
 * connector to the END of the preceding segment rather than dropping
 * it. That is the right choice for offset fidelity (segments must
 * reconstruct the original text so highlight offsets stay valid), but
 * it means a segment fed into ``detectAtLeastCluster`` or shown as a
 * pathway's own display text can carry a dangling ", or" it does not
 * semantically own. Strip it before any content-level parsing.
 */
const TRAILING_CONNECTOR_RE = /,?\s*\bor\b\s*$/i;

/**
 * Strip a dangling trailing ", or" / " or" pathway-boundary connector
 * (see `TRAILING_CONNECTOR_RE`'s doc comment above) so a pathway's own
 * text reads as a complete phrase rather than one that trails off with
 * a connector belonging to the next pathway.
 */
export function cleanPathwayText(text: string): string {
  return text.replace(TRAILING_CONNECTOR_RE, "").trim();
}

export interface AtLeastClusterSplit {
  /** Text before the "any of the following" marker (the AND leaf, if any). */
  leadText: string;
  /** Individual list items after the marker, comma/or-separated. */
  items: string[];
  /**
   * A second, marker-less alternative cluster found in `leadText` before
   * it was consumed -- e.g. "nausea or vomiting" in "nausea or vomiting
   * with any of the following: weight loss, reflux, dyspepsia, upper
   * abdominal pain". Both this cluster and `items` apply to the SAME
   * pathway, ANDed together: every `leadCluster` alternative additionally
   * needs one of `items` to be present, not just any single alternative
   * overall. Undefined when `leadText` reads as ordinary prose instead
   * (see `looksLikeLeadOrCluster`'s guard-rails) -- the ordinary AND-leaf
   * behaviour applies and `leadText` is left populated as normal.
   */
  leadCluster?: string[];
}

/** Same comma/bare-"or" convention used for both trailing AT_LEAST list
 * items and (below) a candidate lead-or cluster's own terms. */
const CLUSTER_ITEM_SPLIT_RE = /,\s*|\s+\bor\b\s+/i;

/**
 * Recognises a short, marker-less "A or B [or C]" alternative sitting in
 * front of an AT_LEAST cluster's marker -- e.g. "nausea or vomiting" in
 * "nausea or vomiting with any of the following: ...". Deliberately
 * conservative: every term must be a short, punctuation-free noun phrase
 * (<=3 words, <=24 chars) and the WHOLE input must be nothing but those
 * terms joined by ", " / " or " connectors, so ordinary prose like
 * "abdominal pain or a change in bowel habit that has persisted for six
 * weeks" (too long/clausal to safely treat as a clean alternative list
 * without a human confirming it) or "people aged 55 or over" (a number,
 * not a term) is rejected rather than mis-split.
 *
 * Returns null when `text` does not look like this pattern -- the
 * caller should keep treating it as an ordinary AND-leaf.
 */
export function looksLikeLeadOrCluster(text: string): string[] | null {
  const trimmed = text.trim();
  if (!trimmed || !/\bor\b/i.test(trimmed)) return null;

  const parts = trimmed
    .split(CLUSTER_ITEM_SPLIT_RE)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  if (parts.length < 2 || parts.length > 4) return null;

  const isShortTerm = (s: string) =>
    s.length <= 24 && s.split(/\s+/).length <= 3 && /^[A-Za-z][A-Za-z\s-]*$/.test(s);
  if (!parts.every(isShortTerm)) return null;

  // Guard against silently dropping or picking up stray words: every
  // character of `trimmed` other than whitespace, commas, and the word
  // "or" must belong to one of `parts`.
  const strip = (s: string) => s.replace(/,|\bor\b/gi, "").replace(/\s+/g, "").toLowerCase();
  if (strip(trimmed) !== strip(parts.join(""))) return null;

  return parts;
}

/**
 * Recognises a plain clinical AND of short findings joined by "with"
 * or "and", with no "any of the following" marker -- e.g. NG12 1.2.9
 * situation B ("upper abdominal pain with low haemoglobin levels") or
 * a simple "nausea and vomiting" clause. Same conservatism as
 * `looksLikeLeadOrCluster`: each side must be a short noun phrase;
 * long clauses (and age phrasing like "55 and over") are left as a
 * single row. Rejects "with any of the following" (AT_LEAST path).
 *
 * Returns null when `text` should stay one unresolved row.
 */
export function looksLikeWithAnd(text: string): string[] | null {
  const trimmed = text.trim().replace(/\.$/, "");
  if (!trimmed) return null;
  if (/\bwith\s+any\s+of\s+the\s+following\b/i.test(trimmed)) return null;

  const isShortFinding = (s: string) =>
    s.length <= 40 &&
    s.split(/\s+/).length <= 5 &&
    /^[A-Za-z][A-Za-z\s-]*$/.test(s);

  for (const connector of [/\s+with\s+/i, /\s+and\s+/i]) {
    if (!connector.test(trimmed)) continue;
    const parts = trimmed
      .split(connector)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    if (parts.length < 2 || parts.length > 4) continue;
    if (!parts.every(isShortFinding)) continue;
    return parts;
  }
  return null;
}

/** Drop a trailing citation / sentence terminator like ". [2015]" from
 * the end of a cluster's own text -- shared by every path that produces
 * a lead-in or trailing-item string so a real backfilled `<li>`'s own
 * end-of-recommendation punctuation reads the same as the heuristic
 * path's already-cleaned text. */
function stripTrailingCitation(text: string): string {
  return text
    .trim()
    .replace(/\.?\s*\[\d{4}\]\s*\.?$/i, "")
    .replace(/\.$/, "")
    .trim();
}

/**
 * Split raw text at the "any of the following" marker into a lead-in
 * (everything before it, with a dangling comma/semicolon trimmed) and
 * the list text after it (trailing citation stripped). Returns null
 * when the marker is not present. Shared by both `detectAtLeastCluster`
 * (heuristic path) and `resolveAtLeastCluster` (structure path) so the
 * two branches agree on exactly where the marker sits and what counts
 * as "before" vs "after" it.
 */
function splitAtMarker(cleaned: string): { leadText: string; listText: string } | null {
  const match = AT_LEAST_MARKER_RE.exec(cleaned);
  if (!match) return null;
  const leadText = cleaned.slice(0, match.index).trim().replace(/[,;]+$/, "").trim();
  const listText = stripTrailingCitation(cleaned.slice(match.index + match[0].length));
  return { leadText, listText };
}

/**
 * Builds the final `AtLeastClusterSplit`, detecting a lead-or cluster in
 * `leadText` (if any) and clearing `leadText` when one is found, since
 * `looksLikeLeadOrCluster` only matches when the whole lead-in is
 * nothing but that cluster's own terms.
 */
function buildClusterSplit(leadText: string, items: string[]): AtLeastClusterSplit | null {
  if (items.length === 0) return null;
  const leadCluster = looksLikeLeadOrCluster(leadText);
  return {
    leadText: leadCluster ? "" : leadText,
    items,
    ...(leadCluster ? { leadCluster } : {}),
  };
}

/**
 * Detects the literal phrase "any of the following" / "with any of" in a
 * single pathway's text and splits it into a lead AND-condition (may be
 * empty, or itself a lead-or cluster -- see `looksLikeLeadOrCluster`)
 * plus the list of AT_LEAST(1) candidate items. Item splitting uses the
 * same comma/bare-"or" convention as the top-level heuristic: items are
 * comma-separated, with the final item joined by a bare "or" (no
 * preceding comma).
 *
 * Returns null when the marker phrase is not present -- the caller
 * should treat the whole segment as a single AND condition with no
 * AT_LEAST suggestion.
 */
export function detectAtLeastCluster(
  text: string | null | undefined,
): AtLeastClusterSplit | null {
  if (!text) return null;
  const split = splitAtMarker(cleanPathwayText(text));
  if (!split) return null;

  const items = split.listText
    .split(CLUSTER_ITEM_SPLIT_RE)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  return buildClusterSplit(split.leadText, items);
}

/**
 * Resolve a pathway's AT_LEAST cluster, preferring the guideline's own
 * nested `<ul>` (via `boundary.structureChildren`) over the "any of the
 * following" text heuristic. A structural item's own `text` still
 * carries its lead-in sentence AND the marker phrase itself (NICE's
 * markup keeps them in the same `<li>` paragraph, only the nested list
 * is split out -- see `nice_list_parser.py`'s `_own_text`), so the
 * marker still needs stripping here exactly as on the heuristic path.
 */
export function resolveAtLeastCluster(
  boundary: Pick<PathwayTextBoundary, "text" | "source" | "structureChildren">,
): AtLeastClusterSplit | null {
  if (boundary.source === "structure") {
    const children = boundary.structureChildren ?? [];
    const items = children
      .map((c, i) => (i === children.length - 1 ? stripTrailingCitation(c.text) : c.text.trim()))
      .filter((t) => t.length > 0);
    if (items.length === 0) return null;

    const split = splitAtMarker(boundary.text.trim());
    const leadText = split ? split.leadText : boundary.text.trim();
    return buildClusterSplit(leadText, items);
  }
  return detectAtLeastCluster(boundary.text);
}
