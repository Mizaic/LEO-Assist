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
 * (Phase 4b decomposition). Redesigned Wave E: FilterBar + SegmentedTabs
 * replace FormControl Selects; ReviewListCard rows replace raw ExampleCard list.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";

import {
  EmptyState,
  FilterBar,
  ReviewListCard,
  SegmentedTabs,
  type FilterChip,
  type ReviewListItem,
} from "@leo/design-system";

import { ExampleCard } from "./ExampleCard";
import {
  CATEGORY_OPTIONS,
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
  const [filterSearch, setFilterSearch] = useState("");

  const catTabs = useMemo(() => {
    const top = Object.entries(catCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([cat, count]) => ({
        id: cat,
        label: categoryLabel(cat),
        count,
      }));
    return [{ id: "", label: "All", count: examples.length }, ...top];
  }, [catCounts, examples.length]);

  const scopeChips = useMemo<FilterChip[]>(
    () => [
      {
        id: "aws",
        label: "AWS",
        active: filterScope === "aws",
        onToggle: () => onFilterScope(filterScope === "aws" ? "" : "aws"),
      },
      {
        id: "azure",
        label: "Azure",
        active: filterScope === "azure",
        onToggle: () => onFilterScope(filterScope === "azure" ? "" : "azure"),
      },
    ],
    [filterScope, onFilterScope],
  );

  const visibleExamples = useMemo(() => {
    if (!filterSearch.trim()) return filteredExamples;
    const q = filterSearch.toLowerCase();
    return filteredExamples.filter(
      (ex) =>
        ex.input.toLowerCase().includes(q) ||
        ex.output.toLowerCase().includes(q) ||
        ex.description.toLowerCase().includes(q),
    );
  }, [filteredExamples, filterSearch]);

  return (
    <Box sx={{ pt: 2 }}>
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, mb: 1.5 }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ xs: "flex-start", md: "center" }}>
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
              sx={{ width: 210 }}
            />
            <Tooltip title="Caps total examples used at runtime, including core examples.">
              <InfoOutlinedIcon sx={{ fontSize: 16, color: "text.disabled" }} />
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

      <FilterBar
        search={filterSearch}
        onSearchChange={setFilterSearch}
        searchPlaceholder="Search examples..."
        aria-label="Teaching examples filter"
        chips={scopeChips}
        trailing={
          <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={onAdd}>
            Add example
          </Button>
        }
      />

      <Box sx={{ mt: 1.5, mb: 1.5 }}>
        <SegmentedTabs
          tabs={catTabs}
          value={filterCat}
          onChange={onFilterCat}
          aria-label="Category filter"
          dense
        />
      </Box>

      <Divider sx={{ mb: 2 }} />

      {visibleExamples.length === 0 ? (
        <EmptyState
          icon={<SchoolOutlinedIcon />}
          title="No teaching examples yet"
          body="Teaching examples help LEO learn patterns. Add one to improve coding accuracy."
          cta={
            examples.length === 0
              ? { label: "Add first example", onClick: onAdd, icon: <AddIcon /> }
              : undefined
          }
          data-testid="examples-empty-state"
        />
      ) : (
        <ExampleRows
          examples={visibleExamples}
          onUpdate={onUpdate}
          onRemove={onRemove}
        />
      )}
    </Box>
  );
}

function ExampleRows({
  examples,
  onUpdate,
  onRemove,
}: {
  examples: FewShotExample[];
  onUpdate: TeachingExamplesTabProps["onUpdate"];
  onRemove: TeachingExamplesTabProps["onRemove"];
}) {
  const [expandedId, setExpandedId] = useState<string | null>(() => {
    const newEx = examples.find((ex) => !ex.input && !ex.output);
    return newEx?.id ?? null;
  });

  return (
    <Stack spacing={1.5}>
      {examples.map((ex, idx) =>
        expandedId === ex.id ? (
          <ExampleCard
            key={ex.id}
            ex={ex}
            idx={idx}
            onChange={onUpdate}
            onRemove={(id) => {
              onRemove(id);
              setExpandedId(null);
            }}
            startInEdit
          />
        ) : (
          <ExampleRow
            key={ex.id}
            ex={ex}
            onExpand={() => setExpandedId(ex.id)}
            onRemove={onRemove}
          />
        ),
      )}
    </Stack>
  );
}

function ExampleRow({
  ex,
  onExpand,
  onRemove,
}: {
  ex: FewShotExample;
  onExpand: () => void;
  onRemove: (id: string) => void;
}) {
  const catLabel = ex.category
    ? CATEGORY_OPTIONS.find((o) => o.value === ex.category)?.label
    : undefined;

  const item: ReviewListItem = {
    id: ex.id,
    title: ex.input
      ? ex.input.slice(0, 120) + (ex.input.length > 120 ? "..." : "")
      : "New example -- click edit to fill in",
    meta: catLabel,
    chips: (
      <>
        {ex.core && (
          <Chip size="small" label="Core" color="success" sx={{ height: 18, fontSize: "0.65rem" }} />
        )}
        {!ex.deidentified && ex.input && (
          <Chip size="small" label="Check for patient data" color="warning" sx={{ height: 18, fontSize: "0.62rem" }} />
        )}
      </>
    ),
    actions: (
      <>
        <Tooltip title="Edit this example">
          <IconButton size="small" aria-label="Edit example" onClick={onExpand}>
            <EditIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Remove this example">
          <IconButton
            size="small"
            aria-label="Remove example"
            onClick={() => onRemove(ex.id)}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </>
    ),
  };

  return <ReviewListCard items={[item]} />;
}
