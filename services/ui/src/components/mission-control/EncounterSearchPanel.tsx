"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import InputAdornment from "@mui/material/InputAdornment";
import Paper from "@mui/material/Paper";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ScatterPlotIcon from "@mui/icons-material/ScatterPlot";
import SearchIcon from "@mui/icons-material/Search";
import TuneIcon from "@mui/icons-material/Tune";
import type { EncounterListItem, EncounterListResponse } from "@/lib/missionControlApi";

// Dedup similarity levels (index 0 = keep most variation, last = remove most aggressively)
// Covers sub-1% differences (0.999) down to ~20% differences (0.80)
const DEDUP_LEVELS = [0.999, 0.99, 0.95, 0.90, 0.85, 0.80] as const;
const DEDUP_LABELS = [
  "Almost identical (<0.1% different)",
  "Near-identical (<1% different)",
  "Very similar (<5% different)",
  "Quite similar (<10% different)",
  "Similar (<15% different)",
  "Broadly similar (<20% different)",
];

export interface EncounterSearchState {
  query: string;
  dateFrom: string;
  dateTo: string;
  selectedYears: number[];
  excludeNearDuplicates: boolean;
  nearDuplicateThreshold: string;
  minCombinedScore: string;
  minVectorScore: string;
  requireKeywordAnchor: boolean;
}

interface Props {
  state: EncounterSearchState;
  rows: EncounterListItem[];
  yearOptions: number[];
  queryDiagnostics: EncounterListResponse["query_diagnostics"];
  loading: boolean;
  hasRows: boolean;
  onQueryChange: (v: string) => void;
  onDateFromChange: (v: string) => void;
  onDateToChange: (v: string) => void;
  onToggleYear: (year: number) => void;
  onMinScoreChange: (v: string) => void;
  onMinVectorScoreChange: (v: string) => void;
  onRequireKeywordAnchorChange: (v: boolean) => void;
  onExcludeNearDuplicatesChange: (v: boolean) => void;
  onNearDuplicateThresholdChange: (v: string) => void;
  onSearch: () => void;
  onShow3D: () => void;
}

function dedupIndexFromThreshold(threshold: string): number {
  const n = Number(threshold);
  const idx = DEDUP_LEVELS.findIndex((v) => v === n);
  return idx >= 0 ? idx : 2;
}

const TYPE_COLOR: Record<string, string> = {
  keyword: "#4F46E5",
  hybrid: "#7C3AED",
  semantic: "#0891B2",
  none: "#94A3B8",
};

// -- SliderRow ---------------------------------------------------------------

interface SliderRowProps {
  label: string;
  tooltip: string;
  value: number; // 0-100
  onChange: (v: number) => void;
}

function SliderRow({ label, tooltip, value, onChange }: SliderRowProps) {
  const active = value > 0;
  return (
    <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 0.75 }}>
      <Tooltip title={tooltip} arrow placement="top">
        <Typography
          variant="caption"
          sx={{
            minWidth: 130,
            fontWeight: active ? 600 : 400,
            color: active ? "text.primary" : "text.secondary",
            cursor: "default",
            userSelect: "none",
          }}
        >
          {label}
        </Typography>
      </Tooltip>
      <Slider
        size="small"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={(_, v) => onChange(Array.isArray(v) ? v[0] : v)}
        sx={{
          flex: 1,
          "& .MuiSlider-track": { height: 5, borderRadius: 3 },
          "& .MuiSlider-rail": { height: 5, opacity: 0.18 },
          "& .MuiSlider-thumb": { width: 17, height: 17 },
        }}
      />
      <Chip
        size="small"
        label={active ? `${value}%+` : "off"}
        color={active ? "primary" : "default"}
        variant={active ? "filled" : "outlined"}
        sx={{ minWidth: 50, fontWeight: 700, fontSize: "0.68rem", pointerEvents: "none" }}
      />
    </Stack>
  );
}

