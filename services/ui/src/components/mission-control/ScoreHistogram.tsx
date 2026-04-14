"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ScatterPlotIcon from "@mui/icons-material/ScatterPlot";
import type { EncounterListItem } from "@/lib/missionControlApi";

// ---- layout ----------------------------------------------------------------
const N = 20; // buckets (5% each)
const BAR_GAP = 2;
const CHART_H = 140;
const TOP_PAD = 28; // room for count badges above bars
const AXIS_H = 22; // x-axis tick labels
const SVG_H = TOP_PAD + CHART_H + AXIS_H;
const HANDLE_R = 8;

// ---- palette ---------------------------------------------------------------
const TYPE_COLOR: Record<string, string> = {
  keyword: "#4F46E5",
  hybrid: "#7C3AED",
  semantic: "#0891B2",
  none: "#94A3B8",
};
const TYPE_LABEL: Record<string, string> = {
  keyword: "Keyword hit",
  hybrid: "Keyword + meaning match",
  semantic: "Meaning match only",
  none: "Unclassified",
};
const GAP_COLOR = "#0D9488"; // teal for natural-break line

// ---- types -----------------------------------------------------------------
interface Bucket {
  lo: number;
  hi: number;
  total: number;
  byType: Partial<Record<string, number>>;
}

interface Recommendation {
  message: string;
  suggested?: number;
  gapAt?: number;
}

export interface BucketFilter {
  lo: number;
  hi: number;
}

interface Props {
  rows: EncounterListItem[];
  minCombinedScore: number;
  onThresholdChange: (score: number) => void;
  onBucketFilter?: (filter: BucketFilter | null) => void;
  onShow3D?: () => void;
}

// ---- helpers ---------------------------------------------------------------
function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

