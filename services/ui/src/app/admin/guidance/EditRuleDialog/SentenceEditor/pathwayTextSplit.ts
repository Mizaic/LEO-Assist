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
import { hasAtLeastQuantifierMarker } from "./atLeastClusterSplit";

export {
  cleanPathwayText,
  detectAtLeastCluster,
  looksLikeLeadOrCluster,
  looksLikeWithAnd,
  resolveAtLeastCluster,
  type AtLeastClusterSplit,
} from "./atLeastClusterSplit";

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
 * markup (unambiguous), inferred from the ", or " text heuristic (a
 * suggestion), or reconstructed from an already-saved logic tree when
 * the guideline sentence has no listable situations (e.g. "according
 * to the thresholds in table 1"). Surfaced so the wizard can show
 * "detected from the guideline's own formatting" vs "suggested from
 * the text" vs "from the saved rule" -- never let the three look
 * identically confident.
 */
export type PathwayBoundarySource = "structure" | "heuristic" | "tree";

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
 * True when the raw text connecting two adjacent top-level structure
 * items reads as an alternative ("upper abdominal pain, OR
 * indigestion...") rather than a conjunctive list of things to do
 * together ("a full blood count, AND blood tests for: ..."). A
 * guideline's own `<ul>` markup is not, by itself, evidence that the
 * list items are different clinical situations -- NICE also renders a
 * single situation's multi-part action list (e.g. NG12 1.10.4's "a
 * full blood count, and blood tests for: ...") as a `<ul>`, and
 * treating that as 2 situations would wrongly turn one recommendation
 * into two independent rules. Only an "or" connector between items
 * counts as a genuine situation split; an "and" connector (or any
 * connector without the word "or") means the items belong to the same
 * situation and structure-derived splitting must not fire.
 */
function connectorReadsAsOr(text: string, prevEnd: number, nextStart: number): boolean {
  const gap = text.slice(prevEnd, nextStart);
  if (/\bor\b/i.test(gap)) return true;
  if (/\band\b/i.test(gap)) return false;
  // No connector word present in the gap at all (e.g. genuine bullet
  // points with no inline prose joining them) -- nothing tells us
  // this ISN'T a situation split, so keep the historical "trust the
  // guideline's own structure" default.
  return true;
}

/**
 * Sentinel returned by `splitPathwaysFromStructure` when the
 * guideline's own structure gives POSITIVE evidence that a 2+ item
 * list is a single situation's AND'd action list, not a situation
 * split. Distinct from returning `null` for "no structure opinion
 * either way" (too few items, or no structure at all) -- that case
 * SHOULD fall through to the flat-text ", or " heuristic below, but
 * an explicit "and"-joined structure must not, because the heuristic
 * scans the WHOLE recommendation text and can misfire on an unrelated
 * ", or" elsewhere in the sentence (e.g. a qualifying-symptom clause
 * like "...persistent bone pain, particularly back pain, or
 * unexplained fracture..." ahead of the actual action list).
 */
const NOT_A_SITUATION_SPLIT = Symbol("not-a-situation-split");

/**
 * True when 2+ of `structure.items` fall inside the SAME ", or "
 * heuristic segment of `text` -- decisive, wording-independent evidence
 * that those items are members of one shared list sitting inside a
 * single real situation, not one-item-per-situation. This is the same
 * signal `AT_LEAST_MARKER_RE` looks for (a quantifier lead-in like "2 or
 * more of the following unexplained symptoms:"), but derived directly
 * from where the guideline's own prose actually splits rather than from
 * guessing every phrasing NICE might use to introduce that list --
 * belt-and-braces for ingested `lead_text` that does not literally
 * contain "of the following" in a form the marker regex recognises.
 * Returns false (no verdict, not "definitely fine") whenever the
 * heuristic itself finds nothing usable, so the caller's other checks
 * still apply.
 */
function structureItemsShareAHeuristicSegment(
  text: string,
  items: RecommendationStructureItem[],
): boolean {
  const heuristicBoundaries = splitPathwaysByOrHeuristic(text);
  if (!heuristicBoundaries || heuristicBoundaries.length === items.length) return false;
  const touchedSegments = new Set(
    items.map((item) =>
      heuristicBoundaries.findIndex((b) => item.start >= b.start && item.start < b.end),
    ),
  );
  return touchedSegments.size < items.length;
}

/**
 * Structure-derived boundaries: when the guideline's own markup lists
 * 2+ top-level `<li>` items AND they are joined by "or" (not "and"),
 * those items ARE the pathways -- no ambiguity, no heuristic needed.
 * Returns null (not "fall back") on anything less than 2 items, so
 * `splitPathways` below falls through to the text heuristic for a
 * recommendation whose structure exists but happens to be a flat
 * single-item list. Returns `NOT_A_SITUATION_SPLIT` (a stronger, no
 * fall-through signal) when 2+ items exist but are "and"-joined -- a
 * single situation's action list, not separate situations.
 */
function splitPathwaysFromStructure(
  text: string | null | undefined,
  structure: RecommendationStructure | null | undefined,
): PathwayTextBoundary[] | null | typeof NOT_A_SITUATION_SPLIT {
  if (!structure || !Array.isArray(structure.items)) return null;
  if (structure.items.length < 2) return null;
  // A quantifier lead-in ("2 or more of the following unexplained
  // symptoms:", "any of the following:") right before the list is
  // decisive evidence the list is ONE shared AT_LEAST(N) collection of
  // findings, not several independent situations -- regardless of how
  // the bare commas between items would otherwise read. Unlike the
  // "and"-joined case below, this does not mean there is only one
  // situation overall: NG12 1.1.2's real 2-way split ("2 or more of...,
  // or ... 1 or more of...") lives in the PROSE before this list, so
  // returning plain `null` (not `NOT_A_SITUATION_SPLIT`) lets
  // `splitPathways` fall through to the flat-text ", or " heuristic,
  // which scans that lead-in prose instead of the list itself.
  if (hasAtLeastQuantifierMarker(structure.lead_text)) return null;
  if (text) {
    for (let i = 0; i < structure.items.length - 1; i++) {
      const { end } = structure.items[i];
      const { start } = structure.items[i + 1];
      if (!connectorReadsAsOr(text, end, start)) return NOT_A_SITUATION_SPLIT;
    }
    // Second, wording-independent safety net for the same "shared list"
    // shape -- see `structureItemsShareAHeuristicSegment`'s doc comment.
    if (structureItemsShareAHeuristicSegment(text, structure.items)) return null;
  }
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
 * (a local guideline, or a NICE guideline not yet backfilled) or the
 * structure has fewer than 2 items. When the structure explicitly
 * says a 2+ item list is "and"-joined (one situation, not several),
 * that verdict is final -- no fall-through to the text heuristic,
 * which could otherwise misfire on an unrelated ", or" elsewhere in
 * the sentence.
 */
export function splitPathways(
  text: string | null | undefined,
  structure?: RecommendationStructure | null,
): PathwayTextBoundary[] | null {
  const structural = splitPathwaysFromStructure(text, structure);
  if (structural === NOT_A_SITUATION_SPLIT) return null;
  return structural ?? splitPathwaysByOrHeuristic(text);
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
