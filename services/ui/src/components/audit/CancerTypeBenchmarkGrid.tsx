/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

/**
 * A 2x2 grid of mini bar charts showing stage/metric breakdowns by cancer type.
 *
 * Each panel shows up to four bars:
 *   1. This Practice (today)   -- live data from liveByCancerType (blue)
 *   2. This Practice (2018)    -- NCDA benchmark, practice slot (brown)
 *   3. Cancer Alliance (2018)  -- NCDA benchmark, alliance slot (teal)
 *   4. All Patients (2018)     -- NCDA benchmark, national slot (purple)
 *
 * Bars 1 and 2 are only shown when orgSelected = true (a practice is chosen).
 * The "today" bar (1) never falls back to 2018 data -- if live data is absent
 * for a given cancer type it renders as an empty slot, not as a 2018 value.
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
import { BENCHMARK_COLOURS, BENCHMARK_LABELS_2018 } from "./BenchmarkLegend";

const CANCER_TYPES = [
  { key: "breast",     label: "Breast cancer" },
  { key: "colorectal", label: "Colorectal cancer" },
  { key: "lung",       label: "Lung cancer" },
  { key: "prostate",   label: "Prostate cancer" },
] as const;

interface MetricSpec {
  metricKey: string;
  label: string;
}

interface CancerTypeBenchmarkGridProps {
  bm: Record<string, { practice?: number | null; alliance?: number | null; national?: number | null }> | null | undefined;
  section: string;
  metrics: MetricSpec[];
  orgSelected?: boolean;
  yMax?: number;
  unit?: string;
  heading?: string;
  liveByCancerType?: Record<string, Record<string, number | null>>;
  /** @deprecated -- label is now derived from orgSelected; prop kept for back-compat */
  primarySeriesLabel?: string;
  /**
   * When org is selected: show Cancer Alliance (2018) benchmark bar. Defaults true if omitted (legacy).
   */
  showAlliance2018?: boolean;
  /**
   * When org is selected: show all patients / England (2018) benchmark bar. Defaults true if omitted (legacy).
   */
  showNational2018?: boolean;
}

// -- Chart data type -------------------------------------------------------

interface BarRow {
  name: string;
  today: number | null;
  practice2018: number | null;
  alliance2018: number | null;
  national2018: number | null;
}

// -- Legend ----------------------------------------------------------------

const SERIES = [
  { key: "today",        colour: BENCHMARK_COLOURS.practice, label: "This Practice (today)" },
  { key: "practice2018", colour: BENCHMARK_COLOURS.national, label: BENCHMARK_LABELS_2018.practice },
  { key: "alliance2018", colour: BENCHMARK_COLOURS.similar,  label: BENCHMARK_LABELS_2018.alliance },
  { key: "national2018", colour: BENCHMARK_COLOURS.alliance, label: BENCHMARK_LABELS_2018.national },
] as const;

