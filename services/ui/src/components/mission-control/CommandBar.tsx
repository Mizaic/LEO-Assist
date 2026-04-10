"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import { TAX_YEAR_PRESETS } from "@/lib/taxYearPresets";
import type { MissionControlFilters } from "@/lib/missionControlFilters";
import PathwayFilterChips from "./PathwayFilterChips";

interface Props {
  draft: MissionControlFilters;
  onChange: (patch: Partial<MissionControlFilters>, applyNow?: boolean) => void;
  onApply: () => void;
  onClear: () => void;
}

export default function CommandBar({ draft, onChange, onApply, onClear }: Props) {
  return (
    <Paper
      elevation={0}
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 2,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
      }}
    >
      {/* Row 1: Date range + year presets */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5, alignItems: "flex-end" }}>
        <TextField
          label="From"
          type="date"
          size="small"
          InputLabelProps={{ shrink: true }}
          value={draft.dateFrom}
          onChange={(e) => onChange({ dateFrom: e.target.value })}
          sx={{ width: 150 }}
        />
        <TextField
          label="To"
          type="date"
          size="small"
          InputLabelProps={{ shrink: true }}
          value={draft.dateTo}
          onChange={(e) => onChange({ dateTo: e.target.value })}
          sx={{ width: 150 }}
        />
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", alignItems: "center" }}>
          {TAX_YEAR_PRESETS.map((preset) => (
            <Chip
              key={preset.label}
              label={preset.label}
              size="small"
              variant={
                draft.dateFrom === preset.from && draft.dateTo === preset.to
                  ? "filled"
                  : "outlined"
              }
              color={
                draft.dateFrom === preset.from && draft.dateTo === preset.to
                  ? "primary"
                  : "default"
              }
              onClick={() => onChange({ dateFrom: preset.from, dateTo: preset.to })}
            />
          ))}
        </Box>
      </Box>

      <Divider />

      {/* Row 2: Pathway toggle + sub-filters + review status */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, alignItems: "flex-start" }}>
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            What are you looking for?
          </Typography>
          <ToggleButtonGroup
            value={draft.pathwayFilter}
            exclusive
            size="small"
            onChange={(_, v) => {
              if (!v) return;
              onChange({
                pathwayFilter: v,
                cancerTypes: [],
                closureReasons: [],
              }, true);
            }}
            sx={{ "& .MuiToggleButton-root": { textTransform: "none", fontSize: "0.75rem" } }}
          >
            <ToggleButton value="all">All pathways</ToggleButton>
            <ToggleButton value="confirmed">Confirmed cancer</ToggleButton>
            <ToggleButton value="closures">Pathway closures</ToggleButton>
          </ToggleButtonGroup>
        </Box>

        <PathwayFilterChips
          pathwayFilter={draft.pathwayFilter}
          cancerTypes={draft.cancerTypes}
          closureReasons={draft.closureReasons}
          onCancerTypesChange={(v) => onChange({ cancerTypes: v }, true)}
          onClosureReasonsChange={(v) => onChange({ closureReasons: v }, true)}
        />

        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            Review status
          </Typography>
          <ToggleButtonGroup
            value={draft.reviewStatus}
            exclusive
            size="small"
            onChange={(_, v) => {
              if (!v) return;
              onChange({ reviewStatus: v }, true);
            }}
            sx={{ "& .MuiToggleButton-root": { textTransform: "none", fontSize: "0.75rem" } }}
          >
            <ToggleButton value="all">All</ToggleButton>
            <ToggleButton value="unreviewed">Needs review</ToggleButton>
            <ToggleButton value="reviewed">Reviewed</ToggleButton>
          </ToggleButtonGroup>
        </Box>

        <Box sx={{ minWidth: 200, flex: "1 1 200px", maxWidth: 280 }}>
          <TextField
            size="small"
            fullWidth
            label="Patient ID"
            helperText="Exact match"
            value={draft.patientId}
            onChange={(e) => onChange({ patientId: e.target.value })}
            inputProps={{ maxLength: 64 }}
          />
        </Box>
      </Box>

      {/* Row 3: Actions */}
      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
        <Button size="small" onClick={onClear} color="inherit">
          Clear all
        </Button>
        <Button size="small" variant="contained" onClick={onApply} disableElevation>
          Go
        </Button>
      </Box>
    </Paper>
  );
}
