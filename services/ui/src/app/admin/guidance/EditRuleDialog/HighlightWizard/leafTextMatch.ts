/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * "Where does this leaf's own value live in the guideline's verbatim
 * text?" -- shared by every wizard step that needs to fuzzy-anchor a
 * real tree leaf (CONCEPT / DEMOGRAPHIC / OBSERVATION) onto the
 * recommendation text: StepPrerequisites (Step 1, anchoring existing
 * always-true leaves) and the wizard orchestrator (Step 3, deciding
 * whether a row already has a matching leaf anywhere under the
 * pathway). Extracted once so both stay in agreement on what counts
 * as a match, instead of drifting apart as two near-identical copies.
 */
import type { HighlightSpan } from "../SentenceEditor/HighlightableRecommendationText";
import {
  findAllTextMatchesForCriterion,
  findBestTextMatch,
  type TextMatchRange,
} from "../SentenceEditor/recommendationTextMatch";
import type { EditableLogicNode } from "../types";

/**
 * A DEMOGRAPHIC leaf's own fields (field/operator/value) carry no
 * wording of their own -- build a short phrase close to how NICE
 * actually writes ages ("aged 55 or over") so the fuzzy matcher has
 * a real chance against the verbatim text, instead of matching only
 * the bare number.
 */
export function demographicMatchCandidate(node: EditableLogicNode): string | null {
  return demographicMatchCandidates(node)[0] ?? null;
}

/**
 * Candidate guideline phrases for a DEMOGRAPHIC leaf, preferred first.
 * Numeric "aged N or under" is tried alongside NICE glossary labels
 * ("children and young people" for age <= 24) so a manually added age
 * band still anchors onto the quote (NG12 1.10.2).
 */
export function demographicMatchCandidates(node: EditableLogicNode): string[] {
  const value = node.value != null ? String(node.value) : "";
  if (!value) return [];
  if (node.field === "sex") {
    const sex = value.toLowerCase();
    if (sex === "m" || sex === "male") return ["male", "men", "man"];
    if (sex === "f" || sex === "female") return ["female", "women", "woman"];
    return [value];
  }
  if (node.field !== "age") return [];

  const out: string[] = [];
  const op = node.operator ?? ">=";
  const n = Number(value);
  const n2 = node.value2 != null ? Number(node.value2) : NaN;
  // NICE glossary bands first -- recommendations usually say the label
  // ("children and young people"), not the numeric threshold from the
  // definition. Keep in sync with demographicPhraseMatch.
  if ((op === "<=" || op === "<") && (n === 24 || n === 25)) {
    out.push("children and young people");
  }
  if ((op === "<=" || op === "<") && (n === 15 || n === 16)) {
    out.push("children");
  }
  if (op === "between" && n === 16 && n2 === 24) {
    out.push("young people");
  }
  if ((op === ">=" || op === ">") && (n === 18 || n === 25)) {
    out.push("adults");
  }

  if (op === "between" && node.value2 != null) {
    out.push(`${value} to ${node.value2}`);
    out.push(`aged ${value} to ${node.value2}`);
  } else if (op === "<") {
    // NICE NG12 1.3.1 E: "aged under 50" -- prefer that over "or less".
    out.push(`aged under ${value}`);
    out.push(`under the age of ${value}`);
    out.push(`aged ${value} or less`);
  } else if (op === "<=") {
    out.push(`aged ${value} or under`);
    out.push(`aged ${value} and under`);
    out.push(`aged under ${value}`);
  } else {
    const suffix: Record<string, string> = {
      ">=": "or over",
      ">": "or more",
      "=": "",
    };
    out.push(`aged ${value} ${suffix[op] ?? ""}`.trim());
    if (op === ">=") {
      out.push(`aged ${value} and over`);
    }
  }
  return out;
}

/** Best-guess highlight range for one leaf, or null when nothing in
 *  the text anchors it (the wireframes' "no clean textual anchor"
 *  fallback). Only CONCEPT / DEMOGRAPHIC / OBSERVATION carry wording
 *  a reviewer would have highlighted; every other leaf kind (RULE_FIRED,
 *  MEDICATION, ...) has no verbatim text to anchor to.
 *
 *  Prefers `source_row_text` (the exact guideline phrasing the wizard
 *  added this leaf for) over the SNOMED preferred term -- a picked
 *  code like "Indigestion" often shares no words with the row that
 *  reads "treatment-resistant dyspepsia", and falling back to the
 *  preferred term alone is exactly how the quote-panel highlighter
 *  used to silently skip those words. */
