/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

import { type ReactNode, useCallback, useMemo } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Paper from "@mui/material/Paper";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ScatterPlotIcon from "@mui/icons-material/ScatterPlot";
import SearchIcon from "@mui/icons-material/Search";
import TuneIcon from "@mui/icons-material/Tune";
import type { EncounterListItem, EncounterListResponse } from "@/lib/missionControlApi";
import ScoreHistogram, { type BucketFilter } from "./ScoreHistogram";

// Dedup similarity levels (index 0 = keep most variation, last = remove most aggressively)
// Covers sub-1% differences (0.999) down to ~20% differences (0.80)
const DEDUP_LEVELS = [0.999, 0.99, 0.95, 0.90, 0.85, 0.80] as const;
// Labels describe what gets hidden, not the raw similarity score.
// The final two positions are flagged as aggressive to warn reviewers.
const DEDUP_LABELS = [
  "Exact copies only — safest",
  "Near-exact copies (tiny edits)",
  "Same template, different patient details",
  "Same structure, some variation — use with care",
  "Similar notes — may hide distinct encounters",
  "Aggressive — high risk of missing relevant notes",
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
  onBucketFilter?: (filter: BucketFilter | null) => void;
  onNearDuplicateThresholdCommit?: () => void;
}

function dedupIndexFromThreshold(threshold: string): number {
  const n = Number(threshold);
  const idx = DEDUP_LEVELS.findIndex((v) => v === n);
  return idx >= 0 ? idx : 2;
}

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
  onBucketFilter,
  onNearDuplicateThresholdCommit,
}: Props) {
  const minScore = Math.round(Number(state.minCombinedScore) * 100) || 0;
  const minVectorScore = Math.round(Number(state.minVectorScore) * 100) || 0;

  const handleThresholdChange = useCallback((score: number) => {
    onMinScoreChange(score.toFixed(2));
  }, [onMinScoreChange]);
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
            endAdornment: state.query ? (
              <InputAdornment position="end">
                <IconButton
                  size="small"
                  edge="end"
                  aria-label="Clear search"
                  data-testid="encounter-search-clear"
                  onClick={() => onQueryChange("")}
                >
                  <CloseIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </InputAdornment>
            ) : undefined,
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

        {/* Score histogram */}
        <Box sx={{ px: 1.5, pb: 1.25 }}>
          <ScoreHistogram
            rows={rows}
            minCombinedScore={minScore / 100}
            onThresholdChange={handleThresholdChange}
            onBucketFilter={onBucketFilter}
            onShow3D={hasRows ? onShow3D : undefined}
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
                  onChangeCommitted={() => onNearDuplicateThresholdCommit?.()}
                  sx={{ py: 0.5 }}
                />
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="caption" color="text.disabled">Keep more variety</Typography>
                  <Typography
                    variant="caption"
                    fontWeight={600}
                    color={dedupIdx >= 4 ? "error.main" : dedupIdx === 3 ? "warning.main" : "primary.main"}
                  >
                    {dedupLabel}
                  </Typography>
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
