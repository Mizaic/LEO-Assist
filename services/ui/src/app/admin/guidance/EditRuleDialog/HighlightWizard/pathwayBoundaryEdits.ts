/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Pure boundary-editing helpers for Step 2 (StepPathwaySplit) --
 * merging two rows into one, splitting one row into two, and the
 * "Situation A, B, C..." lettering. Kept free of React so they are
 * unit-testable without mounting the step component.
 */
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export function pathwayLetter(index: number): string {
  return LETTERS[index % LETTERS.length];
}

/** Merge two adjacent boundaries into one; a mixed source pair
 *  (structure/heuristic/tree) degrades to "heuristic" -- the merged
 *  text is no longer a single clean guideline `<li>` or a pure
 *  tree-rehydrated label. */
export function mergeBoundaries(
  first: PathwayTextBoundary,
  second: PathwayTextBoundary,
): PathwayTextBoundary {
  return {
    start: Math.min(first.start, second.start),
    end: Math.max(first.end, second.end),
    text: `${first.text} ${second.text}`.trim(),
    source: first.source === second.source ? first.source : "heuristic",
  };
}

/** Split one boundary into two at a LOCAL offset (relative to the
 *  boundary's own text, as returned by a scoped selection). */
export function splitBoundaryAt(
  boundary: PathwayTextBoundary,
  localSplitPoint: number,
): [PathwayTextBoundary, PathwayTextBoundary] {
  const splitAt = boundary.start + localSplitPoint;
  return [
    {
      start: boundary.start,
      end: splitAt,
      text: boundary.text.slice(0, localSplitPoint).trim(),
      source: boundary.source,
    },
    {
      start: splitAt,
      end: boundary.end,
      text: boundary.text.slice(localSplitPoint).trim(),
      source: boundary.source,
    },
  ];
}

function resolveSelectionSpans(
  recommendationText: string,
  selectionStart: number,
  selectionEnd: number,
  cleanedText: string,
): Array<{ start: number; end: number }> {
  const slice = recommendationText.slice(selectionStart, selectionEnd);
  const words = cleanedText.split(/\s+/).filter(Boolean);
  const spans: Array<{ start: number; end: number }> = [];
  let cursor = 0;
  let i = 0;
  while (i < words.length) {
    let matchedEnd = i;
    let foundAt = -1;
    let candidateLen = 0;
    for (let j = words.length; j > i; j--) {
      const candidate = words.slice(i, j).join(" ");
      const idx = slice.indexOf(candidate, cursor);
      if (idx >= 0) {
        matchedEnd = j;
        foundAt = idx;
        candidateLen = candidate.length;
        break;
      }
    }
    if (foundAt < 0) return [{ start: selectionStart, end: selectionEnd }];
    spans.push({
      start: selectionStart + foundAt,
      end: selectionStart + foundAt + candidateLen,
    });
    cursor = foundAt + candidateLen;
    i = matchedEnd;
  }
  return spans.length > 0 ? spans : [{ start: selectionStart, end: selectionEnd }];
}

/** Build one situation boundary from a contiguous or disconnected word selection. */
export function buildManualBoundaryFromSelection(
  recommendationText: string,
  selection: { start: number; end: number; text: string },
): PathwayTextBoundary | null {
  const cleaned = selection.text.replace(/^[,;:\s]+|[,;:\s]+$/g, "");
  if (!cleaned) return null;
  const spans = resolveSelectionSpans(
    recommendationText,
    selection.start,
    selection.end,
    cleaned,
  );
  return {
    start: spans[0].start,
    end: spans[spans.length - 1].end,
    text: cleaned,
    spans,
    source: "heuristic",
  };
}
