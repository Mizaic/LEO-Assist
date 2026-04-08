"use client";

/**
 * A 2×2 grid of mini bar charts showing 2018 NCDA benchmarks broken down by
 * the four most common cancer types (Breast / Colorectal / Lung / Prostate).
 *
 * Each panel shows three bars: This Practice (2018), Cancer Alliance (2018), All Patients (2018).
 * This mirrors the "by cancer type" panels in the NCDA practice report (e.g. wb_image7).
 */

import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LabelList,
} from "recharts";
import { resolveBenchmarkValueByCancer, BENCHMARK_COLOURS, BENCHMARK_LABELS_2018 } from "./BenchmarkLegend";

const CANCER_TYPES = [
  { key: "breast",     label: "Breast cancer" },
  { key: "colorectal", label: "Colorectal cancer" },
  { key: "lung",       label: "Lung cancer" },
  { key: "prostate",   label: "Prostate cancer" },
] as const;

type CancerTypeKey = (typeof CANCER_TYPES)[number]["key"];

interface MetricSpec {
  /** Key within the by_cancer_type block, e.g. "early_stage_pct" */
  metricKey: string;
  /** Chart x-axis label, e.g. "Early stage" */
  label: string;
}

interface CancerTypeBenchmarkGridProps {
  bm: Record<string, { practice?: number | null; alliance?: number | null; national?: number | null }> | null | undefined;
  /** JSON section name, e.g. "cancer_stage" */
  section: string;
  /** One entry per bar category to render within each cancer-type panel */
  metrics: MetricSpec[];
  /** When true, Woodbrook values are shown as the "practice" bar */
  orgSelected?: boolean;
  /** y-axis domain max, defaults to 100 */
  yMax?: number;
  /** Unit string appended in tooltip / labels */
  unit?: string;
  /** Descriptive heading shown above the grid */
  heading?: string;
  /**
   * Optional live values for the first series, keyed by cancer type then metric key.
   * Example: liveByCancerType["breast"]["early_stage_pct"] = 61.7
   */
  liveByCancerType?: Record<string, Record<string, number | null>>;
  /** Optional override for the first legend label. */
  primarySeriesLabel?: string;
}

// Colour for the first bar (woodbrook) is blue when live/today data is shown,
// brown only when falling back to 2018 benchmark values.
function woodbrookColour(hasLiveData: boolean): string {
  return hasLiveData ? BENCHMARK_COLOURS.practice : BENCHMARK_COLOURS.national;
}

function MiniBarChart({
  data,
  yMax = 100,
  unit = "%",
  firstBarColour,
  firstBarLabel,
}: {
  data: Array<{ name: string; woodbrook: number | null; east_midlands: number | null; england: number | null }>;
  yMax?: number;
  unit?: string;
  firstBarColour: string;
  firstBarLabel: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 16, right: 8, left: -20, bottom: 0 }} barCategoryGap="30%">
        <XAxis dataKey="name" tick={{ fontSize: 10 }} />
        <YAxis domain={[0, yMax]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}${unit}`} />
        <Tooltip
          formatter={(v: number | string | undefined, name: string | undefined) => [`${v ?? ""}${unit}`, name ?? ""]}
          contentStyle={{ fontSize: 11 }}
        />
        <Bar dataKey="woodbrook"     name={firstBarLabel}               fill={firstBarColour}               radius={[2, 2, 0, 0]}>
          <LabelList dataKey="woodbrook"     position="top" style={{ fontSize: 9 }} formatter={(v: unknown) => v != null ? `${v}` : ""} />
        </Bar>
        <Bar dataKey="east_midlands" name={BENCHMARK_LABELS_2018.alliance} fill={BENCHMARK_COLOURS.similar}  radius={[2, 2, 0, 0]}>
          <LabelList dataKey="east_midlands" position="top" style={{ fontSize: 9 }} formatter={(v: unknown) => v != null ? `${v}` : ""} />
        </Bar>
        <Bar dataKey="england"       name={BENCHMARK_LABELS_2018.national} fill={BENCHMARK_COLOURS.alliance} radius={[2, 2, 0, 0]}>
          <LabelList dataKey="england"       position="top" style={{ fontSize: 9 }} formatter={(v: unknown) => v != null ? `${v}` : ""} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function LegendWithLabels({
  practiceLabel,
  allianceLabel,
  nationalLabel,
  practiceColour,
}: {
  practiceLabel: string;
  allianceLabel: string;
  nationalLabel: string;
  practiceColour: string;
}) {
  const entries = [
    { colour: practiceColour,              label: practiceLabel },
    { colour: BENCHMARK_COLOURS.similar,   label: allianceLabel },
    { colour: BENCHMARK_COLOURS.alliance,  label: nationalLabel },
  ];
  return (
    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 1 }}>
      {entries.map(({ colour, label }) => (
        <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: colour, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ fontSize: "0.72rem", color: "text.secondary" }}>
            {label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

export default function CancerTypeBenchmarkGrid({
  bm,
  section,
  metrics,
  orgSelected = false,
  yMax = 100,
  unit = "%",
  heading = "2018 Baseline by Cancer Type",
  liveByCancerType,
  primarySeriesLabel,
}: CancerTypeBenchmarkGridProps) {
  if (!bm && !liveByCancerType) return null;

  const hasLiveData = liveByCancerType != null && Object.keys(liveByCancerType).length > 0;
  const firstBarColour = woodbrookColour(hasLiveData);
  const practiceLegendLabel = primarySeriesLabel ?? BENCHMARK_LABELS_2018.practice;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600, color: "text.secondary", fontSize: "0.8rem" }}>
        {heading}
      </Typography>
      <LegendWithLabels
        practiceLabel={practiceLegendLabel}
        allianceLabel={BENCHMARK_LABELS_2018.alliance}
        nationalLabel={BENCHMARK_LABELS_2018.national}
        practiceColour={firstBarColour}
      />
      <Grid container spacing={2}>
        {CANCER_TYPES.map(({ key, label }) => {
          const chartData = metrics.map((m) => {
            const wb =
              liveByCancerType?.[key]?.[m.metricKey] ??
              resolveBenchmarkValueByCancer(bm, section, m.metricKey, key, orgSelected);
            const em = bm[`${section}.by_cancer_type.${key}.${m.metricKey}`]?.alliance ?? null;
            const en = bm[`${section}.by_cancer_type.${key}.${m.metricKey}`]?.national ?? null;
            return {
              name: m.label,
              woodbrook:     wb,
              east_midlands: em,
              england:       en,
            };
          });

          const hasData = chartData.some(
            (d) => d.woodbrook != null || d.east_midlands != null || d.england != null,
          );

          return (
            <Grid key={key} size={{ xs: 12, sm: 6 }}>
              <Box
                sx={{
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                  p: 1.5,
                  bgcolor: "background.paper",
                }}
              >
                <Typography variant="caption" sx={{ fontWeight: 600, color: "text.primary", fontSize: "0.78rem" }}>
                  {label}
                </Typography>
                {hasData ? (
                  <MiniBarChart
                    data={chartData}
                    yMax={yMax}
                    unit={unit}
                    firstBarColour={firstBarColour}
                    firstBarLabel={practiceLegendLabel}
                  />
                ) : (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    No benchmark data
                  </Typography>
                )}
              </Box>
            </Grid>
          );
        })}
      </Grid>
    </Box>
  );
}
