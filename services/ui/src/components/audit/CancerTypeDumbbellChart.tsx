"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { BENCHMARK_COLOURS, getBenchmarkLabels } from "./BenchmarkLegend";

export interface DumbbellRow {
  cancer_type: string;
  practice: number | null;
  national: number | null;
}

// Special-case display names for well-known multi-word type keys.
const LABEL_MAP: Record<string, string> = {
  lower_gi: "Lower GI",
  upper_gi: "Upper GI",
  head_and_neck: "Head and Neck",
  non_site_specific: "Non Site Specific",
  cns: "CNS",
  non_hodgkin: "Non-Hodgkin",
  cris: "CRiS",
  childrens_tumour: "Children's Tumour",
};

export function humaniseCancerLabel(key: string): string {
  if (LABEL_MAP[key]) return LABEL_MAP[key];
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

const COLOUR_ABOVE = "#16A34A";
const COLOUR_BELOW = "#D97706";
const COLOUR_NONE  = "#9CA3AF";

const LABEL_W  = 120;
const ROW_H    = 34;
const PLOT_W   = 380;
const DELTA_W  = 52;
const MARGIN_L = 8;
const MARGIN_R = 4;

function plotX(value: number, maxVal: number): number {
  return MARGIN_L + (value / maxVal) * PLOT_W;
}

interface RowProps {
  row: DumbbellRow;
  y: number;
  maxVal: number;
  orgSelected: boolean;
}

function DumbbellRowSvg({ row, y, maxVal }: RowProps) {
  const cy = y + ROW_H / 2;
  const p = row.practice;
  const n = row.national;

  const delta = p != null && n != null ? +(p - n).toFixed(1) : null;
  const lineColour =
    delta == null ? COLOUR_NONE
    : delta > 0   ? COLOUR_ABOVE
    : delta < 0   ? COLOUR_BELOW
    :               COLOUR_NONE;

  const px = p != null ? plotX(p, maxVal) : null;
  const nx = n != null ? plotX(n, maxVal) : null;

  const deltaLabel =
    delta != null
      ? `${delta > 0 ? "+" : ""}${delta}pp`
      : null;

  const diamondSize = 5;

  return (
    <g>
      {/* connecting line */}
      {px != null && nx != null && (
        <line
          x1={Math.min(px, nx)}
          y1={cy}
          x2={Math.max(px, nx)}
          y2={cy}
          stroke={lineColour}
          strokeWidth={2.5}
          strokeOpacity={0.6}
        />
      )}

      {/* today dot (filled circle) */}
      {px != null && (
        <circle
          cx={px}
          cy={cy}
          r={6}
          fill={BENCHMARK_COLOURS.practice}
          stroke="#fff"
          strokeWidth={1.5}
        />
      )}

      {/* 2018 benchmark (hollow diamond) */}
      {nx != null && (
        <polygon
          points={[
            `${nx},${cy - diamondSize}`,
            `${nx + diamondSize},${cy}`,
            `${nx},${cy + diamondSize}`,
            `${nx - diamondSize},${cy}`,
          ].join(" ")}
          fill="#fff"
          stroke={BENCHMARK_COLOURS.national}
          strokeWidth={2}
        />
      )}

      {/* delta label to the right of the rightmost point */}
      {deltaLabel != null && (px != null || nx != null) && (
        <text
          x={(Math.max(px ?? 0, nx ?? 0)) + 8}
          y={cy + 4}
          fontSize={9.5}
          fill={lineColour}
          dominantBaseline="middle"
        >
          {deltaLabel}
        </text>
      )}
    </g>
  );
}

function XAxisTicks({ maxVal, svgWidth }: { maxVal: number; svgWidth: number }) {
  const ticks: number[] = [];
  const step = maxVal <= 20 ? 5 : 10;
  for (let v = 0; v <= maxVal; v += step) ticks.push(v);

  return (
    <g>
      {ticks.map((v) => {
        const x = LABEL_W + MARGIN_L + (v / maxVal) * PLOT_W;
        return (
          <g key={v}>
            <line x1={x} y1={0} x2={x} y2={-6} stroke="#D1D5DB" strokeWidth={1} />
            <text x={x} y={-9} textAnchor="middle" fontSize={9} fill="#6B7280">
              {v}%
            </text>
          </g>
        );
      })}
      <line
        x1={LABEL_W + MARGIN_L}
        y1={0}
        x2={LABEL_W + MARGIN_L + PLOT_W + MARGIN_R}
        y2={0}
        stroke="#E5E7EB"
        strokeWidth={1}
      />
      {/* vertical gridlines */}
      {ticks.map((v) => {
        const x = LABEL_W + MARGIN_L + (v / maxVal) * PLOT_W;
        return (
          <line
            key={`grid-${v}`}
            x1={x}
            y1={0}
            x2={x}
            y2={9999}
            stroke="#F3F4F6"
            strokeWidth={1}
          />
        );
      })}
    </g>
  );
}

interface Props {
  rows: DumbbellRow[];
  orgSelected?: boolean;
}

export default function CancerTypeDumbbellChart({ rows, orgSelected = false }: Props) {
  const labels = getBenchmarkLabels(orgSelected);

  if (!rows || rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
        No cancer type data available for the selected period.
      </Typography>
    );
  }

  const allValues = rows.flatMap((r) =>
    [r.practice, r.national].filter((v): v is number => v != null)
  );
  const rawMax = allValues.length > 0 ? Math.max(...allValues) : 40;
  const maxVal = Math.ceil((rawMax + 3) / 5) * 5;

  const AXIS_H   = 24;
  const svgWidth = LABEL_W + MARGIN_L + PLOT_W + DELTA_W + MARGIN_R;
  const svgHeight = AXIS_H + rows.length * ROW_H + 8;

  return (
    <Box>
      {/* Legend */}
      <Box sx={{ display: "flex", gap: 3, mb: 1.5, flexWrap: "wrap" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box
            aria-hidden
            sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: BENCHMARK_COLOURS.practice, flexShrink: 0 }}
          />
          <Typography variant="caption" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
            {labels.practice}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box
            aria-hidden
            component="svg"
            width={12}
            height={12}
            viewBox="0 0 12 12"
            sx={{ flexShrink: 0 }}
          >
            <polygon points="6,0 12,6 6,12 0,6" fill="#fff" stroke={BENCHMARK_COLOURS.national} strokeWidth={2} />
          </Box>
          <Typography variant="caption" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
            {labels.national}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box aria-hidden sx={{ width: 18, height: 2.5, bgcolor: COLOUR_ABOVE, borderRadius: 1, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
            Above benchmark
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          <Box aria-hidden sx={{ width: 18, height: 2.5, bgcolor: COLOUR_BELOW, borderRadius: 1, flexShrink: 0 }} />
          <Typography variant="caption" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
            Below benchmark
          </Typography>
        </Box>
      </Box>

      <Box sx={{ overflowX: "auto" }}>
        <svg
          role="img"
          aria-label={`Dumbbell chart: cancer type distribution vs ${labels.national}. ${rows.length} cancer types shown.`}
          width={svgWidth}
          height={svgHeight}
          style={{ display: "block", minWidth: svgWidth }}
        >
          {/* Axis tick area */}
          <g transform={`translate(0, ${AXIS_H})`}>
            <XAxisTicks maxVal={maxVal} svgWidth={svgWidth} />
          </g>

          {/* Rows */}
          {rows.map((row, i) => {
            const rowY = AXIS_H + i * ROW_H;
            const cy = rowY + ROW_H / 2;

            return (
              <g key={row.cancer_type}>
                {/* row stripe (alternating) */}
                {i % 2 === 1 && (
                  <rect x={0} y={rowY} width={svgWidth} height={ROW_H} fill="#F9FAFB" />
                )}

                {/* cancer type label */}
                <text
                  x={LABEL_W - 8}
                  y={cy + 4}
                  textAnchor="end"
                  fontSize={11}
                  fill="#374151"
                  dominantBaseline="middle"
                >
                  {humaniseCancerLabel(row.cancer_type)}
                </text>

                {/* dumbbell (plot area starts at LABEL_W) */}
                <g transform={`translate(${LABEL_W}, 0)`}>
                  <DumbbellRowSvg
                    row={row}
                    y={rowY}
                    maxVal={maxVal}
                    orgSelected={orgSelected}
                  />
                </g>
              </g>
            );
          })}
        </svg>
      </Box>
    </Box>
  );
}
