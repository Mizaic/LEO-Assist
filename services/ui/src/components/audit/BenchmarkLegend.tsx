"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

export const BENCHMARK_COLOURS = {
  practice: "#1D4ED8",
  similar: "#0D7C6F",
  alliance: "#7C3AED",
  national: "#92400E",
} as const;

/** Labels shown in the legend and chart tooltips. Vary by whether an org is selected. */
export function getBenchmarkLabels(orgSelected: boolean): Record<keyof typeof BENCHMARK_COLOURS, string> {
  return {
    practice: orgSelected ? "This Practice" : "England (today)",
    similar: "Alliance (today)",
    alliance: orgSelected ? "England (today)" : "England (today)",
    // When an org is selected the 4th column is the practice's own 2018 baseline;
    // when no org is selected it is the England 2018 national baseline.
    national: orgSelected ? "This Practice (2018)" : "England (2018)",
  };
}

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
