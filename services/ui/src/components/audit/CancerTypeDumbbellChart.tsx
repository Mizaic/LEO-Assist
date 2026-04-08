"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { BENCHMARK_COLOURS, getBenchmarkLabels } from "./BenchmarkLegend";

export interface DumbbellRow {
  cancer_type: string;
  practice: number | null;
  national: number | null;
}

// Display names for NCDA cancer type keys and pathway-level fallback groups.
const LABEL_MAP: Record<string, string> = {
  // NCDA specific types
  colorectal: "Colorectal",
  oesophageal: "Oesophageal",
  stomach: "Stomach",
  pancreatic: "Pancreatic",
  liver: "Liver",
  gallbladder: "Gallbladder",
  small_intestine: "Small Intestine",
  oropharyngeal: "Oropharyngeal",
  laryngeal: "Laryngeal",
  thyroid: "Thyroid",
  leukaemia: "Leukaemia",
  lymphoma: "Lymphoma",
  myeloma: "Myeloma",
  ovarian: "Ovarian",
  endometrial: "Endometrial",
  cervical: "Cervical",
  vulval: "Vulval",
  prostate: "Prostate",
  bladder: "Bladder",
  renal: "Renal",
  testicular: "Testicular",
  mesothelioma: "Mesothelioma",
  melanoma: "Melanoma",
  // Pathway-level fallbacks (2WW referrals without specific diagnosis)
  upper_gi: "Upper GI",
  lower_gi: "Lower GI",
  head_and_neck: "Head and Neck",
  gynaecological: "Gynaecological",
  urological: "Urological",
  haematological: "Haematological",
  // Other categories
  non_site_specific: "Non Site Specific",
  unknown_primary: "Unknown Primary",
  childrens_tumour: "Children's Tumour",
  cns: "CNS",
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

// Fixed layout constants (px in SVG coordinate space)
const LABEL_W   = 120;
const ROW_H     = 34;
const DELTA_W   = 54;   // reserved width for the +/-Xpp label after the rightmost dot
const MARGIN_L  = 0;    // gap between label column and plot
const MARGIN_R  = 4;
const AXIS_H    = 24;

function px(value: number, maxVal: number, plotW: number): number {
  return MARGIN_L + (value / maxVal) * plotW;
}

interface RowSvgProps {
  row: DumbbellRow;
  rowY: number;
  maxVal: number;
  plotW: number;
}

function DumbbellRowSvg({ row, rowY, maxVal, plotW }: RowSvgProps) {
  const cy = rowY + ROW_H / 2;
  const p = row.practice;
  const n = row.national;

  const delta = p != null && n != null ? +(p - n).toFixed(1) : null;
  const lineColour =
    delta == null ? COLOUR_NONE
    : delta > 0   ? COLOUR_ABOVE
    : delta < 0   ? COLOUR_BELOW
    :               COLOUR_NONE;

  const dotPx = p != null ? px(p, maxVal, plotW) : null;
  const dotNx = n != null ? px(n, maxVal, plotW) : null;

  // Only show the delta annotation when there is a meaningful difference.
  // Suppress the label when delta is zero (dots overlap) to avoid visual clutter.
  const deltaLabel =
    delta != null && delta !== 0
      ? `${delta > 0 ? "+" : ""}${delta}pp`
      : null;

  const ds = 5; // diamond half-size

  return (
    <g>
      {/* connecting line between the two dots */}
      {dotPx != null && dotNx != null && delta !== 0 && (
        <line
          x1={Math.min(dotPx, dotNx)}
          y1={cy}
          x2={Math.max(dotPx, dotNx)}
          y2={cy}
          stroke={lineColour}
          strokeWidth={2.5}
          strokeOpacity={0.6}
        />
      )}

      {/* today dot (filled circle) */}
      {dotPx != null && (
        <circle cx={dotPx} cy={cy} r={6} fill={BENCHMARK_COLOURS.practice} stroke="#fff" strokeWidth={1.5} />
      )}

      {/* 2018 benchmark dot (hollow diamond) */}
      {dotNx != null && (
        <polygon
          points={[
            `${dotNx},${cy - ds}`,
            `${dotNx + ds},${cy}`,
            `${dotNx},${cy + ds}`,
            `${dotNx - ds},${cy}`,
          ].join(" ")}
          fill="#fff"
          stroke={BENCHMARK_COLOURS.national}
          strokeWidth={2}
        />
      )}

      {/* delta annotation to the right of the rightmost point */}
      {deltaLabel != null && (dotPx != null || dotNx != null) && (
        <text
          x={Math.max(dotPx ?? 0, dotNx ?? 0) + 9}
          y={cy}
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

interface AxisProps {
  maxVal: number;
  plotW: number;
  totalRows: number;
}

function XAxisTicks({ maxVal, plotW, totalRows }: AxisProps) {
  const step = maxVal <= 20 ? 5 : 10;
  const ticks: number[] = [];
  for (let v = 0; v <= maxVal; v += step) ticks.push(v);
  const totalH = totalRows * ROW_H;

  return (
    <g>
      {/* vertical gridlines extending through all rows */}
      {ticks.map((v) => {
        const x = LABEL_W + MARGIN_L + (v / maxVal) * plotW;
        return (
          <line key={`grid-${v}`} x1={x} y1={0} x2={x} y2={totalH} stroke="#F3F4F6" strokeWidth={1} />
        );
      })}
      {/* baseline */}
      <line x1={LABEL_W + MARGIN_L} y1={0} x2={LABEL_W + MARGIN_L + plotW} y2={0} stroke="#E5E7EB" strokeWidth={1} />
      {/* tick marks and labels (drawn above the baseline using negative y) */}
      {ticks.map((v) => {
        const x = LABEL_W + MARGIN_L + (v / maxVal) * plotW;
        return (
          <g key={v}>
            <line x1={x} y1={0} x2={x} y2={-5} stroke="#D1D5DB" strokeWidth={1} />
            <text x={x} y={-8} textAnchor="middle" fontSize={9} fill="#6B7280">
              {v}%
            </text>
          </g>
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
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState(640);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      setContainerW(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

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

  // plotW fills the container; minimum 180 px so the chart stays readable.
  const plotW = Math.max(180, containerW - LABEL_W - MARGIN_L - DELTA_W - MARGIN_R);
  const svgW  = containerW;
  const svgH  = AXIS_H + rows.length * ROW_H + 4;

  return (
    <Box ref={containerRef}>
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

      <svg
        role="img"
        aria-label={`Dumbbell chart: cancer type distribution vs ${labels.national}. ${rows.length} cancer types shown.`}
        width={svgW}
        height={svgH}
        style={{ display: "block", overflow: "visible" }}
      >
        {/* Axis (positioned at AXIS_H so tick labels sit above row 0) */}
        <g transform={`translate(0, ${AXIS_H})`}>
          <XAxisTicks maxVal={maxVal} plotW={plotW} totalRows={rows.length} />
        </g>

        {/* Rows */}
        {rows.map((row, i) => {
          const rowY = AXIS_H + i * ROW_H;
          const cy   = rowY + ROW_H / 2;

          return (
            <g key={row.cancer_type}>
              {/* alternating stripe fills full SVG width */}
              {i % 2 === 1 && (
                <rect x={0} y={rowY} width={svgW} height={ROW_H} fill="#F9FAFB" />
              )}

              {/* cancer type label — right-aligned flush against the plot edge */}
              <text
                x={LABEL_W - 6}
                y={cy}
                textAnchor="end"
                fontSize={11}
                fill="#374151"
                dominantBaseline="middle"
              >
                {humaniseCancerLabel(row.cancer_type)}
              </text>

              {/* dumbbell elements (plot area starts at LABEL_W) */}
              <g transform={`translate(${LABEL_W}, 0)`}>
                <DumbbellRowSvg row={row} rowY={rowY} maxVal={maxVal} plotW={plotW} />
              </g>
            </g>
          );
        })}
      </svg>
    </Box>
  );
}
