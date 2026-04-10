/** UK tax-year fiscal presets (6 April to 5 April) for analytics date filters. */
export const TAX_YEAR_PRESETS = [
  { label: "2023/24", from: "2023-04-06", to: "2024-04-05" },
  { label: "2024/25", from: "2024-04-06", to: "2025-04-05" },
  { label: "2025/26", from: "2025-04-06", to: "2026-04-05" },
] as const;

export type TaxYearPreset = (typeof TAX_YEAR_PRESETS)[number];
