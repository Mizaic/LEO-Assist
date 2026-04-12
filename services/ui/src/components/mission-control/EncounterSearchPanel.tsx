"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import InputAdornment from "@mui/material/InputAdornment";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import SearchIcon from "@mui/icons-material/Search";
import type { EncounterListResponse } from "@/lib/missionControlApi";

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
  yearOptions: number[];
  queryDiagnostics: EncounterListResponse["query_diagnostics"];
  loading: boolean;
  onQueryChange: (v: string) => void;
  onDateFromChange: (v: string) => void;
  onDateToChange: (v: string) => void;
  onToggleYear: (year: number) => void;
  onSearch: () => void;
}

export default function EncounterSearchPanel({
  state,
  yearOptions,
  queryDiagnostics,
  loading,
  onQueryChange,
  onDateFromChange,
  onDateToChange,
  onToggleYear,
  onSearch,
}: Props) {
  return (
    <Box>
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
              label={`${queryDiagnostics.near_duplicate_filtered_count} repeated entries removed`}
            />
          )}
        </Stack>
      )}
    </Box>
  );
}
