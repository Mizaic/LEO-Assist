/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4DADBA3F")
 */
"use client";

/**
 * Multimorbidity radar: registry-ordered comorbidity buckets as % of audited cohort.
 */

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";

import type { AuditComorbidityRadarRow } from "@/lib/analyticsApi";

const COLOUR_LIVE = "#9338ff";
const COLOUR_BASELINE = "#92400E";
const COLOUR_GRID = "#E5E7EB";
const COLOUR_GRID_BOLD = "#9CA3AF";
const COLOUR_LABEL = "#4B5563";

const CHART_PADDING_X = 52;
const CHART_PADDING_Y = 40;
const MIN_RADIUS = 58;

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

function shorten(label: string): string {
  if (label.length <= 14) return label;
  return label.slice(0, 13).trimEnd() + "...";
}

function displayAxisLabel(label: string): string {
  const trimmed = label.trim();
  const canonical = trimmed
    .replace(/^history of\s+/i, "")
    .replace(/^parent has\s+/i, "")
    .replace(
      /\s*\((situation|disorder|disease|finding|clinical[_\s-]finding)\)\s*$/i,
      "",
    );

  const lower = canonical.toLowerCase();
  if (lower === "chronic obstructive airways disease") return "COPD";
  if (lower === "musculoskeletal disease") return "MSK disease";
  if (lower === "cardiovascular disease") return "Cardio disease";
  if (lower === "malignant neoplasm") return "Previous cancer";
  if (lower === "brain disorder") return "Cognitive issue";
  if (lower === "mental disorder") return "Severe mental illness";
  if (lower === "kidney disease") return "Renal disease";
  if (lower === "connective tissue disorder") return "CTD";
  if (lower === "complication due to diabetes mellitus") {
    return "DM complications";
  }

  return canonical;
}

export interface ComorbidityRadarCardProps {
  yearLabel: string;
  radar: AuditComorbidityRadarRow[];
  totalPatients: number;
  loading?: boolean;
  isBaseline?: boolean;
  /**
   * Optional shared radial max (%). When provided the card uses this scale
   * instead of computing its own per-card max, so all year cards in a
   * section share the same axis and shapes are visually comparable.
   */
  maxScale?: number;
  onBreakdown?: () => void;
  /** When provided, renders a small expand button in the card header. */
  onZoom?: () => void;
  /** Bare mode: skip card border/padding/header for use inside ChartZoomDialog. */
  bare?: boolean;
}

