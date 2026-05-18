/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import Box from "@mui/material/Box";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import SearchIcon from "@mui/icons-material/Search";

export type RagFilter = "all" | "breached" | "at-risk" | "on-track";
export type ActionedFilter = "all" | "outstanding" | "actioned";

export interface WorklistFilterState {
  search: string;
  cancerSite: string;
  stage: string;
  rag: RagFilter;
  actioned: ActionedFilter;
}

interface WorklistFiltersProps {
  filters: WorklistFilterState;
  onChange: (next: WorklistFilterState) => void;
  cancerSites: string[];
  stages: string[];
}

export default function WorklistFilters({
  filters,
  onChange,
  cancerSites,
  stages,
}: WorklistFiltersProps) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, mb: 1.5 }}>
      <Box sx={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
        <TextField
          placeholder="Search patient ID or cancer site..."
          size="small"
          value={filters.search}
          onChange={(e) => onChange({ ...filters, search: e.target.value })}
          sx={{ width: 280 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ fontSize: 18, color: "text.secondary" }} />
                </InputAdornment>
              ),
            },
          }}
        />
        <TextField
          select
          size="small"
          label="Cancer Site"
          value={filters.cancerSite}
          onChange={(e) => onChange({ ...filters, cancerSite: e.target.value })}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="all">All Cancer Sites</MenuItem>
          {[...cancerSites].sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" })).map((site) => (
            <MenuItem key={site} value={site}>
              {site}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Pathway Stage"
          value={filters.stage}
          onChange={(e) => onChange({ ...filters, stage: e.target.value })}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="all">All Stages</MenuItem>
          {[...stages].sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" })).map((stage) => (
            <MenuItem key={stage} value={stage}>
              {stage}
            </MenuItem>
          ))}
        </TextField>
      </Box>

      <Box sx={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
        <ToggleButtonGroup
          value={filters.rag}
          exclusive
          onChange={(_e, val) => {
            if (val !== null) onChange({ ...filters, rag: val as RagFilter });
          }}
          size="small"
        >
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="at-risk">At Risk</ToggleButton>
          <ToggleButton value="on-track">On Track</ToggleButton>
          <ToggleButton value="breached">Overdue</ToggleButton>
        </ToggleButtonGroup>
        <ToggleButtonGroup
          value={filters.actioned}
          exclusive
          onChange={(_e, val) => {
            if (val !== null)
              onChange({ ...filters, actioned: val as ActionedFilter });
          }}
          size="small"
        >
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="actioned">Actioned</ToggleButton>
          <ToggleButton value="outstanding">Outstanding</ToggleButton>
        </ToggleButtonGroup>
      </Box>
    </Box>
  );
}