export function leafTextMatch(
  recommendationText: string | null | undefined,
  node: EditableLogicNode,
): TextMatchRange | null {
  return leafTextMatches(recommendationText, node)[0] ?? null;
}

/**
 * Every anchor for one leaf, not just the best one. A CONCEPT leaf
 * built from several synonym seeds ("Add another code that means the
 * same") can legitimately anchor onto several different phrases in
 * the guideline text at once -- `leafTextMatch` above only ever
 * surfaces the single best of those, which is right for "does this
 * leaf have SOME anchor?" checks but wrong for a highlighter that is
 * meant to show a reviewer everything they've already captured (see
 * `collectTreeHighlights` and `StepPrerequisites`'s "Captured so
 * far" panel).
 */
function findDisconnectedSourceMatches(
  recommendationText: string,
  sourceRowText: string,
): TextMatchRange[] | null {
  const words = sourceRowText.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return null;

  const spans: TextMatchRange[] = [];
  let cursor = 0;
  let i = 0;
  while (i < words.length) {
    let bestMatch: TextMatchRange | null = null;
    let bestEndIdx = i;
    for (let j = words.length; j > i; j--) {
      const candidate = words.slice(i, j).join(" ");
      const match = findBestTextMatch(recommendationText.slice(cursor), candidate);
      if (match?.strategy === "exact") {
        bestMatch = {
          ...match,
          start: cursor + match.start,
          end: cursor + match.end,
        };
        bestEndIdx = j;
        break;
      }
    }
    if (!bestMatch) return null;
    spans.push(bestMatch);
    cursor = bestMatch.end;
    i = bestEndIdx;
  }
  return spans.length >= 2 ? spans : null;
}

export function leafTextMatches(
  recommendationText: string | null | undefined,
  node: EditableLogicNode,
): TextMatchRange[] {
  if (node.source_row_text) {
    const bySource = findBestTextMatch(recommendationText, node.source_row_text);
    if (bySource?.strategy === "exact") return [bySource];
    const disconnected = recommendationText
      ? findDisconnectedSourceMatches(recommendationText, node.source_row_text)
      : null;
    if (disconnected) return disconnected;
    if (bySource) return [bySource];
  }
  if (node.kind === "CONCEPT") {
    return findAllTextMatchesForCriterion(recommendationText, node.criterion);
  }
  if (node.kind === "DEMOGRAPHIC") {
    for (const candidate of demographicMatchCandidates(node)) {
      const match = findBestTextMatch(recommendationText, candidate);
      if (match) return [match];
    }
    return [];
  }
  if (node.kind === "OBSERVATION") {
    const match = findBestTextMatch(recommendationText, node.observation?.observable_term);
    return match ? [match] : [];
  }
  return [];
}

/**
 * Every leaf in `tree` (any depth, any pathway) that anchors onto
 * `recommendationText`, as "confirmed" highlight spans -- lets a
 * read-only surface like GuidelineQuotePanel show a reviewer which
 * words they've already turned into rule conditions, without them
 * having to re-scroll between the canvas and the guideline quote to
 * check. Walks every child regardless of node kind (group nodes
 * simply never match in `leafTextMatch`), so it works for a tree at
 * any stage of the wizard -- a single prerequisite, a fully split set
 * of pathways, or anything in between.
 */
export function collectTreeHighlights(
  recommendationText: string | null | undefined,
  tree: EditableLogicNode | null | undefined,
): HighlightSpan[] {
  if (!recommendationText || !tree) return [];
  const spans: HighlightSpan[] = [];
  const walk = (node: EditableLogicNode): void => {
    for (const match of leafTextMatches(recommendationText, node)) {
      spans.push({ start: match.start, end: match.end, kind: "confirmed" });
    }
    for (const child of node.children ?? []) walk(child);
  };
  walk(tree);
  return spans;
}
