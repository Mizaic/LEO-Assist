"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import { BENCHMARK_COLOURS } from "./BenchmarkLegend";

export interface PatientInterval {
  episode_id: string;
  cancer_type?: string | null;
  pci_days?: number | null;
  di_days?: number | null;
  diag_is_inferred?: boolean | null;
}

interface IntervalStripPlotProps {
  patients: PatientInterval[];
  intervalKey: "pci_days" | "di_days";
  label: string;
  median?: number | null;
  q1?: number | null;
  q3?: number | null;
  nationalMedian?: number | null;
  /** Label for the national/baseline reference line. Defaults to "2018 baseline". */
  nationalLabel?: string;
  allianceMedian?: number | null;
  unit?: string;
  maxDays?: number;
}

function jitter(index: number, total: number): number {
  return 0.5 + (index / Math.max(total - 1, 1)) * 0.9;
}

export default function IntervalStripPlot({
  patients,
  intervalKey,
  label,
  median,
  q1,
  q3,
  nationalMedian,
  nationalLabel = "2018 baseline",
  allianceMedian,
  unit = "days",
  maxDays = 365,
}: IntervalStripPlotProps) {
  const filtered = patients.filter(
    (p) => p[intervalKey] != null && (p[intervalKey] as number) <= maxDays
  );
  const points = filtered.map((p, i) => ({
    x: p[intervalKey] as number,
    y: jitter(i, filtered.length),
    cancer_type: p.cancer_type ?? "Unknown",
    episode_id: p.episode_id,
    inferred: !!p.diag_is_inferred,
  }));
  const confirmedPoints = points.filter((p) => !p.inferred);
  const inferredPoints = points.filter((p) => p.inferred);
  const inferredCount = inferredPoints.length;

  type ScatterPointPayload = (typeof points)[0];
  const noData = points.length === 0;
  const tooltipContent = ({
    payload,
  }: {
    payload?: ReadonlyArray<{ payload?: ScatterPointPayload }>;
  }) => {
    if (!payload?.length) return null;
    const d = payload[0]?.payload;
    return (
      <Box sx={{ bgcolor: "white", p: 1, border: "1px solid #E5E7EB", borderRadius: 1, fontSize: "0.78rem" }}>
        <div><strong>{d?.cancer_type}</strong></div>
        <div>{label}: {d?.x} {unit}</div>
        {d?.inferred && (
          <div style={{ color: "#B45309", fontStyle: "italic", marginTop: 2 }}>
            ~ Inferred outcome - not a coded diagnosis
          </div>
        )}
      </Box>
    );
  };

  return (
    <Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5, mb: 1.5, alignItems: "center" }}>
        {median != null && (
          <Chip
            label={`Median: ${median} ${unit}`}
            size="small"
            sx={{ bgcolor: BENCHMARK_COLOURS.practice, color: "white", fontWeight: 700 }}
          />
        )}
        {q1 != null && q3 != null && (
          <Chip
            label={`IQR: ${q1}–${q3} ${unit}`}
            size="small"
            variant="outlined"
          />
        )}
        {nationalMedian != null && (
          <Chip
            label={`${nationalLabel}: ${nationalMedian} ${unit}`}
            size="small"
            sx={{ bgcolor: BENCHMARK_COLOURS.national, color: "white" }}
          />
        )}
        {allianceMedian != null && (
          <Chip
            label={`Cancer Alliance median: ${allianceMedian} ${unit}`}
            size="small"
            sx={{ bgcolor: BENCHMARK_COLOURS.similar, color: "white" }}
          />
        )}
      </Box>

      {noData ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
          No {label.toLowerCase()} data available for the selected period.
        </Typography>
      ) : (
        <Box
          role="img"
          aria-label={`Strip plot: ${label}. ${points.length} patients shown. Median: ${median ?? "unknown"} ${unit}.`}
        >
          <ResponsiveContainer width="99%" height={160}>
            <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
              <XAxis
                type="number"
                dataKey="x"
                name={label}
                unit={` ${unit}`}
                label={{ value: `${label} (${unit})`, position: "insideBottom", offset: -10, fontSize: 11, fill: "#6B7280" }}
                tick={{ fontSize: 10, fill: "#374151" }}
                domain={[0, maxDays]}
              />
              <YAxis type="number" dataKey="y" hide domain={[0, 1.4]} />
              <Tooltip cursor={false} content={tooltipContent} />
              {median != null && (
                <ReferenceLine x={median} stroke={BENCHMARK_COLOURS.practice} strokeWidth={2} strokeDasharray="6 3" label={{ value: "Median", fill: BENCHMARK_COLOURS.practice, fontSize: 10, position: "top" }} />
              )}
              {nationalMedian != null && (
                <ReferenceLine x={nationalMedian} stroke={BENCHMARK_COLOURS.national} strokeWidth={1.5} strokeDasharray="4 2" label={{ value: nationalLabel, fill: BENCHMARK_COLOURS.national, fontSize: 10, position: "insideTopRight" }} />
              )}
              {allianceMedian != null && (
                <ReferenceLine x={allianceMedian} stroke={BENCHMARK_COLOURS.similar} strokeWidth={1.5} strokeDasharray="4 2" label={{ value: "Cancer Alliance", fill: BENCHMARK_COLOURS.similar, fontSize: 10, position: "insideTopLeft" }} />
              )}
              <Scatter data={confirmedPoints} fill={BENCHMARK_COLOURS.practice} fillOpacity={0.55} r={4} name="Confirmed" />
              <Scatter data={inferredPoints} fill="#D97706" fillOpacity={0.75} r={4} name="Inferred" />
            </ScatterChart>
          </ResponsiveContainer>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "center", mt: 0.5 }}>
            Each dot represents one patient. Dots further right = longer {label.toLowerCase()}.
            {inferredCount > 0 && (
              <Box component="span" sx={{ color: "#B45309" }}>
                {" "}Amber dots ({inferredCount}) show inferred outcomes — not coded diagnoses. Hover for detail.
              </Box>
            )}
            {points.length < patients.filter((p) => p[intervalKey] != null).length && (
              ` (Patients beyond ${maxDays} days not shown.)`
            )}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
