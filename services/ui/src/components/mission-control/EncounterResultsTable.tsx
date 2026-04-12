"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableFooter from "@mui/material/TableFooter";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import type { EncounterListItem } from "@/lib/missionControlApi";

type JobState = "queued" | "running" | "completed" | "failed";
type ChipColor = "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning";

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

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function normaliseScore(value: number | null | undefined): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null;
  }
  return Math.min(1, Math.max(0, value));
}

function scoreColour(value: number): string {
  if (value >= 0.6) {
    return "success.main";
  }
  if (value >= 0.3) {
    return "warning.main";
  }
  return "text.disabled";
}

function MatchStrengthBar({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 0.35 }}>
        No score
      </Typography>
    );
  }
  return (
    <Box title={`This result matches your search at ${Math.round(score * 100)}%`} sx={{ mt: 0.5 }}>
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
  minVectorScore?: number
): boolean {
  const combined = normaliseScore(row.score);
  if (combined == null || combined < minScore) {
    return true;
  }
  if (typeof minVectorScore !== "number") {
    return false;
  }
  const vector = normaliseScore(row.vector_score);
  return vector == null || vector < minVectorScore;
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
  onToggleSelection,
  onOpenPreview,
  onPageChange,
  onRowsPerPageChange,
}: Props) {
  const vectorDrift = (liveMinVectorScore ?? 0) !== (lastSearchedMinVectorScore ?? 0);
  const showLiveImpact = liveMinScore !== lastSearchedMinScore || vectorDrift;
  const removedCount = rows.filter((row) =>
    isFilteredByLiveThreshold(row, liveMinScore, liveMinVectorScore)
  ).length;

  return (
    <Paper elevation={0} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, overflow: "hidden" }}>
      {showLiveImpact && (
        <Alert severity="info" sx={{ m: 1.5, mb: 0.5 }}>
          At this setting, {removedCount} of {rows.length} shown results would be removed.
          Click Search to update the list.
        </Alert>
      )}
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell padding="checkbox" sx={{ width: 48, bgcolor: "background.paper" }} />
            <TableCell sx={{ whiteSpace: "nowrap", bgcolor: "background.paper" }}>Date</TableCell>
            <TableCell sx={{ bgcolor: "background.paper" }}>Patient</TableCell>
            <TableCell sx={{ bgcolor: "background.paper" }}>Match</TableCell>
            <TableCell align="right" sx={{ bgcolor: "background.paper" }}>Codes</TableCell>
            <TableCell sx={{ bgcolor: "background.paper" }}>Status</TableCell>
            <TableCell sx={{ bgcolor: "background.paper" }}>Encounter text</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={7}>
                <Box sx={{ py: 4, textAlign: "center" }}>
                  <Typography variant="body2" color="text.secondary">
                    No encounters found. Enter a search term and click Search.
                  </Typography>
                </Box>
              </TableCell>
            </TableRow>
          )}
          {rows.map((row) => {
            const matchMeta = MATCH_CHIP[row.match_type] ?? MATCH_CHIP.none;
            const status = statuses[row.encounter_id];
            const statusMeta = status ? STATUS_CHIP[status] : null;
            const isSelected = Boolean(selected[row.encounter_id]);
            const isHighlighted = highlightedEncounterId === row.encounter_id;
            const combinedScore = normaliseScore(row.score);
            const wouldBeRemoved = showLiveImpact &&
              isFilteredByLiveThreshold(row, liveMinScore, liveMinVectorScore);

            return (
              <TableRow
                key={row.encounter_id}
                hover
                selected={isSelected}
                onClick={() => onOpenPreview(row)}
                sx={{
                  cursor: "pointer",
                  opacity: wouldBeRemoved ? 0.45 : 1,
                  bgcolor: isHighlighted ? "rgba(31, 58, 138, 0.08)" : undefined,
                  transition: "opacity 0.15s ease",
                }}
              >
                <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    size="small"
                    checked={isSelected}
                    onChange={() => onToggleSelection(row)}
                    aria-label={`Select encounter ${row.encounter_id}`}
                  />
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Typography variant="body2">{formatDate(row.encounter_date)}</Typography>
                </TableCell>
                <TableCell>
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: "monospace", fontSize: "0.72rem", color: "text.secondary" }}
                  >
                    {row.patient_id}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={matchMeta.label}
                    color={matchMeta.color}
                    variant={matchMeta.color === "default" ? "outlined" : "filled"}
                  />
                  <MatchStrengthBar score={combinedScore} />
                </TableCell>
                <TableCell align="right">
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: row.coded_count > 0 ? 600 : 400, color: row.coded_count > 0 ? "success.main" : "text.secondary" }}
                  >
                    {row.coded_count}
                  </Typography>
                </TableCell>
                <TableCell>
                  {statusMeta ? (
                    <Chip size="small" label={statusMeta.label} color={statusMeta.color} variant="filled" />
                  ) : (
                    <Typography variant="body2" color="text.disabled">-</Typography>
                  )}
                </TableCell>
                <TableCell sx={{ maxWidth: 500 }}>
                  <Typography variant="body2" noWrap title={row.text ?? ""}>
                    {row.text ?? ""}
                  </Typography>
                  {!!row.match_rationale?.length && (
                    <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: "wrap" }} useFlexGap>
                      {row.match_rationale.slice(0, 4).map((term, idx) => (
                        <Chip
                          key={`${row.encounter_id}-mr-${idx}-${term}`}
                          size="small"
                          label={term}
                          variant="outlined"
                          sx={{ fontSize: "0.65rem", height: 20 }}
                        />
                      ))}
                    </Stack>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TablePagination
              colSpan={7}
              count={totalResults}
              page={page - 1}
              rowsPerPage={rowsPerPage}
              rowsPerPageOptions={[25, 50, 100]}
              onPageChange={(_, p) => onPageChange(p + 1)}
              onRowsPerPageChange={(e) => onRowsPerPageChange(Number(e.target.value))}
              sx={{ border: 0 }}
            />
          </TableRow>
        </TableFooter>
      </Table>
    </Paper>
  );
}
