/**
 * Keys for grouped audit bar charts (live practice + benchmark + optional comparators).
 * See BenchmarkLegend for key meanings.
 */
export type AuditBarVisibleKey = "practice" | "national" | "similar" | "alliance";

/**
 * When a practice is selected, default is practice + historical benchmark only.
 * Optional live comparators: Cancer Alliance (similar) and all patients in England (alliance).
 * When no practice is selected, charts keep practice + national benchmark columns only.
 */
export function buildAuditBarVisibleKeys(
  orgSelected: boolean,
  showCancerAlliance: boolean,
  showAllPatients: boolean,
): readonly AuditBarVisibleKey[] {
  if (!orgSelected) {
    return ["practice", "national"];
  }
  const keys: AuditBarVisibleKey[] = ["practice", "national"];
  if (showCancerAlliance) keys.push("similar");
  if (showAllPatients) keys.push("alliance");
  return keys;
}
