/** UK tax-year fiscal presets (6 April to 5 April) for analytics date filters.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
export const TAX_YEAR_PRESETS = [
  { label: "2023/24", from: "2023-04-06", to: "2024-04-05" },
  { label: "2024/25", from: "2024-04-06", to: "2025-04-05" },
  { label: "2025/26", from: "2025-04-06", to: "2026-04-05" },
] as const;

export type TaxYearPreset = (typeof TAX_YEAR_PRESETS)[number];