function Legend({
  orgSelected,
  showAlliance2018,
  showNational2018,
}: {
  orgSelected: boolean;
  showAlliance2018: boolean;
  showNational2018: boolean;
}) {
  const visible = orgSelected
    ? SERIES.filter((s) => {
        if (s.key === "alliance2018") return showAlliance2018;
        if (s.key === "national2018") return showNational2018;
        return true;
      })
    : SERIES.slice(2);
  return (
    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 1 }}>
      {visible.map(({ key, colour, label }) => (
        <Box key={key} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: colour, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ fontSize: "0.72rem", color: "text.secondary" }}>
            {label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

// -- Mini bar chart --------------------------------------------------------

function MiniBarChart({
  data,
  yMax = 100,
  unit = "%",
  orgSelected,
  showAlliance2018,
  showNational2018,
}: {
  data: BarRow[];
  yMax?: number;
  unit?: string;
  orgSelected: boolean;
  showAlliance2018: boolean;
  showNational2018: boolean;
}) {
  const fmt = (v: unknown) => (v != null ? `${v}` : "");
  // Recharts Tooltip Formatter signature widened in v3: value/name are
  // typed `ValueType`/`NameType` (which include arrays). Cast to the
  // expected scalar shape since our data series only emit numbers/strings.
  const tipFmt = (v: unknown, name: unknown) =>
    [`${(v as string | number | undefined) ?? ""}${unit}`, `${name ?? ""}`] as [
      string,
      string,
    ];

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 16, right: 8, left: -20, bottom: 0 }} barCategoryGap="25%">
        <XAxis dataKey="name" tick={{ fontSize: 10 }} />
        <YAxis domain={[0, yMax]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}${unit}`} />
        <Tooltip formatter={tipFmt} contentStyle={{ fontSize: 11 }} />
        {orgSelected && (
          <Bar dataKey="today" name="This Practice (today)" fill={BENCHMARK_COLOURS.practice} radius={[2, 2, 0, 0]}>
            <LabelList dataKey="today" position="top" style={{ fontSize: 9 }} formatter={fmt} />
          </Bar>
        )}
        {orgSelected && (
          <Bar dataKey="practice2018" name={BENCHMARK_LABELS_2018.practice} fill={BENCHMARK_COLOURS.national} radius={[2, 2, 0, 0]}>
            <LabelList dataKey="practice2018" position="top" style={{ fontSize: 9 }} formatter={fmt} />
          </Bar>
        )}
        {(!orgSelected || showAlliance2018) && (
          <Bar dataKey="alliance2018" name={BENCHMARK_LABELS_2018.alliance} fill={BENCHMARK_COLOURS.similar} radius={[2, 2, 0, 0]}>
            <LabelList dataKey="alliance2018" position="top" style={{ fontSize: 9 }} formatter={fmt} />
          </Bar>
        )}
        {(!orgSelected || showNational2018) && (
          <Bar dataKey="national2018" name={BENCHMARK_LABELS_2018.national} fill={BENCHMARK_COLOURS.alliance} radius={[2, 2, 0, 0]}>
            <LabelList dataKey="national2018" position="top" style={{ fontSize: 9 }} formatter={fmt} />
          </Bar>
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}

// -- Main export -----------------------------------------------------------

export default function CancerTypeBenchmarkGrid({
  bm,
  section,
  metrics,
  orgSelected = false,
  yMax = 100,
  unit = "%",
  heading = "Stage at Diagnosis by Cancer Type",
  liveByCancerType,
  showAlliance2018,
  showNational2018,
}: CancerTypeBenchmarkGridProps) {
  if (!bm && !liveByCancerType) return null;

  const alliance2018On = showAlliance2018 ?? true;
  const national2018On = showNational2018 ?? true;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600, color: "text.secondary", fontSize: "0.8rem" }}>
        {heading}
      </Typography>
      <Legend
        orgSelected={orgSelected}
        showAlliance2018={alliance2018On}
        showNational2018={national2018On}
      />
      <Grid container spacing={2}>
        {CANCER_TYPES.map(({ key, label }) => {
          const chartData: BarRow[] = metrics.map((m) => {
            const bmEntry = bm?.[`${section}.by_cancer_type.${key}.${m.metricKey}`] ?? null;
            return {
              name:         m.label,
              // Live today data -- null if not present; never falls back to 2018.
              today:        liveByCancerType?.[key]?.[m.metricKey] ?? null,
              // Three separate 2018 benchmark series from distinct fields.
              practice2018: bmEntry?.practice ?? null,
              alliance2018: bmEntry?.alliance ?? null,
              national2018: bmEntry?.national ?? null,
            };
          });

          const hasData = chartData.some(
            (d) => d.today != null || d.practice2018 != null || d.alliance2018 != null || d.national2018 != null,
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
                    orgSelected={orgSelected}
                    showAlliance2018={alliance2018On}
                    showNational2018={national2018On}
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
