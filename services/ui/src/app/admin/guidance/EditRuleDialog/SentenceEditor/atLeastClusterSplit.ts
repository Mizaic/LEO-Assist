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
 * Descriptive wording is allowed between "following" and the colon
 * ("following unexplained symptoms:", and NG12 1.5.2's longer
 * "following symptoms on a persistent or frequent basis -- particularly
 * more than 12 times per month:"). The colon itself stays required so
 * ordinary prose that happens to contain "of the following" without
 * introducing a list does not match. Cap the gap so a later unrelated
 * colon cannot pull the marker across the whole recommendation.
 */
const AT_LEAST_MARKER_GAP = String.raw`[^:]{0,120}`;
const AT_LEAST_MARKER_RE = new RegExp(
  String.raw`\b(?:with\s+)?(?:any|either|(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+or\s+more)?)\s+of\s+the\s+following\b(?:${AT_LEAST_MARKER_GAP})?:\s*`,
  "i",
);

/** Captures the quantifier token ("any", "either", "2", "two", "1 or more", ...). */
const AT_LEAST_QUANTIFIER_RE =
  /\b(?:with\s+)?(any|either|(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+or\s+more)?)\s+of\s+the\s+following\b/i;

const WORD_MIN: Record<string, number> = {
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
};

/**
 * Parse the AT_LEAST threshold from guideline quantifier wording.
 * "any" / "either" / "1 or more" -> 1; "2 or more" / "two" -> 2.
 */
export function parseAtLeastSuggestedMin(text: string | null | undefined): number {
  if (!text) return 1;
  const match = AT_LEAST_QUANTIFIER_RE.exec(text);
  if (!match) return 1;
  const token = match[1].trim().toLowerCase();
  if (token === "any" || token === "either") return 1;
  const head = token.split(/\s+/)[0] ?? token;
  if (/^\d+$/.test(head)) return Math.max(1, parseInt(head, 10));
  return WORD_MIN[head] ?? 1;
}

/**
 * Drop post-recommendation caveats glued onto the last NICE list item
 * (NG12 1.3.1: FIT screening / rectal-mass prose after the anaemia clause).
 */
export function stripGuidelineCaveatTail(text: string): string {
  return text
    .replace(/\.\s+FIT should be offered[\s\S]*$/i, "")
    .replace(/\.\s+People with a rectal mass[\s\S]*$/i, "")
    // Rationale / "See NICE..." cross-ref tails (NG12 1.5.5). Do not
    // match "(see recommendations 1.5.6...)" mid-sentence.
    .replace(/,\s*because\b[\s\S]*$/i, "")
    .replace(/\s*\(See\s+NICE[\s\S]*$/i, "")
    .replace(/\.?\s*\[\d{4}\]\s*\.?$/i, "")
    .replace(/\.$/, "")
    .trim();
}

/**
 * Strip a leading age band and scaffolding "with"/"have" so Step 3 rows
 * are codeable clinical findings (NG12 1.3.1 "aged under 50 with rectal
 * bleeding and..." -> "rectal bleeding").
 */
export function stripLeadingAgePreamble(text: string): string {
  let t = text
    .trim()
    .replace(/^aged\s+(?:under\s+\d+|\d+\s+and\s+over)\s+(?:with\s+)?/i, "");
  t = t.replace(/^(?:with|have)\s+(?:an?\s+)?/i, "");
  t = t.replace(/\s+and\s*$/i, "").trim();
  return t;
}

/**
 * Peel "Only consider / Consider / Refer ... for people with X if Y"
 * into two clinical AND clauses (NG12 1.7.6 BCC + delay concern).
 * Returns null when the pattern is absent so callers keep a single row.
 */
export function peelReferralClinicalClauses(text: string): string[] | null {
  const trimmed = text.trim().replace(/^\d+(?:\.\d+)+\s+/, "");
  const withIf = trimmed.match(
    /^(?:only\s+)?(?:consider|refer)\b[\s\S]*?\bfor\s+people\s+with\s+(.+?)\s+if\s+(.+)$/i,
  );
  if (!withIf?.[1] || !withIf?.[2]) return null;
  const lesion = withIf[1].replace(/^(?:a|an)\s+/i, "").trim();
  const concern = withIf[2]
    .replace(/^(?:there\s+is\s+)/i, "")
    .replace(/^(?:a|an)\s+/i, "")
    .trim();
  if (!lesion || !concern) return null;
  return [lesion, concern];
}

/**
 * Strip "For people who have" / "who have" patient scaffolding from
 * lead-split situation rows (NG12 1.3.3). Also peels long action +
 * inclusive-sex + age leads down to the clinical clause after
 * "who has experienced" (NG12 1.5.5), and peels "Refer people using
 * a suspected cancer pathway referral if ..." down to the clinical
 * condition (NG12 1.7.2 dermoscopy / 1.1.4 CXR findings).
 */
export function stripPatientLeadScaffold(text: string): string {
  const trimmed = text.trim();
  const experienced = trimmed.match(/\bwho\s+has\s+experienced\s+(.+)$/i);
  if (experienced?.[1]) {
    return experienced[1].replace(/^(?:a|an)\s+/i, "").trim();
  }
  // Referral / offer action leads: keep only the clause after "if"
  // (not "Carry out..." IBS-style leads -- those use who-has-experienced).
  const referralIf = trimmed.match(
    /^(?:\d+(?:\.\d+)+\s+)?refer\s+(?:people|the\s+person)\b[\s\S]*?\bif\s+(.+)$/i,
  );
  if (referralIf?.[1]) {
    return referralIf[1]
      .replace(/^(?:they\s+(?:have|has|are)\s+)/i, "")
      .replace(/^(?:a|an)\s+/i, "")
      .trim();
  }
  return trimmed
    .replace(/^\d+(?:\.\d+)+\s+/, "")
    .replace(/^for\s+people\s+who\s+(?:have|has|are)\s+/i, "")
    .replace(/^people\s+who\s+(?:have|has|are)\s+/i, "")
    .replace(/^who\s+(?:have|has|are)\s+/i, "")
    .replace(/^(?:a|an)\s+/i, "")
    .trim();
}

/**
 * Short clinical findings that often sit in longer "if they have X and
 * have N or more..." prose ahead of a shared symptom list (NG12 1.1.2
 * "ever smoked", 1.1.5 asbestos exposure). Kept as an allow-list so
 * recommendation prose never invents a fake unresolved lead row.
 */
const EMBEDDED_LEAD_FINDINGS_RE =
  /\b(?:ever smoked|been exposed to asbestos|exposed to asbestos)\b/i;

function normaliseEmbeddedLead(raw: string): string {
  const lower = raw.trim().toLowerCase();
  if (lower.includes("asbestos")) return "exposed to asbestos";
  if (lower.includes("ever smoked")) return "ever smoked";
  return raw.trim();
}

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
  /**
   * Suggested `AT_LEAST.min` from the guideline quantifier -- 1 for
   * "any" / "1 or more", 2 for "2 or more", etc. Clamped by the
   * caller to the live item count when the subgroup is created.
   */
  suggestedMin: number;
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
 * Same as `AT_LEAST_MARKER_RE` but the trailing colon is optional.
 * Used when a shared structure list supplies the items (NG12 1.1.2
 * situation A ends at "...2 or more of the following unexplained
 * symptoms," with the colon / list living only on situation B).
 */
const AT_LEAST_MARKER_RELAXED_RE = new RegExp(
  String.raw`\b(?:with\s+)?(?:any|either|(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+or\s+more)?)\s+of\s+the\s+following\b(?:${AT_LEAST_MARKER_GAP})?`,
  "i",
);

function splitAtMarkerRelaxed(
  cleaned: string,
): { leadText: string; listText: string } | null {
  const match = AT_LEAST_MARKER_RELAXED_RE.exec(cleaned);
  if (!match) return null;
  const leadText = cleaned.slice(0, match.index).trim().replace(/[,;]+$/, "").trim();
  const after = cleaned.slice(match.index + match[0].length).replace(/^:\s*/, "");
  const listText = stripTrailingCitation(after);
  return { leadText, listText };
}

/**
 * Keep only a short clinical lead (e.g. "indigestion") ahead of an
 * AT_LEAST list. Drop long recommendation prose ("Offer an urgent...
 * if they have") so NG12 1.1.2 situation A does not invent a fake
 * unresolved lead row when the shared symptom list was attached from
 * structureChildren. Strips age bands (NG12 1.3.1 "aged under 50 with
 * rectal bleeding") and falls through to an allow-listed embedded
 * finding ("ever smoked") so situation B still gets a codeable smoking
 * row.
 */
function keepAsClusterLead(leadText: string): string {
  const trimmed = stripGuidelineCaveatTail(leadText);
  if (!trimmed) return "";

  // Age-stripped core first -- "aged under 50 with rectal bleeding and"
  // must keep "rectal bleeding", not disappear because of the age ban.
  const clinical = stripLeadingAgePreamble(trimmed);
  if (clinical && clinical !== trimmed) {
    if (looksLikeLeadOrCluster(clinical)) return clinical;
    if (
      clinical.length <= 48 &&
      clinical.split(/\s+/).length <= 6 &&
      !/\b(people|aged?|offer|consider|refer|assess)\b/i.test(clinical)
    ) {
      return clinical;
    }
  }

  if (looksLikeLeadOrCluster(trimmed)) return trimmed;
  // "if they have" / "they have" is guideline scaffolding, not a
  // finding -- fall through to the embedded-finding allow-list.
  const isScaffoldOnly = /^(if\s+)?they\s+have\b/i.test(trimmed);
  if (
    !isScaffoldOnly &&
    trimmed.length <= 48 &&
    trimmed.split(/\s+/).length <= 5 &&
    !/\b(people|aged?|offer|consider|refer|assess)\b/i.test(trimmed)
  ) {
    return trimmed;
  }
  const embedded = EMBEDDED_LEAD_FINDINGS_RE.exec(trimmed);
  return embedded ? normaliseEmbeddedLead(embedded[0]) : "";
}

/**
 * Builds the final `AtLeastClusterSplit`, detecting a lead-or cluster in
 * `leadText` (if any) and clearing `leadText` when one is found, since
 * `looksLikeLeadOrCluster` only matches when the whole lead-in is
 * nothing but that cluster's own terms.
 */
function buildClusterSplit(
  leadText: string,
  items: string[],
  markerSource: string,
): AtLeastClusterSplit | null {
  if (items.length === 0) return null;
  const usableLead = keepAsClusterLead(leadText);
  const leadCluster = looksLikeLeadOrCluster(usableLead);
  const suggestedMin = Math.min(
    parseAtLeastSuggestedMin(markerSource),
    Math.max(1, items.length),
  );
  return {
    leadText: leadCluster ? "" : usableLead,
    items,
    suggestedMin,
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
  const cleaned = cleanPathwayText(text);
  const split = splitAtMarker(cleaned);
  if (!split) return null;

  const items = split.listText
    .split(CLUSTER_ITEM_SPLIT_RE)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  return buildClusterSplit(split.leadText, items, cleaned);
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
/**
 * When structureChildren are present, NICE sometimes introduces the list with
 * "SYMPTOM who: ..." or "SYMPTOM, and: ..." rather than "any of the following:".
 * Split at that list-intro phrase so the lead clinical concept is preserved as
 * a codeable row in Step 3. Only used in the structure-backed path where the
 * actual items come from structureChildren, not from listText.
 */
function splitAtListIntroColon(
  cleaned: string,
): { leadText: string; listText: string } | null {
  const whoMatch = /^(.+?)\s+who\s*:\s*(.*)/is.exec(cleaned);
  if (whoMatch) {
    return { leadText: whoMatch[1].trim(), listText: (whoMatch[2] ?? "").trim() };
  }
  const andMatch = /^(.+?),\s*and\s*:\s*(.*)/is.exec(cleaned);
  if (andMatch) {
    return { leadText: andMatch[1].trim(), listText: (andMatch[2] ?? "").trim() };
  }
  return null;
}

export function resolveAtLeastCluster(
  boundary: Pick<PathwayTextBoundary, "text" | "source" | "structureChildren">,
): AtLeastClusterSplit | null {
  const children = boundary.structureChildren ?? [];
  if (children.length > 0) {
    // Prefer nested / shared structure items over re-parsing the flat
    // text. Heuristic pathways for NG12 1.1.2 also carry the shared
    // symptom `<ul>` here (see `splitPathways`), even though
    // `source === "heuristic"`.
    const items = children
      .map((c, i) =>
        i === children.length - 1 ? stripTrailingCitation(c.text) : c.text.trim(),
      )
      .filter((t) => t.length > 0);
    if (items.length === 0) return null;

    const cleaned = cleanPathwayText(boundary.text);
    const split =
      splitAtMarker(cleaned) ??
      splitAtMarkerRelaxed(cleaned) ??
      splitAtListIntroColon(cleaned);
    const leadText = split ? split.leadText : cleaned;
    // Prefer the pathway's own marker wording for suggestedMin; when
    // the marker lives only on the sibling situation (shared list on
    // A with colon on B), fall back to scanning cleaned + a joined
    // structure lead if present.
    const markerSource = split
      ? cleaned.slice(split.leadText.length)
      : cleaned;
    return buildClusterSplit(leadText, items, markerSource || cleaned);
  }
  return detectAtLeastCluster(boundary.text);
}
