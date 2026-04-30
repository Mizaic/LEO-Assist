/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
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
import IconButton from "@mui/material/IconButton";
import MuiTooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import { BENCHMARK_COLOURS } from "./BenchmarkLegend";

export interface PatientInterval {
  episode_id: string;
  cancer_type?: string | null;
  pci_days?: number | null;
  di_days?: number | null;
  diag_is_inferred?: boolean | null;
  is_benign?: boolean | null;
}

interface IntervalStripPlotProps {
  patients: PatientInterval[];
  intervalKey: "pci_days" | "di_days";
  label: string;
  median?: number | null;
  q1?: number | null;
  q3?: number | null;
  /** Median for confirmed-cancer episodes only. */
  cancerMedian?: number | null;
  /** Median for benign/excluded episodes only. */
  benignMedian?: number | null;
  /** When true, benign/excluded episodes are rendered in the chart. */
  showBenign?: boolean;
  nationalMedian?: number | null;
  /** Label for the national/baseline reference line. Defaults to "2018 baseline". */
  nationalLabel?: string;
  allianceMedian?: number | null;
  unit?: string;
  maxDays?: number;
  noDataMessage?: string;
  /** Height of the recharts ResponsiveContainer in px.  Defaults to 160. */
  chartHeight?: number;
  /** When provided, renders a small expand button beside the stats chips. */
  onZoom?: () => void;
}

const CANCER_DOT_COLOUR = "#DC2626";  // red-600
const BENIGN_DOT_COLOUR = "#16A34A";  // green-600

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
  cancerMedian,
  benignMedian,
  showBenign = true,
  nationalMedian,
  nationalLabel = "2018 baseline",
  allianceMedian,
  unit = "days",
  maxDays = 365,
  noDataMessage,
  chartHeight = 160,
  onZoom,
}: IntervalStripPlotProps) {
  const filtered = patients.filter(
    (p) =>
      p[intervalKey] != null &&
      (p[intervalKey] as number) >= 0 &&
      (p[intervalKey] as number) <= maxDays &&
      (showBenign || !p.is_benign)
  );
  const allPoints = filtered.map((p, i) => ({
    x: p[intervalKey] as number,
    y: jitter(i, filtered.length),
    cancer_type: p.cancer_type ?? "Unknown",
    episode_id: p.episode_id,
    inferred: !!p.diag_is_inferred,
    is_benign: !!p.is_benign,
  }));
  const cancerPoints = allPoints.filter((p) => !p.is_benign);
  const benignPoints = allPoints.filter((p) => p.is_benign);

  type ScatterPointPayload = (typeof allPoints)[0];
  const noData = allPoints.length === 0;

  const effectiveCancerMedian = cancerMedian ?? (cancerPoints.length > 0 ? median : null);
  const effectiveBenignMedian = showBenign ? benignMedian : null;

  const tooltipContent = ({
    payload,
  }: {
    payload?: ReadonlyArray<{ payload?: ScatterPointPayload }>;
  }) => {
    if (!payload?.length) return null;
    const d = payload[0]?.payload;
    const isBenign = d?.is_benign;
    return (
      <Box sx={{ bgcolor: "white", p: 1, border: "1px solid #E5E7EB", borderRadius: 1, fontSize: "0.78rem" }}>
        <div><strong>{d?.cancer_type}</strong></div>
        <div>{label}: {d?.x} {unit}</div>
        {isBenign && (
          <div style={{ color: BENIGN_DOT_COLOUR, fontStyle: "italic", marginTop: 2 }}>
            Benign / excluded outcome
          </div>
        )}
        {!isBenign && d?.inferred && (
          <div style={{ color: "#B45309", fontStyle: "italic", marginTop: 2 }}>
            ~ Inferred outcome — not a coded diagnosis
          </div>
        )}
      </Box>
    );
  };

  return (
    <Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5, mb: 1.5, alignItems: "center", justifyContent: "space-between" }}>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5, alignItems: "center" }}>
          {effectiveCancerMedian != null && (
            <Chip
              label={`Cancer median: ${effectiveCancerMedian} ${unit}`}
              size="small"
              sx={{ bgcolor: CANCER_DOT_COLOUR, color: "white", fontWeight: 700 }}
            />
          )}
          {showBenign && effectiveBenignMedian != null && (
            <Chip
              label={`Benign/excluded median: ${effectiveBenignMedian} ${unit}`}
              size="small"
              sx={{ bgcolor: BENIGN_DOT_COLOUR, color: "white", fontWeight: 700 }}
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
        {onZoom && (
          <MuiTooltip title="Expand chart" placement="top">
            <IconButton
              aria-label={`Expand ${label} strip plot`}
              size="small"
              onClick={onZoom}
              sx={{ p: 0.5, color: "text.secondary", flexShrink: 0, "&:hover": { color: "primary.main" } }}
            >
              <OpenInFullIcon sx={{ fontSize: "1rem" }} />
            </IconButton>
          </MuiTooltip>
        )}
      </Box>

      {noData ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
          {noDataMessage ?? `No ${label.toLowerCase()} data available for the selected period.`}
        </Typography>
      ) : (
        <Box
          role="img"
          aria-label={`Strip plot: ${label}. ${allPoints.length} patients shown. Cancer median: ${effectiveCancerMedian ?? "unknown"} ${unit}.`}
        >
          <ResponsiveContainer width="99%" height={chartHeight}>
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
              {effectiveCancerMedian != null && (
                <ReferenceLine x={effectiveCancerMedian} stroke={CANCER_DOT_COLOUR} strokeWidth={2} strokeDasharray="6 3"
                  label={{ value: "Cancer median", fill: CANCER_DOT_COLOUR, fontSize: 10, position: "top" }} />
              )}
              {showBenign && effectiveBenignMedian != null && (
                <ReferenceLine x={effectiveBenignMedian} stroke={BENIGN_DOT_COLOUR} strokeWidth={2} strokeDasharray="6 3"
                  label={{ value: "Benign median", fill: BENIGN_DOT_COLOUR, fontSize: 10, position: "insideTopRight" }} />
              )}
              {nationalMedian != null && (
                <ReferenceLine x={nationalMedian} stroke={BENCHMARK_COLOURS.national} strokeWidth={1.5} strokeDasharray="4 2"
                  label={{ value: nationalLabel, fill: BENCHMARK_COLOURS.national, fontSize: 10, position: "insideTopRight" }} />
              )}
              {allianceMedian != null && (
                <ReferenceLine x={allianceMedian} stroke={BENCHMARK_COLOURS.similar} strokeWidth={1.5} strokeDasharray="4 2"
                  label={{ value: "Cancer Alliance", fill: BENCHMARK_COLOURS.similar, fontSize: 10, position: "insideTopLeft" }} />
              )}
              <Scatter data={cancerPoints} fill={CANCER_DOT_COLOUR} fillOpacity={0.65} r={4} name="Cancer" />
              {showBenign && <Scatter data={benignPoints} fill={BENIGN_DOT_COLOUR} fillOpacity={0.65} r={4} name="Benign/excluded" />}
            </ScatterChart>
          </ResponsiveContainer>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "center", mt: 0.5 }}>
            Each dot represents one referral. Red = cancer confirmed, green = benign/excluded. Dots further right = longer {label.toLowerCase()}.
            {allPoints.length < patients.filter((p) => p[intervalKey] != null && (showBenign || !p.is_benign)).length && (
              ` (Referrals beyond ${maxDays} days not shown.)`
            )}
          </Typography>
        </Box>
      )}
    </Box>
  );
}
