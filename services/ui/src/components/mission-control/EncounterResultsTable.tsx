"use client";

/**
 * EncounterResultsTable -- DI-LEO-AI-514.
 *
 * Lifts the dry-run Candidates row template (`ReviewListCard` from
 * `@leo/design-system`) onto /care/encounters so reviewers see one
 * consistent visual language across:
 *
 *   - /admin/training Candidates queue (the dry-run review list)
 *   - /care/patients side drawer encounter cards
 *   - /care/encounters search results (this file)
 *
 * The row composes:
 *   - tone   = positive when codes >= 1, danger when batch state is
 *              `failed`, warning when matched but no codes,
 *              neutral otherwise
 *   - title  = encounter text snippet rendered through the shared
 *              <HighlightedText> primitive
 *   - meta   = en-GB short date | patient id (monospace) | match
 *              strength bar | optional "would be removed" hint
 *   - chips  = match-type chip + "{n} coded" chip + status chip +
 *              up to 4 match_rationale chips
 *   - actions = selection checkbox (clicking propagates to the
 *               toggle handler, NOT to the row preview)
 *
 * Pagination is rendered below the list using MUI `Pagination`
 * (the dry-run pattern) instead of a `TableFooter`.
 */

import { type ReactNode, useMemo } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import Pagination from "@mui/material/Pagination";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ReviewListCard, type ReviewListItem } from "@leo/design-system";
import type { EncounterListItem } from "@/lib/missionControlApi";
import {
  HighlightedText,
  collectHighlightTerms,
} from "./HighlightedText";

type JobState = "queued" | "running" | "completed" | "failed";
type ChipColor =
  | "default"
  | "primary"
  | "secondary"
  | "error"
  | "info"
  | "success"
  | "warning";

const MATCH_CHIP: Record<string, { color: ChipColor; label: string }> = {
  hybrid: { color: "info", label: "Hybrid" },
  keyword: { color: "warning", label: "Keyword" },
  semantic: { color: "success", label: "Semantic" },
  none: { color: "default", label: "None" },
};

const STATUS_CHIP: Record<JobState, { color: ChipColor; label: string }> = {
  queued: { color: "default", label: "Queued" },
  running: { color: "info", label: "Running" },
  completed: { color: "success", label: "Done" },
  failed: { color: "error", label: "Failed" },
};

const ROWS_PER_PAGE_OPTIONS = [25, 50, 100] as const;

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function normaliseScore(value: number | null | undefined): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Math.min(1, Math.max(0, value));
}

function scoreColour(value: number): string {
  if (value >= 0.6) return "success.main";
  if (value >= 0.3) return "warning.main";
  return "text.disabled";
}

function MatchStrengthBar({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <Typography variant="caption" color="text.disabled">
        No score
      </Typography>
    );
  }
  return (
    <Box
      title={`This result matches your search at ${Math.round(score * 100)}%`}
      sx={{ display: "inline-flex", alignItems: "center" }}
    >
      <Box sx={{ height: 4, width: 84, bgcolor: "grey.300", borderRadius: 999 }}>
        <Box
          sx={{
            height: "100%",
            width: `${Math.round(score * 100)}%`,
            bgcolor: scoreColour(score),
            borderRadius: 999,
            transition: "width 0.2s ease",
          }}
        />
      </Box>
    </Box>
  );
}

function isFilteredByLiveThreshold(
  row: EncounterListItem,
  minScore: number,
  minVectorScore?: number,
): boolean {
  const combined = normaliseScore(row.score);
  if (combined == null || combined < minScore) return true;
  if (typeof minVectorScore !== "number") return false;
  const vector = normaliseScore(row.vector_score);
  return vector == null || vector < minVectorScore;
}

// -- toneFor ---------------------------------------------------------------
// Maps an encounter row to the ReviewListCard tone vocabulary. Order
// matters: a `failed` batch run is the most attention-grabbing signal,
// then "matched but no codes" (warning), then "has codes" (positive).
export function toneFor(
  row: EncounterListItem,
  status: JobState | undefined,
  hasActiveQuery: boolean,
): ReviewListItem["tone"] {
  if (status === "failed") return "danger";
  if (row.coded_count >= 1) return "positive";
  if (hasActiveQuery) return "warning";
  return "neutral";
}