// -- ToggleCard ---------------------------------------------------------------

interface ToggleCardProps {
  title: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  ariaLabel: string;
  children?: ReactNode;
}

function ToggleCard({ title, description, checked, onChange, ariaLabel, children }: ToggleCardProps) {
  return (
    <Paper
      elevation={0}
      sx={{
        flex: 1,
        p: 1.25,
        border: "1.5px solid",
        borderColor: checked ? "primary.main" : "divider",
        borderRadius: 1.5,
        bgcolor: checked ? "rgba(31,58,138,0.04)" : "transparent",
        transition: "border-color 0.15s, background-color 0.15s",
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
        <Box>
          <Typography
            variant="caption"
            sx={{ fontWeight: 700, color: checked ? "primary.main" : "text.primary", transition: "color 0.15s" }}
          >
            {title}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
            {description}
          </Typography>
        </Box>
        <Switch
          size="small"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          inputProps={{ "aria-label": ariaLabel }}
        />
      </Stack>
      {children}
    </Paper>
  );
}

// -- ThresholdMap2D ----------------------------------------------------------

interface ThresholdMap2DProps {
  xPercent: number;
  yPercent: number;
  rows: EncounterListItem[];
  onChange: (nextX: number, nextY: number) => void;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

const MAP_H = 180;

// LONG FUNCTION: complex interactive SVG component with drag, resize, and data rendering
function ThresholdMap2D({ xPercent, yPercent, rows, onChange }: ThresholdMap2DProps) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [svgW, setSvgW] = useState(600);

  useEffect(() => {
    const el = mapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setSvgW(el.getBoundingClientRect().width));
    ro.observe(el);
    setSvgW(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);

  const updateFromPointer = useCallback((clientX: number, clientY: number) => {
    const rect = mapRef.current?.getBoundingClientRect();
    if (!rect) return;
    const nextX = clamp(((clientX - rect.left) / rect.width) * 100, 0, 100);
    const nextY = clamp(100 - ((clientY - rect.top) / rect.height) * 100, 0, 100);
    onChange(Math.round(nextX / 5) * 5, Math.round(nextY / 5) * 5);
  }, [onChange]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => updateFromPointer(e.clientX, e.clientY);
    const onUp = () => setDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragging, updateFromPointer]);

  const threshX = (xPercent / 100) * svgW;
  const threshY = (1 - yPercent / 100) * MAP_H;

  const { dots, keptCount } = useMemo(() => {
    const cap = rows.slice(0, 500);
    let kept = 0;
    const d = cap.map((r) => {
      const rx = r.rank_features?.fulltext_norm ?? r.score ?? 0;
      const ry = r.rank_features?.vector_norm ?? r.vector_score ?? 0;
      const isKept = rx >= xPercent / 100 && (yPercent === 0 || ry >= yPercent / 100);
      if (isKept) kept++;
      return {
        x: rx * svgW,
        y: (1 - ry) * MAP_H,
        fill: isKept ? (TYPE_COLOR[r.match_type ?? "none"] ?? "#94A3B8") : "#CBD5E1",
      };
    });
    return { dots: d, keptCount: kept };
  }, [rows, svgW, xPercent, yPercent]);

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
        <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
          Score map
        </Typography>
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 500 }}>
            {keptCount} of {Math.min(rows.length, 500)} kept
          </Typography>
          <Chip size="small" label="2D view" variant="outlined" sx={{ fontSize: "0.63rem", height: 18 }} />
        </Stack>
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75, fontSize: "0.72rem" }}>
        Drag the intersection point to set thresholds. Coloured dots stay; grey dots are removed.
      </Typography>

      {/* Map with Y-axis label column */}
      <Stack direction="row" spacing={0.5} alignItems="stretch">
        <Box sx={{ width: 16, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <Typography
            variant="caption"
            color="text.disabled"
            sx={{ fontSize: "0.58rem", transform: "rotate(-90deg)", whiteSpace: "nowrap", letterSpacing: "0.06em" }}
          >
            MEANING
          </Typography>
        </Box>
        <Box
          ref={mapRef}
          sx={{
            flex: 1, position: "relative", borderRadius: 1.5,
            border: "1px solid", borderColor: "divider",
            overflow: "hidden", bgcolor: "#F8FAFC",
            cursor: dragging ? "grabbing" : "crosshair",
            boxShadow: "inset 0 1px 3px rgba(0,0,0,0.04)",
          }}
          onMouseDown={(e) => { setDragging(true); updateFromPointer(e.clientX, e.clientY); }}
          role="slider"
          aria-label="Score threshold map"
        >
          <svg width="100%" height={MAP_H} style={{ display: "block" }}>
            <rect x={0} y={0} width={threshX} height={MAP_H} fill="rgba(239,68,68,0.06)" />
            <rect x={threshX} y={threshY} width={Math.max(0, svgW - threshX)} height={Math.max(0, MAP_H - threshY)} fill="rgba(34,197,94,0.09)" />
            {[0.25, 0.5, 0.75].map((f) => (
              <g key={f}>
                <line x1={f * svgW} y1={0} x2={f * svgW} y2={MAP_H} stroke="#E2E8F0" strokeWidth={1} />
                <line x1={0} y1={f * MAP_H} x2={svgW} y2={f * MAP_H} stroke="#E2E8F0" strokeWidth={1} />
              </g>
            ))}
            {dots.map((d, i) => (
              <circle key={i} cx={d.x} cy={d.y} r={3.5} fill={d.fill} fillOpacity={0.82} />
            ))}
            <line x1={threshX} y1={0} x2={threshX} y2={MAP_H} stroke="#1F3A8A" strokeWidth={1.5} strokeDasharray="4 3" />
            <line x1={0} y1={threshY} x2={svgW} y2={threshY} stroke="#1F3A8A" strokeWidth={1.5} strokeDasharray="4 3" />
            <circle cx={threshX} cy={threshY} r={9} fill="#1F3A8A" stroke="#fff" strokeWidth={2.5}
              style={{ cursor: dragging ? "grabbing" : "grab", filter: "drop-shadow(0 1px 3px rgba(31,58,138,0.4))" }} />
            <circle cx={threshX} cy={threshY} r={3} fill="#fff" />
            <text x={4} y={MAP_H - 4} fontSize={9} fill="#CBD5E1">0%</text>
            <text x={svgW - 30} y={MAP_H - 4} fontSize={9} fill="#CBD5E1">100%</text>
          </svg>
        </Box>
      </Stack>

      {/* X-axis label */}
      <Stack direction="row" justifyContent="space-between" sx={{ mt: 0.4, pl: "22px" }}>
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem" }}>Loose</Typography>
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem" }}>Keyword match --&gt;</Typography>
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem" }}>Strict</Typography>
      </Stack>

      {/* Dot legend */}
      <Stack direction="row" spacing={1.25} sx={{ mt: 0.75, pl: "22px", flexWrap: "wrap" }} useFlexGap>
        {(["keyword", "hybrid", "semantic"] as const).map((type) => (
          <Stack key={type} direction="row" spacing={0.4} alignItems="center">
            <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: TYPE_COLOR[type], flexShrink: 0 }} />
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem", textTransform: "capitalize" }}>
              {type}
            </Typography>
          </Stack>
        ))}
        <Stack direction="row" spacing={0.4} alignItems="center">
          <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "#CBD5E1", flexShrink: 0 }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem" }}>Below threshold</Typography>
        </Stack>
      </Stack>
    </Box>
  );
}

