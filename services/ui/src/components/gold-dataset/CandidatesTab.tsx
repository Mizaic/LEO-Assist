/**
 * CandidatesTab -- candidates list + toolbar for the gold dataset panel.
 *
 * Extracted from GoldDatasetPanel as part of Wave E file-size refactoring.
 * Design Controls: DI-21946271, DO-1E9BCC70.
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Pagination from "@mui/material/Pagination";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import { FilterBar, SkeletonList } from "@leo/design-system";
import type { Candidate } from "./goldDatasetTypes";
import CandidateReviewList from "./CandidateReviewList";

export interface CandidatesTabProps {
  items: Candidate[];
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
  findSimilarAfterGold: boolean;
  onFindSimilarChange: (value: boolean) => void;
  onOpen: (id: string) => void;
  onMarkGold: (id: string) => void;
  onDelete: (id: string) => void;
  openingLabelId: string | null;
  markingGoldId: string | null;
  deletingId: string | null;
}

function EmptyMessage({ search }: { search: string }) {
  return (
    <Box sx={{ py: 4, textAlign: "center" }}>
      <Typography color="text.secondary" variant="body2">
        {search
          ? `Nothing matches "${search}". Try different words.`
          : "No sentences to review yet. Run the pipeline to get started."}
      </Typography>
    </Box>
  );
}

export function CandidatesTab({
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
  findSimilarAfterGold,
  onFindSimilarChange,
  onOpen,
  onMarkGold,
  onDelete,
  openingLabelId,
  markingGoldId,
  deletingId,
}: CandidatesTabProps) {
  return (
    <>
      <FilterBar
        search={search}
        onSearchChange={onSearchChange}
        searchPlaceholder="Search by sentence text..."
        aria-label="Search training candidates"
      />

      <FormControlLabel
        control={
          <Switch
            checked={findSimilarAfterGold}
            onChange={(e) => onFindSimilarChange(e.target.checked)}
            inputProps={{ "aria-label": "Look for similar candidates after accepting" }}
          />
        }
        label={
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Look for similar candidates after accepting
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Off by default. Turn this on to review matching candidates before moving on.
            </Typography>
          </Box>
        }
        sx={{ mb: 1.25, alignItems: "flex-start" }}
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
          <CandidateReviewList
            items={items}
            onOpen={(id) => onOpen(id)}
            onMarkGold={onMarkGold}
            onDelete={onDelete}
            openingLabelId={openingLabelId}
            markingGoldId={markingGoldId}
            deletingId={deletingId}
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