function snap5(v: number): number {
  return Math.round(v * 20) / 20;
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function buildBuckets(rows: EncounterListItem[]): Bucket[] {
  const step = 1 / N;
  const buckets: Bucket[] = Array.from({ length: N }, (_, i) => ({
    lo: i * step,
    hi: (i + 1) * step,
    total: 0,
    byType: {},
  }));
  for (const row of rows) {
    const s = typeof row.score === "number" ? row.score : null;
    if (s === null) continue;
    const idx = clamp(Math.floor(s * N), 0, N - 1);
    const b = buckets[idx]!;
    b.total++;
    const t = row.match_type ?? "none";
    b.byType[t] = (b.byType[t] ?? 0) + 1;
  }
  return buckets;
}

function findNaturalGap(buckets: Bucket[]): number | null {
  // Find largest zero-or-low span between two non-empty buckets
  let maxGap = 0;
  let gapIdx = -1;
  for (let i = 0; i < buckets.length - 1; i++) {
    const gap = (buckets[i + 1]?.total ?? 0) === 0
      ? 2
      : (buckets[i]?.total ?? 0) === 0
        ? 1
        : 0;
    const scoreGap = (buckets[i + 1]?.lo ?? 0) - (buckets[i]?.hi ?? 0);
    const weight = gap + scoreGap;
    if ((buckets[i]?.total ?? 0) > 0 && (buckets[i + 1]?.total ?? 0) > 0) {
      // score jump between non-empty adjacent buckets
      const diff = 0;
      if (diff > maxGap) { maxGap = diff; gapIdx = i; }
    }
  }
  // Simpler: find empty bucket between two populated ones
  const totals = buckets.map((b) => b.total);
  for (let i = 1; i < totals.length - 1; i++) {
    if ((totals[i] ?? 0) === 0 && (totals[i - 1] ?? 0) > 0 && (totals[i + 1] ?? 0) > 0) {
      return snap5((buckets[i]!.lo + buckets[i]!.hi) / 2);
    }
  }
  // Find biggest count gap between adjacent non-empty buckets
  let bestJump = 0;
  let bestIdx = -1;
  for (let i = 0; i < totals.length - 1; i++) {
    const a = totals[i] ?? 0;
    const b = totals[i + 1] ?? 0;
    if (a > 0 && b > 0) continue; // both populated - not a gap
  }
  // Fall back: largest score gap between non-zero buckets
  const nonEmpty = buckets.filter((b) => b.total > 0);
  for (let i = 0; i < nonEmpty.length - 1; i++) {
    const jump = (nonEmpty[i + 1]?.lo ?? 0) - (nonEmpty[i]?.hi ?? 0);
    if (jump > bestJump) { bestJump = jump; bestIdx = i; }
  }
  if (bestIdx >= 0 && bestJump >= 0.04 && nonEmpty[bestIdx]) {
    return snap5(((nonEmpty[bestIdx]!.hi) + (nonEmpty[bestIdx + 1]?.lo ?? 0)) / 2);
  }
  return null;
}

function buildRecommendation(
  buckets: Bucket[],
  minScore: number
): Recommendation | null {
  const total = buckets.reduce((s, b) => s + b.total, 0);
  if (total === 0) return null;

  const gapAt = findNaturalGap(buckets);
  const kept = buckets.filter((b) => b.lo >= minScore).reduce((s, b) => s + b.total, 0);

  if (gapAt != null) {
    const above = buckets.filter((b) => b.lo >= gapAt).reduce((s, b) => s + b.total, 0);
    const atGap = Math.abs(minScore - gapAt) <= 0.05;
    if (atGap) {
      return { message: `Good split -- ${above} strong matches above the natural break at ${pct(gapAt)}.`, gapAt };
    }
    return {
      message: `Natural break at ${pct(gapAt)} -- ${above} results above, ${total - above} below. Setting the cut-off here gives the cleanest split.`,
      suggested: gapAt,
      gapAt,
    };
  }

  if (kept === total) {
    return { message: `All ${total} results pass the cut-off. The bars show where they cluster -- raise the cut-off to narrow down.` };
  }
  return { message: `${kept} of ${total} results above the cut-off.` };
}

// ---- component -------------------------------------------------------------
export default function ScoreHistogram({
  rows,
  minCombinedScore,
  onThresholdChange,
  onBucketFilter,
  onShow3D,
}: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [svgW, setSvgW] = useState(600);
  const [dragging, setDragging] = useState(false);
  const [activeBucket, setActiveBucket] = useState<BucketFilter | null>(null);

  const handleBarClick = useCallback(
    (lo: number, hi: number) => {
      const next = activeBucket?.lo === lo ? null : { lo, hi };
      setActiveBucket(next);
      onBucketFilter?.(next);
    },
    [activeBucket, onBucketFilter],
  );

  useEffect(() => {
    const el = svgRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(() => setSvgW(el.getBoundingClientRect().width));
    ro.observe(el);
    setSvgW(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);

  const buckets = useMemo(() => buildBuckets(rows), [rows]);
  const recommendation = useMemo(
    () => buildRecommendation(buckets, minCombinedScore),
    [buckets, minCombinedScore]
  );

  const maxCount = useMemo(() => Math.max(1, ...buckets.map((b) => b.total)), [buckets]);
  const barW = (svgW - 1) / N;

  // threshold -> pixel X
  const threshX = minCombinedScore * svgW;
  const gapX = recommendation?.gapAt != null ? recommendation.gapAt * svgW : null;

  const kept = useMemo(
    () => buckets.filter((b) => b.lo >= minCombinedScore).reduce((s, b) => s + b.total, 0),
    [buckets, minCombinedScore]
  );
  const removed = rows.filter((r) => typeof r.score === "number" && r.score < minCombinedScore).length;

  const scoreFromX = useCallback(
    (clientX: number) => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return minCombinedScore;
      return snap5(clamp((clientX - rect.left) / rect.width, 0, 1));
    },
    [minCombinedScore]
  );

  useEffect(() => {
    if (!dragging) return;
    const move = (e: MouseEvent) => onThresholdChange(scoreFromX(e.clientX));
    const up = () => setDragging(false);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [dragging, scoreFromX, onThresholdChange]);

  // build bar segments
  const barSegments = useMemo(() => {
    const types = ["keyword", "hybrid", "semantic", "none"] as const;
    return buckets.map((b, i) => {
      const x = i * barW + BAR_GAP / 2;
      const w = barW - BAR_GAP;
      const below = b.lo < minCombinedScore;
      const segments: Array<{ y: number; h: number; fill: string; type: string }> = [];
      let stackH = 0;
      for (const t of types) {
        const count = b.byType[t] ?? 0;
        if (!count) continue;
        const h = (count / maxCount) * CHART_H;
        const fill = below ? "#CBD5E1" : TYPE_COLOR[t] ?? "#94A3B8";
        segments.push({ y: TOP_PAD + CHART_H - stackH - h, h, fill, type: t });
        stackH += h;
      }
      return { x, w, segments, below, total: b.total, lo: b.lo, hi: b.hi };
    });
  }, [buckets, barW, minCombinedScore, maxCount]);

  return (
    <Box sx={{ mt: 1.5, p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2, bgcolor: "background.paper" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.75 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Score map</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          {onShow3D && (
            <Chip
              size="small"
              label="Show 3D"
              icon={<ScatterPlotIcon sx={{ fontSize: "14px !important" }} />}
              onClick={onShow3D}
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 24 }}
            />
          )}
        </Stack>
      </Stack>

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        Each bar is a group of results. Drag the blue line to set your cut-off.
        Coloured bars stay. Grey bars would be removed.
      </Typography>

      {recommendation && (
        <Alert
          severity={recommendation.suggested != null ? "info" : "success"}
          sx={{ mb: 1.5, py: 0.5, fontSize: "0.76rem", alignItems: "center" }}
          action={
            recommendation.suggested != null ? (
              <Chip
                label={`Use ${pct(recommendation.suggested)}`}
                size="small"
                color="primary"
                variant="outlined"
                onClick={() => onThresholdChange(recommendation.suggested!)}
                sx={{ cursor: "pointer", whiteSpace: "nowrap" }}
              />
            ) : undefined
          }
        >
          {recommendation.message}
        </Alert>
      )}

      {/* SVG histogram */}
      <Box sx={{ position: "relative" }}>
        <svg
          ref={svgRef}
          width="100%"
          height={SVG_H}
          style={{ display: "block", overflow: "visible" }}
        >
          <defs>
            {Object.entries(TYPE_COLOR).map(([type, color]) => (
              <linearGradient key={type} id={`grad-${type}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity="0.95" />
                <stop offset="100%" stopColor={color} stopOpacity="0.65" />
              </linearGradient>
            ))}
            <linearGradient id="grad-grey" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#CBD5E1" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#CBD5E1" stopOpacity="0.5" />
            </linearGradient>
          </defs>

          {/* Subtle grid lines */}
          {[0.25, 0.5, 0.75, 1].map((f) => (
            <line
              key={f}
              x1={0}
              x2={svgW}
              y1={TOP_PAD + CHART_H - f * CHART_H}
              y2={TOP_PAD + CHART_H - f * CHART_H}
              stroke="#E2E8F0"
              strokeWidth={1}
            />
          ))}

          {/* Bars */}
          {barSegments.map((bar, i) => {
            const isActive = activeBucket?.lo === bar.lo;
            const isDimmed = activeBucket !== null && !isActive;
            const barH = bar.segments.reduce((sum, s) => sum + s.h, 0);
            const barTopY = bar.segments.length > 0
              ? Math.min(...bar.segments.map((s) => s.y))
              : TOP_PAD + CHART_H;
            return (
              <g
                key={i}
                onClick={() => bar.total > 0 && handleBarClick(bar.lo, bar.hi)}
                style={{ cursor: bar.total > 0 ? "pointer" : "default" }}
                opacity={isDimmed ? 0.35 : 1}
              >
                {bar.segments.map((seg, j) => (
                  <Tooltip
                    key={j}
                    title={`${bar.total} result${bar.total !== 1 ? "s" : ""} scoring ${pct(bar.lo)}-${pct(bar.hi)} (${TYPE_LABEL[seg.type] ?? seg.type})${bar.total > 0 ? " — click to filter" : ""}`}
                    placement="top"
                    arrow
                  >
                    <rect
                      x={bar.x}
                      y={seg.y}
                      width={bar.w}
                      height={seg.h}
                      fill={bar.below ? "url(#grad-grey)" : `url(#grad-${seg.type})`}
                      rx={j === bar.segments.length - 1 ? 3 : 0}
                      ry={j === bar.segments.length - 1 ? 3 : 0}
                    />
                  </Tooltip>
                ))}
                {/* Selection ring on active bucket */}
                {isActive && barH > 0 && (
                  <rect
                    x={bar.x - 1}
                    y={barTopY - 1}
                    width={bar.w + 2}
                    height={barH + 2}
                    fill="none"
                    stroke="#3B5FD9"
                    strokeWidth={2}
                    rx={3}
                    ry={3}
                    style={{ pointerEvents: "none" }}
                  />
                )}
              </g>
            );
          })}

          {/* Baseline */}
          <line
            x1={0} x2={svgW}
            y1={TOP_PAD + CHART_H} y2={TOP_PAD + CHART_H}
            stroke="#CBD5E1" strokeWidth={1}
          />

          {/* Natural break line */}
          {gapX != null && (
            <g>
              <line
                x1={gapX} x2={gapX}
                y1={TOP_PAD} y2={TOP_PAD + CHART_H}
                stroke={GAP_COLOR} strokeWidth={1.5} strokeDasharray="3 3"
              />
              <text x={gapX + 4} y={TOP_PAD + 10} fontSize={9} fill={GAP_COLOR}>
                Natural break
              </text>
            </g>
          )}

          {/* Threshold line */}
          <line
            x1={threshX} x2={threshX}
            y1={TOP_PAD - 4} y2={TOP_PAD + CHART_H}
            stroke="#3B5FD9" strokeWidth={2} strokeDasharray="5 3"
          />

          {/* Count badges above threshold */}
          <g>
            {/* Left badge - removing */}
            {threshX > 60 && (
              <g>
                <rect x={2} y={4} width={threshX - 6} height={18} rx={4}
                  fill="#F1F5F9" />
                <text
                  x={Math.max(4, threshX / 2 - 20)}
                  y={16}
                  fontSize={10}
                  fill="#64748B"
                  textAnchor="middle"
                >
                  {removed > 0 ? `Removing ${removed}` : ""}
                </text>
              </g>
            )}
            {/* Right badge - keeping */}
            {threshX < svgW - 60 && (
              <g>
                <rect x={threshX + 4} y={4} width={svgW - threshX - 6} height={18} rx={4}
                  fill="#DCFCE7" />
                <text
                  x={threshX + 4 + (svgW - threshX - 6) / 2}
                  y={16}
                  fontSize={10}
                  fill="#16A34A"
                  textAnchor="middle"
                >
                  Keeping {kept}
                </text>
              </g>
            )}
          </g>

          {/* Threshold handle */}
          <circle
            cx={threshX}
            cy={TOP_PAD + CHART_H}
            r={HANDLE_R}
            fill="#3B5FD9"
            stroke="#fff"
            strokeWidth={2}
            style={{ cursor: dragging ? "grabbing" : "grab", filter: "drop-shadow(0 1px 3px rgba(59,95,217,0.4))" }}
            onMouseDown={(e) => { e.preventDefault(); setDragging(true); }}
          />

          {/* X axis labels */}
          {[0, 0.25, 0.5, 0.75, 1].map((f) => (
            <text
              key={f}
              x={f * svgW}
              y={TOP_PAD + CHART_H + 16}
              fontSize={10}
              fill="#94A3B8"
              textAnchor="middle"
            >
              {pct(f)}
            </text>
          ))}
        </svg>
      </Box>

      {/* Active bucket filter pill */}
      {activeBucket && (
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 1 }}>
          <Chip
            size="small"
            label={`Filtered: ${pct(activeBucket.lo)} – ${pct(activeBucket.hi)}`}
            onDelete={() => { setActiveBucket(null); onBucketFilter?.(null); }}
            color="primary"
            variant="outlined"
            sx={{ fontSize: "0.72rem", height: 22 }}
          />
          <Typography variant="caption" color="text.secondary">
            Click the bar again or the x to clear
          </Typography>
        </Stack>
      )}

      {/* Legend */}
      <Stack direction="row" spacing={2} sx={{ mt: 1, flexWrap: "wrap" }}>
        {(["keyword", "hybrid", "semantic"] as const).map((t) => (
          <Stack key={t} direction="row" spacing={0.5} alignItems="center">
            <Box sx={{ width: 10, height: 10, borderRadius: 1, bgcolor: TYPE_COLOR[t] }} />
            <Typography variant="caption" color="text.secondary">{TYPE_LABEL[t]}</Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}
