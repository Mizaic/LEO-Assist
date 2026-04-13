/**
 * Compare two user-visible strings with numeric-aware ordering (e.g. "Item 7" before "Item 30").
 * Uses Unicode Collation Algorithm numeric mode where available.
 */
export function compareStringsNatural(a: string, b: string): number {
  return a.localeCompare(b, "en", { numeric: true, sensitivity: "base" });
}
