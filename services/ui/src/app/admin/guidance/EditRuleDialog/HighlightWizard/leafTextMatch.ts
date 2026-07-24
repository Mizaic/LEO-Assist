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
  findBestTextMatch,
  findBestTextMatchForCriterion,
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
  const value = node.value != null ? String(node.value) : "";
  if (!value) return null;
  if (node.field === "sex") {
    const sex = value.toLowerCase();
    if (sex === "m" || sex === "male") return "male";
    if (sex === "f" || sex === "female") return "female";
    return value;
  }
  if (node.operator === "between" && node.value2 != null) {
    return `${value} to ${node.value2}`;
  }
  const suffix: Record<string, string> = {
    ">=": "or over",
    "<=": "or under",
    ">": "or more",
    "<": "or less",
    "=": "",
  };
  return `aged ${value} ${suffix[node.operator ?? ">="] ?? ""}`.trim();
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
  if (node.source_row_text) {
    const bySource = findBestTextMatch(recommendationText, node.source_row_text);
    if (bySource) return bySource;
  }
  if (node.kind === "CONCEPT") {
    return findBestTextMatchForCriterion(recommendationText, node.criterion);
  }
  if (node.kind === "DEMOGRAPHIC") {
    return findBestTextMatch(recommendationText, demographicMatchCandidate(node));
  }
  if (node.kind === "OBSERVATION") {
    return findBestTextMatch(recommendationText, node.observation?.observable_term);
  }
  return null;
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
    const match = leafTextMatch(recommendationText, node);
    if (match) spans.push({ start: match.start, end: match.end, kind: "confirmed" });
    for (const child of node.children ?? []) walk(child);
  };
  walk(tree);
  return spans;
}
