/**
 * SyntheticTab -- synthetic gold list + coverage stats + generate controls.
 *
 * Extracted from GoldDatasetPanel as part of Wave E file-size refactoring.
 * Design Controls: DI-3035F221, DO-1E9BCC70.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Pagination from "@mui/material/Pagination";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SyncIcon from "@mui/icons-material/Sync";

import { FilterBar, SkeletonList } from "@leo/design-system";
import type { GoldLabel, SyntheticStats } from "./goldDatasetTypes";
import GoldLabelReviewList from "./GoldLabelReviewList";

export interface SyntheticTabProps {
  items: GoldLabel[];
  syntheticStats: SyntheticStats | null;
  total: number;
  listLoading: boolean;
  listError: string | null;
  onDismissError: () => void;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  search: string;
  debouncedSearch: string;
  onSearchChange: (value: string) => void;
  generatingSynthetic: boolean;
  purgingSynthetic: boolean;
  onOpenGenerate: () => void;
  onDeleteSet: () => void;
  resettingLabelId: string | null;
  onOpen: (item: GoldLabel) => void;
  onReset: (item: GoldLabel) => void;
}

function CoverageCard({
  syntheticStats,
  generatingSynthetic,
  purgingSynthetic,
  onOpenGenerate,
  onDeleteSet,
}: Pick<SyntheticTabProps, "syntheticStats" | "generatingSynthetic" | "purgingSynthetic" | "onOpenGenerate" | "onDeleteSet">) {
  if (!syntheticStats) return null;
  const pct =
    syntheticStats.total_surface_forms > 0
      ? (syntheticStats.covered_surface_forms / syntheticStats.total_surface_forms) * 100
      : 0;

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent sx={{ py: 1.5 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          alignItems={{ xs: "flex-start", sm: "center" }}
          justifyContent="space-between"
        >
          <Box sx={{ width: "100%" }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Surface-form coverage:{" "}
              {syntheticStats.covered_surface_forms.toLocaleString()} /{" "}
              {syntheticStats.total_surface_forms.toLocaleString()}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={pct}
              sx={{ mt: 1, height: 8, borderRadius: 1 }}
            />
            <Stack direction="row" spacing={0.75} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
              {syntheticStats.tag_breakdown.slice(0, 6).map((row) => (
                <Chip
                  key={row.semantic_tag}
                  size="small"
                  label={`${row.semantic_tag}: ${row.covered_surface_forms}`}
                  variant="outlined"
                />
              ))}
            </Stack>
          </Box>
          <Button
            variant="contained"
            color="secondary"
            startIcon={
              generatingSynthetic ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <SyncIcon />
              )
            }
            onClick={onOpenGenerate}
            disabled={generatingSynthetic}
            size="small"
          >
            Generate synthetic
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={
              purgingSynthetic ? (
                <CircularProgress size={14} color="inherit" />
              ) : (
                <DeleteOutlineIcon />
              )
            }
            onClick={onDeleteSet}
            disabled={purgingSynthetic}
            size="small"
          >
            Delete synthetic set
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}

function EmptyMessage({ search }: { search: string }) {
  return (
    <Box sx={{ py: 4, textAlign: "center" }}>
      <Typography color="text.secondary" variant="body2">
        {search
          ? `Nothing matches "${search}". Try different words.`
          : "No synthetic examples yet. Use the button above to create some."}
      </Typography>
    </Box>
  );
}

export function SyntheticTab({
  items,
  syntheticStats,
  total,
  listLoading,
  listError,
  onDismissError,
  page,
  totalPages,
  onPageChange,
  search,
  debouncedSearch,
  onSearchChange,
  generatingSynthetic,
  purgingSynthetic,
  onOpenGenerate,
  onDeleteSet,
  resettingLabelId,
  onOpen,
  onReset,
}: SyntheticTabProps) {
  return (
    <>
      <CoverageCard
        syntheticStats={syntheticStats}
        generatingSynthetic={generatingSynthetic}
        purgingSynthetic={purgingSynthetic}
        onOpenGenerate={onOpenGenerate}
        onDeleteSet={onDeleteSet}
      />

      <FilterBar
        search={search}
        onSearchChange={onSearchChange}
        searchPlaceholder="Search synthetic examples..."
        aria-label="Search synthetic gold labels"
      />

      {listError ? (
        <Alert severity="error" sx={{ mb: 1.25 }} onClose={onDismissError}>
          {listError}
        </Alert>
      ) : null}

      {listLoading ? (
        <SkeletonList />
      ) : items.length === 0 ? (
        <EmptyMessage search={debouncedSearch} />
      ) : (
        <>
          <GoldLabelReviewList
            items={items.filter((item) => item.label_id)}
            onOpen={onOpen}
            onReset={onReset}
            resettingLabelId={resettingLabelId}
            search={debouncedSearch}
          />
          {totalPages > 1 ? (
            <Stack alignItems="center" sx={{ mt: 2 }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(_, p) => onPageChange(p)}
                color="primary"
                size="small"
              />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                {total.toLocaleString()} total - page {page} of {totalPages}
              </Typography>
            </Stack>
          ) : null}
        </>
      )}
    </>
  );
}
