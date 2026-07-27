/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Compares two dotted NICE section numbers ("1.2.1", "1.11.1") the way a
 * reviewer expects to read them: numeric segment by numeric segment,
 * NOT as plain strings. Plain string/lexicographic comparison puts
 * "1.11.1" before "1.2.1" (because the character "1" sorts before "2"),
 * which is the exact bug reviewers hit in the guideline review pool.
 *
 * Splits on runs of digits so "1.2.1" -> ["1", ".", "2", ".", "1"] and
 * "1.11.1" -> ["1", ".", "11", ".", "1"]; each pair of segments is then
 * compared numerically when both sides are pure digit runs, or as plain
 * strings otherwise (so the "." separators, and any non-numeric ids
 * this is ever handed, still compare sensibly instead of throwing).
 */
export function naturalSortCompare(a: string, b: string): number {
  const segmentsOf = (value: string): string[] => value.split(/(\d+)/).filter((seg) => seg.length > 0);
  const segA = segmentsOf(a);
  const segB = segmentsOf(b);
  const length = Math.max(segA.length, segB.length);
  for (let i = 0; i < length; i++) {
    const partA = segA[i] ?? "";
    const partB = segB[i] ?? "";
    const cmp = compareSegment(partA, partB);
    if (cmp !== 0) return cmp;
  }
  return 0;
}

function compareSegment(partA: string, partB: string): number {
  const isDigitsA = /^\d+$/.test(partA);
  const isDigitsB = /^\d+$/.test(partB);
  if (isDigitsA && isDigitsB) return Number(partA) - Number(partB);
  return partA.localeCompare(partB);
}
