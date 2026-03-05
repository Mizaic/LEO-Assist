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
    national: "NCDA 2018 Baseline",
  };
}

/** Default (backward-compat) static labels. */
export const BENCHMARK_LABELS = getBenchmarkLabels(true);

interface BenchmarkLegendProps {
  visibleKeys?: Array<keyof typeof BENCHMARK_COLOURS>;
  /** When true, shows practice-centric labels; when false shows England-centric labels. */
  orgSelected?: boolean;
  /** Override specific label text. */
  labelOverrides?: Partial<Record<keyof typeof BENCHMARK_COLOURS, string>>;
}

export default function BenchmarkLegend({
  visibleKeys = ["practice", "similar", "alliance", "national"],
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
