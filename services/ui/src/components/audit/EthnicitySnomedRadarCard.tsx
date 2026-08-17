/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Risk: R-05B6DDA7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4DADBA3F")
 */
"use client";

/**
 * Radar of NCDA ethnicity SNOMED buckets (pct of sex-tabulated cohort).
 * Header surfaces cohort size vs patients with any coded ethnicity link.
 */

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

import type { AuditDemographics } from "@/lib/analyticsApi";

const COLOUR_LIVE = "#0d46d6";
const COLOUR_GRID = "#E5E7EB";
const COLOUR_GRID_BOLD = "#9CA3AF";
const COLOUR_LABEL = "#4B5563";

const LOW_SAMPLE_THRESHOLD = 20;

const CHART_PADDING_X = 56;
const CHART_PADDING_Y = 44;
const MIN_RADIUS = 62;

export interface EthnicitySnomedRadarCardProps {
  yearLabel: string;
  ethnicityBySnomed: AuditDemographics["ethnicity_by_snomed"];
  demographicsCohortN: number;
  patientsWithEthnicitySnomedN: number;
  ethnicitySnomedCoveragePct: number | null;
  loading?: boolean;
  /**
   * Optional shared radial max (%). When provided the card uses this scale
   * instead of computing its own per-card max, so all year cards in the
   * section share the same axis and shapes are visually comparable.
   */
  maxScale?: number | null;
}

interface AxisDatum {
  key: string;
  label: string;
  fullLabel: string;
  value: number | null;
}

interface PolarPoint {
  x: number;
  y: number;
}

function polar(
  cx: number,
  cy: number,
  radius: number,
  angle: number,
): PolarPoint {
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  };
}

function angleFor(index: number, total: number): number {
  return -Math.PI / 2 + (index * (2 * Math.PI)) / total;
}

function valueRadius(
  value: number | null,
  maxScale: number,
  outerRadius: number,
): number {
  if (value == null || maxScale <= 0) return 0;
  const clamped = Math.max(0, Math.min(value, maxScale));
  return (clamped / maxScale) * outerRadius;
}

function polygonPoints(
  axes: AxisDatum[],
  cx: number,
  cy: number,
  outerRadius: number,
  maxScale: number,
): { points: string; isEmpty: boolean } {
  const total = axes.length;
  if (total === 0) return { points: "", isEmpty: true };
  let sawValue = false;
  const coords: string[] = [];
  axes.forEach((datum, idx) => {
    const r = valueRadius(datum.value, maxScale, outerRadius);
    if (datum.value != null && datum.value > 0) sawValue = true;
    const p = polar(cx, cy, r, angleFor(idx, total));
    coords.push(`${p.x.toFixed(2)},${p.y.toFixed(2)}`);
  });
  return { points: coords.join(" "), isEmpty: !sawValue };
}

function shortenEthnicityLabel(label: string): string {
  if (label.length <= 10) return label;
  return label.slice(0, 9).trimEnd() + "...";
}

