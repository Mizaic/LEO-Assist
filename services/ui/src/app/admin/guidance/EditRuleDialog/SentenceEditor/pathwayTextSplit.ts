/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Text-only pathway-boundary heuristic for the highlight-to-build wizard's
 * Step 2 ("does this split into different situations?").
 *
 * A structured `recommendation_structure` tree (see the plan's "Ingestion"
 * section) is always preferred when present -- its own `<li>` boundaries
 * are unambiguous. This module is the fallback used when no structure
 * exists yet (a local guideline, or a NICE guideline not yet backfilled).
 *
 * Heuristic, confirmed against the NG12 1.2.9 fixture text used throughout
 * this test suite: a **comma immediately before "or"** (", or") marks a
 * top-level pathway boundary; a **bare "or" with no preceding comma**
 * marks the final item of a nested "any of the following: a, b or c"
 * list. This distinction holds because English list style conventionally
 * omits the Oxford comma before the last item of an inline list ("a, b
 * or c") but always uses a comma before a conjunctive "or" joining two
 * independent clauses ("X, or Y"). It is a heuristic, not a parser -- the
 * wizard always shows the result as an adjustable suggestion, never a
 * silent auto-decision (per the plan).
 */

/**
 * Mirrors the JSON tree produced by the (upstream, ingestion-side)
 * recursive HTML list-tree parser -- see the plan's "Ingestion:
 * capture the guideline's own list structure" section. Each item's
 * ``text`` is that item's OWN text, already excluding any nested
 * ``children`` list -- exactly the split the wizard's UI wants
 * ("the parent row's own text... offered for concept-matching on
 * its own; the nested items render as indented child rows"), so no
 * further text-splitting is needed once structure is present.
 * ``start``/``end`` are offsets into the SAME flattened string as
 * ``recommendation_text``/``verbatim``, so a structural boundary and
 * a heuristic one are directly comparable / highlightable the same
 * way.
 */
export interface RecommendationStructureItem {
  text: string;
  start: number;
  end: number;
  children?: RecommendationStructureItem[];
}

/** Root shape of a recommendation's parsed `recommendation_structure`. */
export interface RecommendationStructure {
  lead_text: string;
  items: RecommendationStructureItem[];
  trailing_text?: string;
}

/**
 * Whether a pathway boundary was read directly off the guideline's own
 * markup (unambiguous) or inferred from the ", or " text heuristic (a
 * suggestion). Surfaced so the wizard can show "detected from the
 * guideline's own formatting" vs "suggested from the text" per the
 * plan -- never let the two look identically confident.
 */
export type PathwayBoundarySource = "structure" | "heuristic";

export interface PathwayTextBoundary {
  start: number;
  end: number;
  text: string;
  source: PathwayBoundarySource;
  /**
   * Present only when `source === "structure"` and the guideline's own
   * markup nested a `<ul>` under this item -- these ARE the AT_LEAST
   * candidate items, no further text parsing required. See
   * `resolveAtLeastCluster` below.
   */
  structureChildren?: RecommendationStructureItem[];
}

/**
 * Split boundary regex: a comma, optional whitespace, then the word
 * "or" as a whole word, then whitespace. Case-insensitive so "Or" at
 * the start of a sentence fragment still matches.
 *
 * The whitespace around the comma is deliberately `\s*` (zero or
 * more), not `\s+` -- real ingested guideline text has been observed
 * with the connector mashed together with no space at all (NG12
 * 1.2.9's verbatim contains a literal "...low haemoglobin
 * levels,or raised platelet count..."), and a stricter `\s+` here
 * silently fails to match that boundary, merging two real pathways
 * into one.
 */
const TOP_LEVEL_OR_RE = /,\s*or\b\s*/gi;

/**
 * Attempt to split `text` into top-level pathway segments using the
 * comma-before-"or" heuristic. Returns null when fewer than two
 * boundaries are found (fewer than 2 segments), signalling "this text
 * does not look like a pathway split" rather than forcing a spurious
 * single-pathway "split".
 */
export function splitPathwaysByOrHeuristic(
  text: string | null | undefined,
): PathwayTextBoundary[] | null {
  if (!text || !text.trim()) return null;

  const splitPoints: number[] = [];
  const re = new RegExp(TOP_LEVEL_OR_RE);
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    // The boundary is the start of the next segment, i.e. right after
    // the matched ", or " run (comma + whitespace + "or" + whitespace).
    splitPoints.push(match.index + match[0].length);
  }

  if (splitPoints.length === 0) return null;

  const boundaries: PathwayTextBoundary[] = [];
  let cursor = 0;
  for (const point of splitPoints) {
    boundaries.push({
      start: cursor,
      end: point,
      text: text.slice(cursor, point),
      source: "heuristic",
    });
    cursor = point;
  }
  boundaries.push({
    start: cursor,
    end: text.length,
    text: text.slice(cursor),
    source: "heuristic",
  });

  // A single trailing boundary that is only punctuation/whitespace
  // (e.g. a stray comma right before the citation year) is not a real
  // pathway -- drop it rather than showing the reviewer an empty row.
  const meaningful = boundaries.filter((b) => /[A-Za-z]/.test(b.text));
  return meaningful.length >= 2 ? meaningful : null;
}

