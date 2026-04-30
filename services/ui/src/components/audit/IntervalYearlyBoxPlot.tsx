/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

const CANCER_COLOUR = "#DC2626";
const BENIGN_COLOUR = "#16A34A";
const BASELINE_COLOUR = "#92400E";
const AXIS_COLOUR = "#CBD5E1";
const TEXT_COLOUR = "#475569";

export interface IntervalBoxStats {
  n: number;
  median: number | null;
  q1: number | null;
  q3: number | null;
}

export interface IntervalYearBoxDatum {
  year: string;
  cancer: IntervalBoxStats;
  benign: IntervalBoxStats;
  baseline?: IntervalBoxStats | null;
  isBaseline?: boolean;
  loading?: boolean;
  error?: string | null;
}

interface Props {
  yearData: IntervalYearBoxDatum[];
  showBenign: boolean;
  label: string;
  baselineLabel?: string;
  unit?: string;
}

function finiteValues(values: Array<number | null | undefined>): number[] {
  return values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
}

function niceMax(value: number): number {
  if (value <= 10) return 10;
  if (value <= 30) return Math.ceil(value / 5) * 5;
  if (value <= 100) return Math.ceil(value / 10) * 10;
  return Math.ceil(value / 50) * 50;
}

function BoxGlyph({
  x,
  width,
  stats,
  colour,
  yFor,
}: {
  x: number;
  width: number;
  stats: IntervalBoxStats;
  colour: string;
  yFor: (value: number) => number;
}) {
  if (stats.median == null) return null;

  const q1 = stats.q1 ?? stats.median;
  const q3 = stats.q3 ?? stats.median;
  const yTop = yFor(Math.max(q1, q3));
  const yBottom = yFor(Math.min(q1, q3));
  const boxHeight = Math.max(yBottom - yTop, 4);
  const yMedian = yFor(stats.median);

  return (
    <g>
      <rect
        x={x - width / 2}
        y={yTop}
        width={width}
        height={boxHeight}
        rx={3}
        fill={colour}
        fillOpacity={0.22}
        stroke={colour}
        strokeWidth={1.5}
      />
      <line
        x1={x - width / 2}
        x2={x + width / 2}
        y1={yMedian}
        y2={yMedian}
        stroke={colour}
        strokeWidth={2}
      />
      <circle cx={x} cy={yMedian} r={3} fill={colour} />
    </g>
  );
}

export default function IntervalYearlyBoxPlot({
  yearData,
  showBenign,
  label,
  baselineLabel = "2018 baseline",
  unit = "days",
}: Props) {
  const width = 720;
  const height = 230;
  const margin = { top: 18, right: 18, bottom: 48, left: 52 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;

  const values = finiteValues([
    ...yearData.flatMap((d) => [
      d.baseline?.q1,
      d.baseline?.q3,
      d.baseline?.median,
      d.cancer.q1,
      d.cancer.q3,
      d.cancer.median,
      showBenign ? d.benign.q1 : null,
      showBenign ? d.benign.q3 : null,
      showBenign ? d.benign.median : null,
    ]),
  ]);
  const yMax = niceMax(Math.max(...values, 1) * 1.15);
  const yFor = (value: number) =>
    margin.top + plotHeight - (Math.max(0, value) / yMax) * plotHeight;
  const tickValues = [0, yMax / 2, yMax].map((v) => Math.round(v));

  if (yearData.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
        No yearly {label.toLowerCase()} data available yet.
      </Typography>
    );
  }

  return (
    <Box>
      <Box
        role="group"
        aria-label={`${label} yearly box plot. Boxes show IQR and the dot shows median ${unit}.`}
        sx={{ width: "100%", overflowX: "auto" }}
      >
        <svg viewBox={`0 0 ${width} ${height}`} width="100%">
          {tickValues.map((tick) => {
            const y = yFor(tick);
            return (
              <g key={tick}>
                <line
                  x1={margin.left}
                  x2={width - margin.right}
                  y1={y}
                  y2={y}
                  stroke={AXIS_COLOUR}
                  strokeDasharray={tick === 0 ? undefined : "4 4"}
                />
                <text
                  x={margin.left - 8}
                  y={y + 4}
                  textAnchor="end"
                  fontSize={10}
                  fill={TEXT_COLOUR}
                >
                  {tick}
                </text>
              </g>
            );
          })}

          {yearData.map((datum, index) => {
            const band = plotWidth / yearData.length;
            const groupX = margin.left + band * index + band / 2;
            const boxWidth = Math.min(34, band * 0.22);
            const cancerX = showBenign ? groupX - boxWidth * 0.72 : groupX;
            const benignX = groupX + boxWidth * 0.72;

            return (
              <g key={datum.year}>
                {datum.isBaseline ? (
                  <BoxGlyph
                    x={groupX}
                    width={boxWidth * 1.2}
                    stats={datum.baseline ?? datum.cancer}
                    colour={BASELINE_COLOUR}
                    yFor={yFor}
                  />
                ) : (
                  <>
                    <BoxGlyph
                      x={cancerX}
                      width={boxWidth}
                      stats={datum.cancer}
                      colour={CANCER_COLOUR}
                      yFor={yFor}
                    />
                    {showBenign && (
                      <BoxGlyph
                        x={benignX}
                        width={boxWidth}
                        stats={datum.benign}
                        colour={BENIGN_COLOUR}
                        yFor={yFor}
                      />
                    )}
                  </>
                )}
                <text
                  x={groupX}
                  y={height - 26}
                  textAnchor="middle"
                  fontSize={12}
                  fontWeight={500}
                  fill={TEXT_COLOUR}
                >
                  {datum.year}
                </text>
                <text
                  x={groupX}
                  y={height - 10}
                  textAnchor="middle"
                  fontSize={10}
                  fill={TEXT_COLOUR}
                >
                  {datum.isBaseline
                    ? "baseline"
                    : `n=${datum.cancer.n + (showBenign ? datum.benign.n : 0)}`}
                </text>
              </g>
            );
          })}
        </svg>
      </Box>

      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 0.5 }}>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          <Box component="span" sx={{ color: CANCER_COLOUR, fontWeight: 700 }}>
            Red
          </Box>{" "}
          = cancer confirmed.
        </Typography>
        {showBenign && (
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            <Box component="span" sx={{ color: BENIGN_COLOUR, fontWeight: 700 }}>
              Green
            </Box>{" "}
            = benign/excluded.
          </Typography>
        )}
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          <Box component="span" sx={{ color: BASELINE_COLOUR, fontWeight: 700 }}>
            Brown
          </Box>{" "}
          = {baselineLabel}.
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          Boxes show IQR; dot and line show median. Referral dots are shown in the scatter plot below.
        </Typography>
      </Box>
    </Box>
  );
}