export default function EthnicitySnomedRadarCard({
  yearLabel,
  ethnicityBySnomed,
  demographicsCohortN,
  patientsWithEthnicitySnomedN,
  ethnicitySnomedCoveragePct,
  loading = false,
  maxScale: maxScaleProp = null,
}: EthnicitySnomedRadarCardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState(320);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      setContainerW(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const axes: AxisDatum[] = ethnicityBySnomed.map((row) => ({
    key: row.snomed,
    label: shortenEthnicityLabel(row.benchmark_key),
    fullLabel: row.benchmark_key,
    value: row.pct,
  }));

  const maxPct = axes.reduce(
    (m, a) => Math.max(m, a.value ?? 0),
    0,
  );
  const maxScale = maxScaleProp && maxScaleProp > 0
    ? maxScaleProp
    : Math.min(100, Math.max(12, Math.ceil(maxPct + 4)));

  const svgW = Math.max(240, containerW);
  const svgH = svgW;
  const cx = svgW / 2;
  const cy = svgH / 2;
  const outerRadius = Math.max(
    MIN_RADIUS,
    Math.min(svgW / 2 - CHART_PADDING_X, svgH / 2 - CHART_PADDING_Y),
  );

  const total = axes.length;
  const gridLevels = [0.25, 0.5, 0.75, 1];

  const livePoly = polygonPoints(axes, cx, cy, outerRadius, maxScale);

  const showEmptyCaption =
    !loading && demographicsCohortN === 0;
  const showLowSampleCaption =
    !loading &&
    demographicsCohortN > 0 &&
    demographicsCohortN < LOW_SAMPLE_THRESHOLD;

  const headerCaption = loading
    ? "Loading..."
    : showEmptyCaption
      ? "No data yet"
      : showLowSampleCaption
        ? "Limited sample"
        : "Live";

  const coverageLine =
    demographicsCohortN > 0
      ? `${demographicsCohortN} patient${demographicsCohortN === 1 ? "" : "s"} in cohort; ${patientsWithEthnicitySnomedN} with SNOMED ethnicity coded` +
        (ethnicitySnomedCoveragePct != null
          ? ` (${ethnicitySnomedCoveragePct}% of cohort).`
          : ".")
      : "";

  return (
    <Box
      ref={containerRef}
      role="group"
      aria-label={`Ethnicity SNOMED radar for ${yearLabel}`}
      sx={{
        display: "flex",
        flexDirection: "column",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 1.5,
        bgcolor: "background.paper",
        height: "100%",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          mb: 0.5,
          gap: 1,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="h3"
            sx={{ fontSize: "0.95rem", fontWeight: 700, color: "text.primary" }}
          >
            {yearLabel}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontSize: "0.7rem", display: "block" }}
          >
            {headerCaption}
          </Typography>
          {!loading && coverageLine ? (
            <Typography
              variant="caption"
              sx={{
                color: "text.secondary",
                fontSize: "0.68rem",
                display: "block",
                mt: 0.35,
                lineHeight: 1.35,
              }}
            >
              {coverageLine}
            </Typography>
          ) : null}
        </Box>
        <Chip
          label={`n = ${demographicsCohortN}`}
          size="small"
          variant="outlined"
          sx={{ fontWeight: 600, fontSize: "0.72rem", flexShrink: 0 }}
          aria-label={`Cohort size for ${yearLabel}: ${demographicsCohortN} patients`}
        />
      </Box>

      <Box sx={{ position: "relative", flex: 1, minHeight: 220 }}>
        {loading ? (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              minHeight: 220,
            }}
          >
            <Typography variant="caption" color="text.secondary">
              Loading chart...
            </Typography>
          </Box>
        ) : total === 0 ? (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              minHeight: 220,
            }}
          >
            <Typography variant="caption" color="text.secondary">
              No ethnicity axes loaded.
            </Typography>
          </Box>
        ) : (
          <svg
            role="img"
            aria-label={`Radar of ethnicity SNOMED shares for ${yearLabel}. Cohort ${demographicsCohortN} patients.`}
            width={svgW}
            height={svgH}
            style={{ display: "block", overflow: "visible" }}
          >
          {gridLevels.map((level, idx) => {
            const r = outerRadius * level;
            const ringPoints: string[] = [];
            for (let i = 0; i < total; i += 1) {
              const p = polar(cx, cy, r, angleFor(i, total));
              ringPoints.push(`${p.x.toFixed(2)},${p.y.toFixed(2)}`);
            }
            return (
              <polygon
                key={`grid-${level}`}
                points={ringPoints.join(" ")}
                fill="none"
                stroke={idx === gridLevels.length - 1 ? COLOUR_GRID_BOLD : COLOUR_GRID}
                strokeWidth={idx === gridLevels.length - 1 ? 1.25 : 1}
              />
            );
          })}

          {axes.map((datum, idx) => {
            const end = polar(cx, cy, outerRadius, angleFor(idx, total));
            return (
              <line
                key={`spoke-${idx}-${datum.key}`}
                x1={cx}
                y1={cy}
                x2={end.x}
                y2={end.y}
                stroke={COLOUR_GRID}
                strokeWidth={1}
              />
            );
          })}

          {!livePoly.isEmpty && (
            <polygon
              points={livePoly.points}
              fill={COLOUR_LIVE}
              fillOpacity={0.22}
              stroke={COLOUR_LIVE}
              strokeWidth={2}
            />
          )}

          {axes.map((datum, idx) => {
            const r = valueRadius(datum.value, maxScale, outerRadius);
            const angle = angleFor(idx, total);
            const p = polar(cx, cy, r, angle);
            if (datum.value == null || datum.value <= 0) return null;
            return (
              <circle
                key={`dot-${idx}-${datum.key}`}
                cx={p.x}
                cy={p.y}
                r={2.2}
                fill={COLOUR_LIVE}
              >
                <title>{`${datum.fullLabel}: ${datum.value}% of cohort`}</title>
              </circle>
            );
          })}

          {axes.map((datum, idx) => {
            const angle = angleFor(idx, total);
            const labelRadius = outerRadius + 11;
            const p = polar(cx, cy, labelRadius, angle);
            const cosA = Math.cos(angle);
            let textAnchor: "start" | "middle" | "end" = "middle";
            if (cosA > 0.2) textAnchor = "start";
            else if (cosA < -0.2) textAnchor = "end";
            return (
              <text
                key={`label-${idx}-${datum.key}`}
                x={p.x}
                y={p.y}
                fontSize={7}
                fill={COLOUR_LABEL}
                textAnchor={textAnchor}
                dominantBaseline="middle"
              >
                <title>{datum.fullLabel}</title>
                {datum.label}
              </text>
            );
          })}
        </svg>
        )}

        {showEmptyCaption && (
          <Typography
            variant="caption"
            sx={{
              position: "absolute",
              top: "50%",
              left: 0,
              right: 0,
              textAlign: "center",
              transform: "translateY(-50%)",
              color: "text.secondary",
              fontStyle: "italic",
              fontSize: "0.78rem",
              pointerEvents: "none",
            }}
          >
            No data yet for {yearLabel}
          </Typography>
        )}
      </Box>

      {showLowSampleCaption && (
        <Typography
          variant="caption"
          sx={{
            mt: 0.75,
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.7rem",
            display: "block",
          }}
        >
          Limited sample - radar shape may stabilise as more cases are coded.
        </Typography>
      )}

      <Typography
        variant="caption"
        sx={{
          color: "text.secondary",
          fontSize: "0.65rem",
          display: "block",
          mt: "auto",
          lineHeight: 1.35,
        }}
      >
        Each axis is NCDA ethnicity SNOMED share of the cohort (distinct
        patients per category). Hover dots for full labels.
      </Typography>
    </Box>
  );
}