/**
 * Structure-derived boundaries: when the guideline's own markup lists
 * 2+ top-level `<li>` items, those items ARE the pathways -- no
 * ambiguity, no heuristic needed. Returns null (not "fall back") on
 * anything less than 2 items, so `splitPathways` below falls through
 * to the text heuristic for a recommendation whose structure exists
 * but happens to be a flat single-item list.
 */
function splitPathwaysFromStructure(
  structure: RecommendationStructure | null | undefined,
): PathwayTextBoundary[] | null {
  if (!structure || !Array.isArray(structure.items)) return null;
  if (structure.items.length < 2) return null;
  return structure.items.map((item) => ({
    start: item.start,
    end: item.end,
    text: item.text,
    source: "structure" as const,
    structureChildren: item.children,
  }));
}

/**
 * The single entry point Step 2 should call: prefers the guideline's
 * own list structure when present (see the plan's "Ingestion" and
 * "How structure changes the UI" sections), falling back to the
 * ", or "-splitting text heuristic only when no structure exists yet
 * (a local guideline, or a NICE guideline not yet backfilled).
 */
export function splitPathways(
  text: string | null | undefined,
  structure?: RecommendationStructure | null,
): PathwayTextBoundary[] | null {
  return splitPathwaysFromStructure(structure) ?? splitPathwaysByOrHeuristic(text);
}

/**
 * True when `text` (plus optional structure) looks like a multi-pathway
 * recommendation. Thin, named wrapper so callers can ask a yes/no
 * question without re-deriving the boundaries twice.
 */
export function looksLikePathwaySplit(
  text: string | null | undefined,
  structure?: RecommendationStructure | null,
): boolean {
  return splitPathways(text, structure) !== null;
}

// ---------------------------------------------------------------------------
// "Any of the following" AT_LEAST cluster detection (Step 3)
// ---------------------------------------------------------------------------

/** Marks the start of a nested "any of the following" / "with any of" list. */
const AT_LEAST_MARKER_RE = /\b(?:with\s+)?any\s+of\s+the\s+following:?\s*/i;

/**
 * `splitPathwaysByOrHeuristic` keeps its own boundary slicing lossless
 * (every character of the original text belongs to exactly one
 * segment) by attaching the trailing ", or " connector to the END of
 * the preceding segment rather than dropping it. That is the right
 * choice for offset fidelity (segments must reconstruct the original
 * text so highlight offsets stay valid), but it means a segment
 * fed into ``detectAtLeastCluster`` or shown as a pathway's own
 * display text can carry a dangling ", or" it does not semantically
 * own. Strip it before any content-level parsing.
 */
const TRAILING_CONNECTOR_RE = /,?\s*\bor\b\s*$/i;

/**
 * Strip a dangling trailing ", or" / " or" pathway-boundary connector
 * (see `splitPathwaysByOrHeuristic`'s slicing note above) so a
 * pathway's own text reads as a complete phrase rather than one that
 * trails off with a connector belonging to the next pathway.
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