export default function ComorbidityRadarCard({
  yearLabel,
  radar,
  totalPatients,
  loading = false,
  isBaseline = false,
  maxScale: maxScaleProp,
  onBreakdown,
  onZoom,
  bare = false,
}: ComorbidityRadarCardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState(280);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      setContainerW(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const axes: AxisDatum[] = radar.map((row, idx) => {
    const displayLabel = displayAxisLabel(row.condition);
    return {
      key: `${row.condition}-${idx}`,
      label: shorten(displayLabel),
      fullLabel: row.condition,
      value: row.pct,
    };
  });

  const maxPct = axes.reduce((m, a) => Math.max(m, a.value ?? 0), 0);
  const maxScale = maxScaleProp ?? Math.min(100, Math.max(8, Math.ceil(maxPct + 4)));

  const svgW = Math.max(220, containerW);
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

  const hasRadarValues = axes.some((a) => (a.value ?? 0) > 0);
  const empty = total === 0 || (!isBaseline && totalPatients === 0);
  const headerCaption = loading
    ? "Loading..."
    : isBaseline
      ? "2018 NCDA baseline"
      : empty
        ? "No data yet"
        : "Live";

  const svgLayer = (
    <Box sx={{ position: "relative", minHeight: 200, flex: 1 }}>
        {loading ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            Loading chart...
          </Typography>
        ) : empty || !hasRadarValues ? (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            {isBaseline
              ? "Baseline comorbidity values are not available."
              : "No cohort patients to chart."}
          </Typography>
        ) : (
          <svg
            role="img"
            aria-label={`Comorbidity radar for ${yearLabel}`}
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
                  stroke={
                    idx === gridLevels.length - 1 ? COLOUR_GRID_BOLD : COLOUR_GRID
                  }
                  strokeWidth={idx === gridLevels.length - 1 ? 1.25 : 1}
                />
              );
            })}

            {axes.map((datum, idx) => {
              const end = polar(cx, cy, outerRadius, angleFor(idx, total));
              return (
                <line
                  key={`spoke-${datum.key}`}
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
                fill={isBaseline ? COLOUR_BASELINE : COLOUR_LIVE}
                fillOpacity={0.2}
                stroke={isBaseline ? COLOUR_BASELINE : COLOUR_LIVE}
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
                  key={`dot-${datum.key}`}
                  cx={p.x}
                  cy={p.y}
                  r={2}
                  fill={isBaseline ? COLOUR_BASELINE : COLOUR_LIVE}
                >
                  <title>{`${datum.fullLabel}: ${datum.value}%`}</title>
                </circle>
              );
            })}

            {axes.map((datum, idx) => {
              const angle = angleFor(idx, total);
              const labelRadius = outerRadius + 10;
              const p = polar(cx, cy, labelRadius, angle);
              const cosA = Math.cos(angle);
              let textAnchor: "start" | "middle" | "end" = "middle";
              if (cosA > 0.2) textAnchor = "start";
              else if (cosA < -0.2) textAnchor = "end";
              return (
                <text
                  key={`lab-${datum.key}`}
                  x={p.x}
                  y={p.y}
                  fontSize={6.5}
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
    </Box>
  );

  if (bare) {
    return (
      <Box
        ref={containerRef}
        role="group"
        aria-label={`Comorbidity radar for ${yearLabel}`}
        sx={{ position: "relative", width: "100%", height: "100%", display: "flex" }}
      >
        {svgLayer}
      </Box>
    );
  }

  return (
    <Box
      ref={containerRef}
      role="group"
      aria-label="Comorbidity multimorbidity radar"
      sx={{
        display: "flex",
        flexDirection: "column",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 1.5,
        bgcolor: "background.paper",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          mb: 0.75,
          gap: 1,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="h3"
            sx={{ fontSize: "0.9rem", fontWeight: 700, color: "text.primary" }}
          >
            {yearLabel}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontSize: "0.7rem" }}
          >
            {headerCaption}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
          <Chip
            label={isBaseline ? "2018 NCDA" : `n = ${totalPatients}`}
            size="small"
            variant={isBaseline ? "filled" : "outlined"}
            sx={{
              fontWeight: 600,
              fontSize: "0.72rem",
              bgcolor: isBaseline ? "#FEF3C7" : undefined,
              color: isBaseline ? COLOUR_BASELINE : undefined,
            }}
          />
          {onZoom && (
            <Tooltip title="Expand chart" placement="top">
              <IconButton
                aria-label={`Expand ${yearLabel} comorbidity radar chart`}
                size="small"
                onClick={onZoom}
                sx={{ p: 0.25, color: "text.secondary", "&:hover": { color: "primary.main" } }}
              >
                <OpenInFullIcon sx={{ fontSize: "0.85rem" }} />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Box>

      {svgLayer}

      <Typography
        variant="caption"
        sx={{ color: "text.secondary", fontSize: "0.65rem", mt: 0.5 }}
      >
        Each axis is % of the audited cohort with that condition (patients can
        have multiple).
      </Typography>
      {!isBaseline && onBreakdown ? (
        <Button
          variant="outlined"
          size="small"
          onClick={onBreakdown}
          sx={{ mt: 1, alignSelf: "flex-start" }}
        >
          Breakdown
        </Button>
      ) : null}
    </Box>
  );
}