interface BuildItemContext {
  row: EncounterListItem;
  status: JobState | undefined;
  isSelected: boolean;
  isHighlighted: boolean;
  wouldBeRemoved: boolean;
  highlightTerms: string[];
  hasActiveQuery: boolean;
  onToggleSelection: (item: EncounterListItem) => void;
  onOpenPreview: (item: EncounterListItem) => void;
}

function rowMeta(row: EncounterListItem, wouldBeRemoved: boolean): ReactNode {
  const score = normaliseScore(row.score);
  return (
    <>
      <span>{formatDate(row.encounter_date)}</span>
      <Box
        component="span"
        sx={{
          fontFamily: "monospace",
          fontSize: "0.7rem",
          color: "text.secondary",
        }}
      >
        {row.patient_id}
      </Box>
      <MatchStrengthBar score={score} />
      {wouldBeRemoved && (
        <Box
          component="span"
          sx={{ color: "warning.main", fontWeight: 600, fontSize: "0.7rem" }}
        >
          Would be removed at current threshold
        </Box>
      )}
    </>
  );
}

function rowChips(
  row: EncounterListItem,
  status: JobState | undefined,
): ReactNode {
  const matchMeta = MATCH_CHIP[row.match_type] ?? MATCH_CHIP.none;
  const statusMeta = status ? STATUS_CHIP[status] : null;
  return (
    <>
      <Chip
        size="small"
        label={matchMeta.label}
        color={matchMeta.color}
        variant={matchMeta.color === "default" ? "outlined" : "filled"}
        sx={{ height: 22, fontSize: "0.7rem" }}
      />
      <Chip
        size="small"
        label={`${row.coded_count} coded`}
        color={row.coded_count > 0 ? "success" : "default"}
        variant={row.coded_count > 0 ? "filled" : "outlined"}
        sx={{ height: 22, fontSize: "0.7rem" }}
      />
      {statusMeta && (
        <Chip
          size="small"
          label={statusMeta.label}
          color={statusMeta.color}
          variant="filled"
          sx={{ height: 22, fontSize: "0.7rem" }}
        />
      )}
      {row.match_rationale?.slice(0, 4).map((term, idx) => (
        <Chip
          key={`${row.encounter_id}-mr-${idx}-${term}`}
          size="small"
          label={term}
          variant="outlined"
          sx={{ height: 20, fontSize: "0.65rem" }}
        />
      ))}
    </>
  );
}

function rowActions(
  row: EncounterListItem,
  isSelected: boolean,
  onToggle: (item: EncounterListItem) => void,
): ReactNode {
  return (
    <Box
      data-testid={`encounter-row-actions-${row.encounter_id}`}
      onClick={(e) => e.stopPropagation()}
    >
      <Checkbox
        size="small"
        checked={isSelected}
        onChange={() => onToggle(row)}
        onClick={(e) => e.stopPropagation()}
        aria-label={`Select encounter ${row.encounter_id}`}
      />
    </Box>
  );
}

