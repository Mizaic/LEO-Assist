/**
 * GoldTab -- verified gold list + dataset health panel.
 *
 * Extracted from GoldDatasetPanel as part of Wave E file-size refactoring.
 * Design Controls: DI-2D9F5064, DO-1E9BCC70.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Pagination from "@mui/material/Pagination";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { FilterBar, SkeletonList } from "@leo/design-system";
import type { GoldLabel } from "./goldDatasetTypes";
import DatasetHealthPanel from "./DatasetHealthPanel";
import GoldLabelReviewList from "./GoldLabelReviewList";

export interface GoldTabProps {
  items: GoldLabel[];
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
  resettingLabelId: string | null;
  healthRefreshKey: number;
  entityLabelFilter: string | null;
  onLabelFilter: (label: string | null) => void;
  onOpen: (item: GoldLabel) => void;
  onReset: (item: GoldLabel) => void;
  onOpenLabel: (labelId: string) => void;
}

function EmptyMessage({ search }: { search: string }) {
  return (
    <Box sx={{ py: 4, textAlign: "center" }}>
      <Typography color="text.secondary" variant="body2">
        {search
          ? `Nothing matches "${search}". Try different words.`
          : "No verified examples yet. Mark sentences as gold and they will show up here."}
      </Typography>
    </Box>
  );
}

export function GoldTab({
  items,
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
  resettingLabelId,
  healthRefreshKey,
  entityLabelFilter,
  onLabelFilter,
  onOpen,
  onReset,
  onOpenLabel,
}: GoldTabProps) {
  return (
    <>
      <DatasetHealthPanel
        refreshKey={healthRefreshKey}
        activeLabel={entityLabelFilter}
        onLabelFilter={onLabelFilter}
        onOpenLabel={onOpenLabel}
      />

      <FilterBar
        search={search}
        onSearchChange={onSearchChange}
        searchPlaceholder="Search verified examples..."
        aria-label="Search verified gold labels"
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
