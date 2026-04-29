/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BFF68D36
 *   DI: DI-077C8810
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BFF68D36")
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";

const COLOUR_LIVE = "#1D4ED8";
const COLOUR_BASELINE = "#92400E";
const COLOUR_GRID = "#E5E7EB";
const COLOUR_GRID_BOLD = "#9CA3AF";
const COLOUR_LABEL = "#4B5563";

const LOW_SAMPLE_THRESHOLD = 20;

const CHART_PADDING_X = 70;
const CHART_PADDING_Y = 56;
const MIN_RADIUS = 70;

export interface AxisDatum {
  key: string;
  label: string;
  value: number | null;
  count?: number | null;
}

interface Props {
  yearLabel: string;
  axes: AxisDatum[];
  baseline: AxisDatum[] | null;
  totalN: number;
  maxScale: number;
  loading?: boolean;
  isBaseline?: boolean;
  hasLiveData: boolean;
  /** When provided, renders a small expand button in the card header. */
  onZoom?: () => void;
}

interface PolarPoint {
  x: number;
  y: number;
}

interface RadarTooltipState {
  x: number;
  y: number;
  title: string;
  countLabel: string | null;
  pctLabel: string;
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

function shortenLabel(label: string): string {
  if (label.length <= 12) return label;
  return label.slice(0, 11) + "...";
}

function formatScaleLabel(level: number, maxScale: number): string {
  return `${Math.round(level * maxScale)}%`;
}

function formatPct(value: number): string {
  return `${value.toFixed(value % 1 === 0 ? 0 : 1)}%`;
}

function tooltipForDatum(datum: AxisDatum, point: PolarPoint): RadarTooltipState {
  const pctLabel = datum.value == null ? "No value" : formatPct(datum.value);
  return {
    x: point.x,
    y: point.y,
    title: datum.label,
    countLabel: datum.count == null ? null : `n = ${datum.count}`,
    pctLabel,
  };
}

export default function CancerTypeRadarCard({
  yearLabel,
  axes,
  baseline,
  totalN,
  maxScale,
  loading = false,
  isBaseline = false,
  hasLiveData,
  onZoom,
}: Props) {
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
  const [activeTooltip, setActiveTooltip] = useState<RadarTooltipState | null>(
    null,
  );

  const livePoly = polygonPoints(axes, cx, cy, outerRadius, maxScale);
  const baselinePoly = baseline
    ? polygonPoints(baseline, cx, cy, outerRadius, maxScale)
    : null;

  const showEmptyCaption = !loading && !hasLiveData && !isBaseline;
  const showLowSampleCaption =
    !loading &&
    hasLiveData &&
    !isBaseline &&
    totalN > 0 &&
    totalN < LOW_SAMPLE_THRESHOLD;

  const headerCaption = isBaseline
    ? "Baseline"
    : showEmptyCaption
      ? "No data yet"
      : showLowSampleCaption
        ? "Limited sample"
        : "Live";

  return (
    <Box
      ref={containerRef}
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
          alignItems: "center",
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
            sx={{ color: "text.secondary", fontSize: "0.7rem" }}
          >
            {headerCaption}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
          <Chip
            label={`n = ${totalN}`}
            size="small"
            variant="outlined"
            sx={{ fontWeight: 600, fontSize: "0.72rem" }}
            aria-label={`Sample size for ${yearLabel}: ${totalN} confirmed cancer cases`}
          />
          {onZoom && (
            <Tooltip title="Expand chart" placement="top">
              <IconButton
                aria-label={`Expand ${yearLabel} cancer type radar chart`}
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

      <Box sx={{ position: "relative", flex: 1 }}>
        <svg
          role="img"
          aria-label={`Radar chart of cancer type distribution for ${yearLabel}. Sample size n = ${totalN}.${
            isBaseline ? " 2018 NCDA baseline." : ""
          }`}
          width={svgW}
          height={svgH}
          style={{ display: "block", overflow: "visible" }}
        >
          {gridLevels.map((level, idx) => {
            const r = outerRadius * level;
            const isOuterRing = idx === gridLevels.length - 1;
            const ringPoints: string[] = [];
            for (let i = 0; i < total; i += 1) {
              const p = polar(cx, cy, r, angleFor(i, total));
              ringPoints.push(`${p.x.toFixed(2)},${p.y.toFixed(2)}`);
            }
            return (
              <g key={`grid-${level}`}>
                <polygon
                  points={ringPoints.join(" ")}
                  fill="none"
                  stroke={isOuterRing ? COLOUR_GRID_BOLD : COLOUR_GRID}
                  strokeWidth={isOuterRing ? 1.25 : 1}
                />
                {isOuterRing && (
                  <text
                    x={cx}
                    y={cy - outerRadius - 10}
                    fontSize={9}
                    fill={COLOUR_LABEL}
                    textAnchor="middle"
                    dominantBaseline="middle"
                  >
                    {formatScaleLabel(level, maxScale)} outer ring
                  </text>
                )}
              </g>
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

          {!isBaseline && baselinePoly && !baselinePoly.isEmpty && (
            <polygon
              points={baselinePoly.points}
              fill={COLOUR_BASELINE}
              fillOpacity={0.12}
              stroke={COLOUR_BASELINE}
              strokeOpacity={0.55}
              strokeWidth={1.25}
              strokeDasharray="3 3"
            />
          )}

          {(isBaseline || hasLiveData) && !livePoly.isEmpty && (
            <polygon
              points={livePoly.points}
              fill={isBaseline ? COLOUR_BASELINE : COLOUR_LIVE}
              fillOpacity={isBaseline ? 0.18 : 0.22}
              stroke={isBaseline ? COLOUR_BASELINE : COLOUR_LIVE}
              strokeWidth={2}
            />
          )}

          {(isBaseline || hasLiveData) &&
            axes.map((datum, idx) => {
              const r = valueRadius(datum.value, maxScale, outerRadius);
              const angle = angleFor(idx, total);
              const p = polar(cx, cy, r, angle);
              if (datum.value == null || datum.value <= 0) return null;
              const tooltip = tooltipForDatum(datum, p);
              const ariaLabel = `${datum.label}: ${
                tooltip.countLabel ? `${tooltip.countLabel}, ` : ""
              }${tooltip.pctLabel}`;
              return (
                <g
                  key={`dot-${idx}-${datum.key}`}
                  role="img"
                  tabIndex={0}
                  aria-label={ariaLabel}
                  onPointerEnter={() => setActiveTooltip(tooltip)}
                  onPointerMove={() => setActiveTooltip(tooltip)}
                  onPointerLeave={() => setActiveTooltip(null)}
                  onFocus={() => setActiveTooltip(tooltip)}
                  onBlur={() => setActiveTooltip(null)}
                  style={{ cursor: "default", outline: "none" }}
                >
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={8}
                    fill="transparent"
                    stroke="transparent"
                  />
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={3.25}
                    fill={isBaseline ? COLOUR_BASELINE : COLOUR_LIVE}
                    stroke="#FFFFFF"
                    strokeWidth={1}
                  />
                </g>
              );
            })}

          {axes.map((datum, idx) => {
            const angle = angleFor(idx, total);
            const labelRadius = outerRadius + 14;
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
                fontSize={9.5}
                fill={COLOUR_LABEL}
                textAnchor={textAnchor}
                dominantBaseline="middle"
              >
                {shortenLabel(datum.label)}
              </text>
            );
          })}
        </svg>

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

        {activeTooltip && (
          <Box
            role="tooltip"
            sx={{
              position: "absolute",
              left: activeTooltip.x,
              top: activeTooltip.y,
              transform: "translate(-50%, calc(-100% - 10px))",
              minWidth: 112,
              maxWidth: 180,
              px: 1,
              py: 0.75,
              borderRadius: 1,
              bgcolor: "rgba(17, 24, 39, 0.94)",
              color: "#FFFFFF",
              boxShadow: 3,
              pointerEvents: "none",
              zIndex: 2,
              textAlign: "center",
            }}
          >
            <Typography
              component="div"
              sx={{ fontSize: "0.72rem", fontWeight: 700, lineHeight: 1.2 }}
            >
              {activeTooltip.title}
            </Typography>
            <Typography
              component="div"
              sx={{ fontSize: "0.68rem", lineHeight: 1.35, opacity: 0.9 }}
            >
              {activeTooltip.countLabel
                ? `${activeTooltip.countLabel} (${activeTooltip.pctLabel})`
                : activeTooltip.pctLabel}
            </Typography>
          </Box>
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
          Limited sample - shape may stabilise as more cases are coded.
        </Typography>
      )}
    </Box>
  );
}
