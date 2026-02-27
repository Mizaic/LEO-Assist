"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import SearchIcon from "@mui/icons-material/Search";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import ListIcon from "@mui/icons-material/List";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

export type ViewMode = "grouped" | "flat";

export interface AlertFilterState {
  search: string;
  severity: string | null;
  type: string | null;
  actionedFilter: "all" | "outstanding" | "actioned";
}

const SEVERITY_COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
};

interface AlertFiltersProps {
  filters: AlertFilterState;
  onChange: (filters: AlertFilterState) => void;
  alerts: SafetyNetAlert[];
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}

export default function AlertFilters({
  filters,
  onChange,
  alerts,
  viewMode,
  onViewModeChange,
}: AlertFiltersProps) {
  const severityCounts = alerts.reduce<Record<string, number>>((acc, a) => {
    acc[a.severity] = (acc[a.severity] ?? 0) + 1;
    return acc;
  }, {});

  const typeCounts = alerts.reduce<Record<string, number>>((acc, a) => {
    acc[a.type] = (acc[a.type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
        <TextField
          placeholder="Search by patient, type, description..."
          value={filters.search}
          onChange={(e) => onChange({ ...filters, search: e.target.value })}
          size="small"
          sx={{ minWidth: 280, flex: 1, maxWidth: 420 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ fontSize: 20, color: "text.secondary" }} />
                </InputAdornment>
              ),
            },
          }}
        />
        <ToggleButtonGroup
          value={filters.actionedFilter}
          exclusive
          onChange={(_e, val) => {
            if (val !== null) onChange({ ...filters, actionedFilter: val });
          }}
          size="small"
        >
          <ToggleButton value="all">All</ToggleButton>
          <ToggleButton value="outstanding">Outstanding</ToggleButton>
          <ToggleButton value="actioned">Actioned</ToggleButton>
        </ToggleButtonGroup>

        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={(_e, val) => {
            if (val !== null) onViewModeChange(val);
          }}
          size="small"
          sx={{ ml: "auto" }}
        >
          <ToggleButton value="grouped" aria-label="group by patient">
            <Tooltip title="Group by patient">
              <PeopleOutlineIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
          <ToggleButton value="flat" aria-label="flat list">
            <Tooltip title="Flat list">
              <ListIcon fontSize="small" />
            </Tooltip>
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {["critical", "high", "medium", "low"].map((sev) => {
          const count = severityCounts[sev] ?? 0;
          if (count === 0) return null;
          const isActive = filters.severity === sev;
          return (
            <Chip
              key={sev}
              label={`${sev} (${count})`}
              size="small"
              color={SEVERITY_COLORS[sev] ?? "default"}
              variant={isActive ? "filled" : "outlined"}
              onClick={() =>
                onChange({ ...filters, severity: isActive ? null : sev })
              }
              sx={{ textTransform: "capitalize", cursor: "pointer" }}
            />
          );
        })}

        {Object.entries(typeCounts)
          .sort((a, b) => b[1] - a[1])
          .map(([type, count]) => {
            const isActive = filters.type === type;
            return (
              <Chip
                key={type}
                label={`${type} (${count})`}
                size="small"
                variant={isActive ? "filled" : "outlined"}
                onClick={() =>
                  onChange({ ...filters, type: isActive ? null : type })
                }
                sx={{ cursor: "pointer" }}
              />
            );
          })}
      </Box>
    </Box>
  );
}
