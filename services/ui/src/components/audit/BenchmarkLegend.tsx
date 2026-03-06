"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export const BENCHMARK_COLOURS = {
  practice: "#1D4ED8",
  similar: "#0D7C6F",
  alliance: "#7C3AED",
  national: "#92400E",
} as const;

/**
 * Labels shown in legends, chart tooltips, and table headers.
 *
 * Key semantics:
 *   practice  — live data for the selected practice (or all patients when no org is selected)
 *   similar   — Cancer Alliance live aggregated data
 *   alliance  — All Patients live (England-wide)
 *   national  — 2018 NCDA baseline (practice-level when org selected, national otherwise)
 */
export function getBenchmarkLabels(orgSelected: boolean): Record<keyof typeof BENCHMARK_COLOURS, string> {
  return {
    practice: orgSelected ? "This Practice" : "All Patients (today)",
    similar:  "Cancer Alliance (today)",
    alliance: "All Patients (today)",
    national: orgSelected ? "This Practice (2018)" : "All Patients (2018)",
  };
}

/** Convenience labels for 2018 benchmark-only contexts (e.g. per-cancer-type grids). */
export const BENCHMARK_LABELS_2018 = {
  practice:     "This Practice (2018)",
  alliance:     "Cancer Alliance (2018)",
  national:     "All Patients (2018)",
} as const;

/** Default (backward-compat) static labels. */
export const BENCHMARK_LABELS = getBenchmarkLabels(true);

/**
 * Resolve the benchmark value that should be shown in the "national" chart slot.
 *
 * When an org is selected the most relevant 2018 comparator is the practice's
 * own baseline. Falls back to the national benchmark when no practice-level
 * value exists, and to null when neither is available.
 *
 * When no org is selected (England view) only the national benchmark is shown.
 */
export function resolveBenchmarkValue(
  bm: Record<string, { practice?: number | null; alliance?: number | null; national?: number | null }> | null | undefined,
  metricKey: string,
  orgSelected: boolean,
): number | null {
  if (!bm) return null;
  const entry = bm[metricKey];
  if (!entry) return null;
  if (orgSelected) {
    return entry.practice ?? entry.national ?? null;
  }
  return entry.national ?? null;
}

/**
 * Resolve a benchmark value for a specific cancer type from the by_cancer_type
 * sub-structure. Falls back to the overall metric if no cancer-type value exists.
 *
 * The JSON structure is:
 *   bm["<section>.by_cancer_type.<cancerType>.<metricKey>"] = { practice, national, ... }
 */
export function resolveBenchmarkValueByCancer(
  bm: Record<string, { practice?: number | null; alliance?: number | null; national?: number | null }> | null | undefined,
  section: string,
  metricKey: string,
  cancerType: string,
  orgSelected: boolean,
): number | null {
  if (!bm) return null;
  const specificKey = `${section}.by_cancer_type.${cancerType}.${metricKey}`;
  const fallbackKey = `${section}.${metricKey}`;
  const entry = bm[specificKey] ?? bm[fallbackKey];
  if (!entry) return null;
  if (orgSelected) {
    return entry.practice ?? entry.national ?? null;
  }
  return entry.national ?? null;
}

interface BenchmarkLegendProps {
  visibleKeys?: Array<keyof typeof BENCHMARK_COLOURS>;
  /** When true, shows practice-centric labels; when false shows England-centric labels. */
  orgSelected?: boolean;
  /** Override specific label text. */
  labelOverrides?: Partial<Record<keyof typeof BENCHMARK_COLOURS, string>>;
}

export default function BenchmarkLegend({
  visibleKeys = ["practice", "national", "similar", "alliance"],
  orgSelected = true,
  labelOverrides,
}: BenchmarkLegendProps) {
  const labels = { ...getBenchmarkLabels(orgSelected), ...labelOverrides };

  return (
    <Box
      role="list"
      aria-label="Comparison levels legend"
      sx={{ display: "flex", flexWrap: "wrap", gap: 2, mb: 1 }}
    >
      {visibleKeys.map((key) => (
        <Box
          key={key}
          role="listitem"
          sx={{ display: "flex", alignItems: "center", gap: 0.75 }}
        >
          <Box
            aria-hidden="true"
            sx={{
              width: 12,
              height: 12,
              borderRadius: "2px",
              bgcolor: BENCHMARK_COLOURS[key],
              flexShrink: 0,
            }}
          />
          <Typography variant="caption" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
            {labels[key]}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
