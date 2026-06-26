/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Tab 2 -- few-shot examples library. Extracted from prompts/[id]/page.tsx
 * (Phase 4b decomposition).
 */

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import FilterListIcon from "@mui/icons-material/FilterList";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { ExampleCard } from "./ExampleCard";
import {
  CATEGORY_OPTIONS,
  SCOPE_OPTIONS,
  categoryColor,
  categoryLabel,
  type FewShotExample,
} from "./types";

interface TeachingExamplesTabProps {
  examples: FewShotExample[];
  filteredExamples: FewShotExample[];
  filterCat: string;
  filterScope: string;
  maxFewShot: number;
  catCounts: Record<string, number>;
  onFilterCat: (next: string) => void;
  onFilterScope: (next: string) => void;
  onMaxFewShot: (next: number) => void;
  onAdd: () => void;
  onUpdate: (
    id: string,
    field: keyof FewShotExample,
    value: string | boolean,
  ) => void;
  onRemove: (id: string) => void;
}

export function TeachingExamplesTab({
  examples,
  filteredExamples,
  filterCat,
  filterScope,
  maxFewShot,
  catCounts,
  onFilterCat,
  onFilterScope,
  onMaxFewShot,
  onAdd,
  onUpdate,
  onRemove,
}: TeachingExamplesTabProps) {
  return (
    <Box sx={{ pt: 2 }}>
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, mb: 1.5 }}>
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={1.5}
          alignItems={{ xs: "flex-start", md: "center" }}
        >
          <Stack direction="row" spacing={0.75} alignItems="center">
            <TextField
              size="small"
              type="number"
              label="Max examples used at runtime"
              value={maxFewShot}
              onChange={(e) => {
                const parsed = Number(e.target.value);
                if (Number.isNaN(parsed)) return;
                onMaxFewShot(Math.min(100, Math.max(1, parsed)));
              }}
              inputProps={{ min: 1, max: 100 }}
              sx={{ width: 220 }}
            />
            <Tooltip title="Caps total examples used at runtime, including core examples.">
              <InfoOutlinedIcon
                sx={{ fontSize: 16, color: "text.disabled" }}
              />
            </Tooltip>
          </Stack>
          <Chip
            size="small"
            label="RAG selection: On when embedder available"
            variant="outlined"
            color="info"
          />
        </Stack>
      </Paper>

      <ToolbarRow
        filterCat={filterCat}
        filterScope={filterScope}
        catCounts={catCounts}
        filteredCount={filteredExamples.length}
        totalCount={examples.length}
        onFilterCat={onFilterCat}
        onFilterScope={onFilterScope}
        onAdd={onAdd}
      />

      {examples.length > 0 && (
        <Stack
          direction="row"
          spacing={0.5}
          flexWrap="wrap"
          useFlexGap
          sx={{ mb: 2 }}
        >
          {Object.entries(catCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([cat, count]) => (
              <Chip
                key={cat}
                size="small"
                label={`${categoryLabel(cat)} ${count}`}
                color={categoryColor(cat)}
                variant={filterCat === cat ? "filled" : "outlined"}
                onClick={() => onFilterCat(filterCat === cat ? "" : cat)}
                sx={{ cursor: "pointer", fontSize: "0.68rem", height: 22 }}
              />
            ))}
        </Stack>
      )}

      <Divider sx={{ mb: 2 }} />

      {filteredExamples.length === 0 ? (
        <EmptyState
          totalCount={examples.length}
          onAdd={onAdd}
        />
      ) : (
        filteredExamples.map((ex, idx) => (
          <ExampleCard
            key={ex.id}
            ex={ex}
            idx={idx}
            onChange={onUpdate}
            onRemove={onRemove}
            startInEdit={!ex.input && !ex.output}
          />
        ))
      )}
    </Box>
  );
}

function ToolbarRow({
  filterCat,
  filterScope,
  catCounts,
  filteredCount,
  totalCount,
  onFilterCat,
  onFilterScope,
  onAdd,
}: {
  filterCat: string;
  filterScope: string;
  catCounts: Record<string, number>;
  filteredCount: number;
  totalCount: number;
  onFilterCat: (next: string) => void;
  onFilterScope: (next: string) => void;
  onAdd: () => void;
}) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={1}
      alignItems="center"
      sx={{ mb: 2 }}
    >
      <Stack direction="row" spacing={0.5} alignItems="center">
        <FilterListIcon sx={{ fontSize: 18, color: "text.disabled" }} />
        <Typography variant="caption" color="text.secondary">
          Filter:
        </Typography>
      </Stack>
      <FormControl size="small" sx={{ minWidth: 210 }}>
        <InputLabel>Category</InputLabel>
        <Select
          label="Category"
          value={filterCat}
          onChange={(e) => onFilterCat(e.target.value)}
        >
          {CATEGORY_OPTIONS.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ width: "100%" }}
              >
                <span>{o.label}</span>
                {o.value && catCounts[o.value] !== undefined && (
                  <Chip
                    size="small"
                    label={catCounts[o.value]}
                    sx={{ height: 16, fontSize: "0.65rem", ml: 1 }}
                  />
                )}
              </Stack>
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <FormControl size="small" sx={{ minWidth: 160 }}>
        <InputLabel>Provider</InputLabel>
        <Select
          label="Provider"
          value={filterScope}
          onChange={(e) => onFilterScope(e.target.value)}
        >
          <MenuItem value="">All providers</MenuItem>
          {SCOPE_OPTIONS.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <Box sx={{ flex: 1 }} />
      <Typography variant="caption" color="text.secondary">
        {filteredCount} of {totalCount} shown
      </Typography>
      <Button
        size="small"
        variant="contained"
        startIcon={<AddIcon />}
        onClick={onAdd}
      >
        Add example
      </Button>
    </Stack>
  );
}

function EmptyState({
  totalCount,
  onAdd,
}: {
  totalCount: number;
  onAdd: () => void;
}) {
  return (
    <Box
      sx={{
        textAlign: "center",
        py: 5,
        border: "1px dashed",
        borderColor: "divider",
        borderRadius: 2,
      }}
    >
      <Typography variant="body2" color="text.secondary" gutterBottom>
        {totalCount === 0
          ? "No examples yet. Add one to help the AI understand what you expect."
          : "No examples match the current filter."}
      </Typography>
      {totalCount === 0 && (
        <Button
          size="small"
          startIcon={<AddIcon />}
          onClick={onAdd}
          sx={{ mt: 1 }}
        >
          Add first example
        </Button>
      )}
    </Box>
  );
}