export function buildEncounterListItem(ctx: BuildItemContext): ReviewListItem {
  const {
    row,
    status,
    isSelected,
    isHighlighted,
    wouldBeRemoved,
    highlightTerms,
    hasActiveQuery,
    onToggleSelection,
    onOpenPreview,
  } = ctx;
  const text = (row.text ?? "").trim();
  const title = text ? (
    <HighlightedText text={text} terms={highlightTerms} />
  ) : (
    <Box component="span" sx={{ color: "text.disabled", fontStyle: "italic" }}>
      No text recorded.
    </Box>
  );

  return {
    id: row.encounter_id,
    title: (
      <Box
        sx={{
          opacity: wouldBeRemoved ? 0.55 : 1,
          bgcolor: isHighlighted ? "rgba(31, 58, 138, 0.08)" : undefined,
          borderRadius: 1,
          // Single-line clamp so dense lists stay scannable. The full
          // text is available in the preview dialog.
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {title}
      </Box>
    ),
    meta: rowMeta(row, wouldBeRemoved),
    chips: rowChips(row, status),
    actions: rowActions(row, isSelected, onToggleSelection),
    tone: toneFor(row, status, hasActiveQuery),
    onSelect: () => onOpenPreview(row),
    selected: isSelected,
  };
}

interface Props {
  rows: EncounterListItem[];
  selected: Record<string, EncounterListItem>;
  statuses: Record<string, JobState>;
  totalResults: number;
  page: number;
  rowsPerPage: number;
  liveMinScore: number;
  liveMinVectorScore?: number;
  lastSearchedMinScore: number;
  lastSearchedMinVectorScore?: number;
  highlightedEncounterId?: string | null;
  /** Free-text query the reviewer typed into the search box. Used
   *  to highlight matches inside each row title and to render a
   *  query-echoing empty state. */
  searchQuery?: string;
  onToggleSelection: (item: EncounterListItem) => void;
  onOpenPreview: (item: EncounterListItem) => void;
  onPageChange: (page: number) => void;
  onRowsPerPageChange: (rowsPerPage: number) => void;
}

export default function EncounterResultsTable({
  rows,
  selected,
  statuses,
  totalResults,
  page,
  rowsPerPage,
  liveMinScore,
  liveMinVectorScore,
  lastSearchedMinScore,
  lastSearchedMinVectorScore,
  highlightedEncounterId,
  searchQuery,
  onToggleSelection,
  onOpenPreview,
  onPageChange,
  onRowsPerPageChange,
}: Props) {
  const vectorDrift =
    (liveMinVectorScore ?? 0) !== (lastSearchedMinVectorScore ?? 0);
  const showLiveImpact = liveMinScore !== lastSearchedMinScore || vectorDrift;
  const removedCount = rows.filter((row) =>
    isFilteredByLiveThreshold(row, liveMinScore, liveMinVectorScore),
  ).length;
  const trimmedQuery = (searchQuery ?? "").trim();
  const hasActiveQuery = trimmedQuery.length > 0;

  const highlightTerms = useMemo(
    () => collectHighlightTerms(searchQuery, undefined),
    [searchQuery],
  );

  const items: ReviewListItem[] = useMemo(
    () =>
      rows.map((row) =>
        buildEncounterListItem({
          row,
          status: statuses[row.encounter_id],
          isSelected: Boolean(selected[row.encounter_id]),
          isHighlighted: highlightedEncounterId === row.encounter_id,
          wouldBeRemoved:
            showLiveImpact &&
            isFilteredByLiveThreshold(row, liveMinScore, liveMinVectorScore),
          highlightTerms,
          hasActiveQuery,
          onToggleSelection,
          onOpenPreview,
        }),
      ),
    [
      rows,
      statuses,
      selected,
      highlightedEncounterId,
      showLiveImpact,
      liveMinScore,
      liveMinVectorScore,
      highlightTerms,
      hasActiveQuery,
      onToggleSelection,
      onOpenPreview,
    ],
  );

  const totalPages = Math.max(1, Math.ceil(totalResults / rowsPerPage));

  if (rows.length === 0) {
    return (
      <Box
        data-testid={
          hasActiveQuery ? "encounter-empty-query" : "encounter-empty-default"
        }
        sx={{
          py: 5,
          px: 3,
          textAlign: "center",
          border: "1px dashed",
          borderColor: "divider",
          borderRadius: 2,
          bgcolor: "background.paper",
        }}
      >
        <Typography variant="body2" color="text.secondary">
          {hasActiveQuery
            ? `Nothing matches "${trimmedQuery}". Try different words.`
            : "No encounters found. Enter a search term and click Search."}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {showLiveImpact && (
        <Alert severity="info" sx={{ mb: 1.5 }}>
          At this setting, {removedCount} of {rows.length} shown results would
          be removed. Click Search to update the list.
        </Alert>
      )}
      <ReviewListCard items={items} density="comfortable" />
      <Stack
        direction="row"
        spacing={2}
        alignItems="center"
        justifyContent="flex-end"
        sx={{ mt: 1.5 }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography variant="caption" color="text.secondary">
            Rows per page
          </Typography>
          <Select
            size="small"
            value={rowsPerPage}
            onChange={(e) => onRowsPerPageChange(Number(e.target.value))}
            sx={{ height: 30, minWidth: 70, fontSize: "0.8rem" }}
          >
            {ROWS_PER_PAGE_OPTIONS.map((opt) => (
              <MenuItem key={opt} value={opt}>
                {opt}
              </MenuItem>
            ))}
          </Select>
        </Stack>
        <Pagination
          count={totalPages}
          page={page}
          onChange={(_, p) => onPageChange(p)}
          size="small"
          color="primary"
        />
        <Typography variant="caption" color="text.secondary">
          {totalResults.toLocaleString()} results
        </Typography>
      </Stack>
    </Box>
  );
}