export default function EncounterSearchPanel({
  state,
  rows,
  yearOptions,
  queryDiagnostics,
  loading,
  hasRows,
  onQueryChange,
  onDateFromChange,
  onDateToChange,
  onToggleYear,
  onMinScoreChange,
  onMinVectorScoreChange,
  onRequireKeywordAnchorChange,
  onExcludeNearDuplicatesChange,
  onNearDuplicateThresholdChange,
  onSearch,
  onShow3D,
}: Props) {
  const minScore = Math.round(Number(state.minCombinedScore) * 100) || 0;
  const minVectorScore = Math.round(Number(state.minVectorScore) * 100) || 0;

  // Stable callback for ThresholdMap2D — must not change identity on every
  // render, otherwise updateFromPointer re-memoizes, the dragging effect
  // re-registers onMove mid-drag, and a setState loop ensues.
  const handleMapChange = useCallback((nextX: number, nextY: number) => {
    onMinScoreChange((nextX / 100).toFixed(2));
    onMinVectorScoreChange(nextY > 0 ? (nextY / 100).toFixed(2) : "");
  }, [onMinScoreChange, onMinVectorScoreChange]);
  const dedupIdx = dedupIndexFromThreshold(state.nearDuplicateThreshold);
  const dedupLabel = DEDUP_LABELS[dedupIdx] ?? "Balanced";

  return (
    <Box>
      {/* -- Row 1: search + dates + search button ----------------------------- */}
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flexWrap: "wrap" }} useFlexGap>
        <TextField
          label="Search encounters"
          placeholder="e.g. fast track, chest pain, breathlessness..."
          value={state.query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSearch(); }}
          size="small"
          sx={{ flex: 1, minWidth: 260 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
              </InputAdornment>
            ),
          }}
        />
        <TextField
          label="From"
          type="date"
          value={state.dateFrom}
          onChange={(e) => onDateFromChange(e.target.value)}
          size="small"
          sx={{ width: 160 }}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          label="To"
          type="date"
          value={state.dateTo}
          onChange={(e) => onDateToChange(e.target.value)}
          size="small"
          sx={{ width: 160 }}
          InputLabelProps={{ shrink: true }}
        />
        <Button
          variant="contained"
          onClick={onSearch}
          disabled={loading}
          sx={{ minWidth: 90, height: 40 }}
        >
          Search
        </Button>
      </Stack>

      {/* -- Row 2: year chips ------------------------------------------------ */}
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mt: 1.5, flexWrap: "wrap" }} useFlexGap>
        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>Year:</Typography>
        {yearOptions.map((year) => (
          <Chip
            key={year}
            label={String(year)}
            clickable
            size="small"
            color={state.selectedYears.includes(year) ? "primary" : "default"}
            variant={state.selectedYears.includes(year) ? "filled" : "outlined"}
            onClick={() => onToggleYear(year)}
          />
        ))}
      </Stack>

      {/* -- Row 3: filter options + map -------------------------------------- */}
      <Paper
        elevation={0}
        sx={{ mt: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 2, overflow: "hidden" }}
      >
        {/* Header bar */}
        <Stack
          direction="row"
          alignItems="center"
          spacing={0.75}
          sx={{ px: 1.5, py: 0.9, borderBottom: "1px solid", borderColor: "divider", bgcolor: "#F8FAFC" }}
        >
          <TuneIcon sx={{ fontSize: 14, color: "primary.main" }} />
          <Typography variant="caption" sx={{ color: "primary.main", fontWeight: 700, letterSpacing: "0.04em", flex: 1 }}>
            Filter options
          </Typography>
          {hasRows && (
            <Tooltip title="See all notes plotted in 3D by word match, meaning match, and uniqueness." arrow>
              <Chip
                size="small"
                label="Show 3D map"
                icon={<ScatterPlotIcon sx={{ fontSize: "13px !important" }} />}
                onClick={onShow3D}
                variant="outlined"
                color="primary"
                sx={{ fontWeight: 600, fontSize: "0.7rem" }}
              />
            </Tooltip>
          )}
        </Stack>

        {/* Sliders */}
        <Box sx={{ px: 1.5, pt: 1.25, pb: 0.5 }}>
          <SliderRow
            label="Keyword match (X)"
            tooltip="Remove notes below this keyword match score."
            value={minScore}
            onChange={(v) => onMinScoreChange((v / 100).toFixed(2))}
          />
          <SliderRow
            label="Meaning match (Y)"
            tooltip="Remove notes below this semantic meaning score. Zero turns it off."
            value={minVectorScore}
            onChange={(v) => onMinVectorScoreChange(v > 0 ? (v / 100).toFixed(2) : "")}
          />
        </Box>

        {/* Score map */}
        <Box sx={{ px: 1.5, pb: 1.25 }}>
          <ThresholdMap2D
            xPercent={minScore}
            yPercent={minVectorScore}
            rows={rows}
            onChange={handleMapChange}
          />
        </Box>

        {/* Toggle cards */}
        <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ px: 1.25, pb: 1.25 }}>
          <ToggleCard
            title="Must include your search words"
            description="Turn on to remove meaning-only matches."
            checked={state.requireKeywordAnchor}
            onChange={onRequireKeywordAnchorChange}
            ariaLabel="Must include your search words"
          />
          <ToggleCard
            title="Remove repeated entries"
            description="Hide near-identical notes so you do not review duplicates."
            checked={state.excludeNearDuplicates}
            onChange={onExcludeNearDuplicatesChange}
            ariaLabel="Remove repeated entries"
          >
            {state.excludeNearDuplicates && (
              <Box sx={{ mt: 1 }}>
                <Slider
                  size="small"
                  min={0}
                  max={DEDUP_LEVELS.length - 1}
                  step={1}
                  marks
                  value={dedupIdx}
                  onChange={(_, v) => {
                    const idx = Array.isArray(v) ? v[0] : v;
                    onNearDuplicateThresholdChange(String(DEDUP_LEVELS[idx] ?? 0.90));
                  }}
                  sx={{ py: 0.5 }}
                />
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="caption" color="text.disabled">Keep more variety</Typography>
                  <Typography variant="caption" color="primary.main" fontWeight={600}>{dedupLabel}</Typography>
                  <Typography variant="caption" color="text.disabled">Remove more</Typography>
                </Stack>
              </Box>
            )}
          </ToggleCard>
        </Stack>
      </Paper>

      {/* -- Row 4: search diagnostics ---------------------------------------- */}
      {queryDiagnostics && (
        <Stack direction="row" spacing={0.75} sx={{ mt: 1.5, flexWrap: "wrap" }} useFlexGap alignItems="center">
          <Typography variant="caption" color="text.secondary">Searched for:</Typography>
          <Chip
            size="small"
            label={queryDiagnostics.rewrite_applied
              ? queryDiagnostics.rewritten_query
              : queryDiagnostics.original_query}
            color={queryDiagnostics.rewrite_applied ? "info" : "default"}
            variant={queryDiagnostics.rewrite_applied ? "filled" : "outlined"}
          />
          {queryDiagnostics.rewrite_applied && (
            <Tooltip title={`Your search was expanded from "${queryDiagnostics.original_query}" to improve results.`}>
              <Chip size="small" label="Auto-expanded" variant="outlined" color="info" />
            </Tooltip>
          )}
          {(queryDiagnostics.relevance_filtered_count ?? 0) > 0 && (
            <Chip
              size="small"
              variant="outlined"
              label={`${(queryDiagnostics.relevance_filtered_count ?? 0).toLocaleString()} low-quality results removed`}
            />
          )}
          {(queryDiagnostics.near_duplicate_filtered_count ?? 0) > 0 && (
            <Chip
              size="small"
              color="info"
              variant="outlined"
              label={`${queryDiagnostics.near_duplicate_filtered_count} repeated notes removed`}
            />
          )}
        </Stack>
      )}
    </Box>
  );
}
