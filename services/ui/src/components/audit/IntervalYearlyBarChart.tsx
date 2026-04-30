/**
 * Year-over-year grouped bar chart for PCI / DI medians.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
  Legend,
} from "recharts";
import type { LegendType } from "recharts/types/util/types";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

const CANCER_COLOUR = "#DC2626";
const BENIGN_COLOUR = "#16A34A";
const BASELINE_COLOUR = "#6B7280";

export interface YearBarDatum {
  year: string;
  cancerMedian: number | null;
  benignMedian: number | null;
  cancerN: number;
  benignN: number;
  /** True when this row represents the 2018 historic baseline (read-only reference). */
  isBaseline?: boolean;
}

interface Props {
  yearData: YearBarDatum[];
  intervalKey?: "pci" | "di";
  showBenign: boolean;
  selectedYear: string;
  onSelectYear: (year: string) => void;
  unit?: string;
}


type TooltipPayload = {
  name: string;
  value: number;
  fill: string;
  payload: YearBarDatum;
};

function CustomTooltip({
  active,
  payload,
  unit,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  const datum = payload[0].payload;
  return (
    <Box
      sx={{
        bgcolor: "white",
        p: 1.5,
        border: "1px solid #E5E7EB",
        borderRadius: 1,
        fontSize: "0.78rem",
        minWidth: 150,
      }}
    >
      <Typography variant="caption" fontWeight={700} display="block" mb={0.5}>
        {datum.year}
        {datum.isBaseline ? " (2018 baseline)" : ""}
      </Typography>
      {datum.cancerMedian != null && (
        <Box sx={{ color: CANCER_COLOUR }}>
          Cancer median: {datum.cancerMedian} {unit} (n={datum.cancerN})
        </Box>
      )}
      {datum.benignMedian != null && (
        <Box sx={{ color: BENIGN_COLOUR }}>
          Benign/excluded median: {datum.benignMedian} {unit} (n={datum.benignN})
        </Box>
      )}
    </Box>
  );
}

export default function IntervalYearlyBarChart({
  yearData,
  showBenign,
  selectedYear,
  onSelectYear,
  unit = "days",
}: Props) {
  const baselineDatum = yearData.find((d) => d.isBaseline);
  // Only show baseline reference line when a meaningful benchmark value exists.
  const baselineMedian =
    baselineDatum?.cancerMedian != null && baselineDatum.cancerMedian > 0
      ? baselineDatum.cancerMedian
      : null;

  // Exclude baseline from bar rendering — it goes in as a reference line only.
  const liveBars = yearData.filter((d) => !d.isBaseline);

  const maxVal = Math.max(
    ...liveBars.flatMap((d) => [d.cancerMedian ?? 0, showBenign ? (d.benignMedian ?? 0) : 0]),
    baselineMedian ?? 0,
    1,
  );
  // Add extra headroom and always at least 10 days so near-zero bars are still visible.
  const yMax = Math.max(Math.ceil((maxVal * 1.3) / 10) * 10, 10);

  return (
    <Box>
      <ResponsiveContainer width="99%" height={180}>
        <BarChart
          data={liveBars}
          barCategoryGap="35%"
          barGap={4}
          margin={{ top: 10, right: 16, left: 0, bottom: 4 }}
          onClick={(e) => {
            if (e?.activeLabel) onSelectYear(e.activeLabel as string);
          }}
        >
          <XAxis
            dataKey="year"
            tick={({ x, y, payload }) => {
              const isSelected = payload.value === selectedYear;
              return (
                <text
                  x={x as number}
                  y={(y as number) + 12}
                  textAnchor="middle"
                  fontSize={11}
                  fontWeight={isSelected ? 700 : 400}
                  fill={isSelected ? "#111827" : "#6B7280"}
                  style={{ cursor: "pointer" }}
                >
                  {payload.value}
                </text>
              );
            }}
          />
          <YAxis
            unit={` ${unit}`}
            tick={{ fontSize: 10, fill: "#6B7280" }}
            domain={[0, yMax]}
            width={44}
          />
          <Tooltip
            content={(props) => (
              <CustomTooltip
                active={props.active}
                payload={props.payload as unknown as TooltipPayload[]}
                label={props.label as string}
                unit={unit}
              />
            )}
            cursor={{ fill: "rgba(0,0,0,0.04)" }}
          />
          <Legend
            iconType={"square" as LegendType}
            formatter={(value) => (
              <Typography component="span" variant="caption" color="text.secondary">
                {value}
              </Typography>
            )}
          />
          {baselineMedian != null && (
            <ReferenceLine
              y={baselineMedian}
              stroke={BASELINE_COLOUR}
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{
                value: `2018 baseline: ${baselineMedian} ${unit}`,
                position: "insideTopRight",
                fill: BASELINE_COLOUR,
                fontSize: 9,
              }}
            />
          )}
          {/* Cancer confirmed — always rendered first so it appears in legend first */}
          <Bar
            dataKey="cancerMedian"
            name="Cancer confirmed"
            fill={CANCER_COLOUR}
            radius={[3, 3, 0, 0]}
            isAnimationActive={false}
            minPointSize={3}
          >
            {liveBars.map((entry) => (
              <Cell
                key={entry.year}
                fill={CANCER_COLOUR}
                fillOpacity={entry.year === selectedYear ? 1 : 0.55}
                cursor="pointer"
              />
            ))}
          </Bar>
          {showBenign && (
            <Bar
              dataKey="benignMedian"
              name="Benign/excluded"
              fill={BENIGN_COLOUR}
              radius={[3, 3, 0, 0]}
              isAnimationActive={false}
              minPointSize={3}
            >
              {liveBars.map((entry) => (
                <Cell
                  key={entry.year}
                  fill={BENIGN_COLOUR}
                  fillOpacity={entry.year === selectedYear ? 1 : 0.55}
                  cursor="pointer"
                />
              ))}
            </Bar>
          )}
        </BarChart>
      </ResponsiveContainer>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "center", mt: 0 }}>
        Bars show median days. Click a year to see individual referrals below.
      </Typography>
    </Box>
  );
}
