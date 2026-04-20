/**
 * Compare two user-visible strings with numeric-aware ordering (e.g. "Item 7" before "Item 30").
 * Uses Unicode Collation Algorithm numeric mode where available.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
export function compareStringsNatural(a: string, b: string): number {
  return a.localeCompare(b, "en", { numeric: true, sensitivity: "base" });
}
