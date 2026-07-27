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

/** Merge two adjacent boundaries into one; a mixed structure+heuristic
 *  pair degrades to "heuristic" -- the merged text no longer reads as
 *  a single clean `<li>` the guideline's own markup vouched for. */
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
