/**
 * Keys for grouped audit bar charts (live practice + benchmark + optional comparators).
 * See BenchmarkLegend for key meanings.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
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
