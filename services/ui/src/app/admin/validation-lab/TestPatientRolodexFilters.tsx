"use client";

/** Search and facet filters for the Validation Lab rolodex. */

import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import SearchIcon from "@mui/icons-material/Search";

export type ScenarioFilter = "all" | "generic" | "spo_ag" | "ras_referral";
export type TypeFilter = "all" | "referral" | "ag";
export type GoldFilter = "all" | "gold" | "no_gold";

interface Props {
  query: string;
  onQueryChange: (value: string) => void;
  scenarioFilter: ScenarioFilter;
  onScenarioFilterChange: (value: ScenarioFilter) => void;
  typeFilter: TypeFilter;
  onTypeFilterChange: (value: TypeFilter) => void;
  goldFilter: GoldFilter;
  onGoldFilterChange: (value: GoldFilter) => void;
  tagFilter: string;
  onTagFilterChange: (value: string) => void;
  tagOptions: string[];
}

export default function TestPatientRolodexFilters({
  query,
  onQueryChange,
  scenarioFilter,
  onScenarioFilterChange,
  typeFilter,
  onTypeFilterChange,
  goldFilter,
  onGoldFilterChange,
  tagFilter,
  onTagFilterChange,
  tagOptions,
}: Props) {
  return (
    <Stack spacing={1} sx={{ mb: 1.5 }}>
      <TextField
        size="small"
        fullWidth
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="Search by title, summary, tags, or patient"
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
        inputProps={{ "data-testid": "validation-lab-case-search" }}
      />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField
          select
          size="small"
          label="Scenario"
          value={scenarioFilter}
          onChange={(e) =>
            onScenarioFilterChange(e.target.value as ScenarioFilter)
          }
          sx={{ minWidth: 160 }}
          data-testid="validation-lab-filter-scenario"
        >
          <MenuItem value="all">All scenarios</MenuItem>
          <MenuItem value="generic">Generic</MenuItem>
          <MenuItem value="spo_ag">SPoA A&G</MenuItem>
          <MenuItem value="ras_referral">RAS referral</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label="Type"
          value={typeFilter}
          onChange={(e) => onTypeFilterChange(e.target.value as TypeFilter)}
          sx={{ minWidth: 140 }}
          data-testid="validation-lab-filter-type"
        >
          <MenuItem value="all">All types</MenuItem>
          <MenuItem value="referral">Referral</MenuItem>
          <MenuItem value="ag">A&G</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label="Gold"
          value={goldFilter}
          onChange={(e) => onGoldFilterChange(e.target.value as GoldFilter)}
          sx={{ minWidth: 140 }}
          data-testid="validation-lab-filter-gold"
        >
          <MenuItem value="all">All</MenuItem>
          <MenuItem value="gold">Has gold</MenuItem>
          <MenuItem value="no_gold">No gold</MenuItem>
        </TextField>
        <TextField
          select
          size="small"
          label="Tag"
          value={tagFilter}
          onChange={(e) => onTagFilterChange(e.target.value)}
          sx={{ minWidth: 160 }}
          data-testid="validation-lab-filter-tag"
        >
          <MenuItem value="">All tags</MenuItem>
          {tagOptions.map((tag) => (
            <MenuItem key={tag} value={tag}>
              {tag}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
    </Stack>
  );
}
