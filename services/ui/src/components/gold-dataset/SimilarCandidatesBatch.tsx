import { useMemo } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import EditNoteIcon from "@mui/icons-material/EditNote";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { parseEntities, truncate } from "./goldDatasetUtils";
import type { SimilarCandidateItem } from "./goldDatasetTypes";
import {
  HighlightedText,
  collectHighlightTerms,
} from "@/components/mission-control/HighlightedText";
import {
  computeMatchRationale,
  expandSearchTerms,
} from "@/components/mission-control/encounterRelevance";

interface Props {
  open: boolean;
  candidates: SimilarCandidateItem[];
  selected: Record<string, boolean>;
  loading: boolean;
  sourceEntityCount: number;
  reviewedIds: Set<string>;
  loadingReviewId: string | null;
  // DI-LEO-AI-527 -- when the dialog opens from the dry-run review queue,
  // forward the active debounced search so each similar-candidate row uses
  // the same amber <HighlightedText> token and "why this matched" chip
  // taxonomy as /care/encounters and the patient drawer.
  search?: string;
  onClose: () => void;
  onToggle: (candidateId: string, checked: boolean) => void;
  onReviewCandidate: (candidateId: string) => void;
  onApply: () => void;
}

export default function SimilarCandidatesBatch({
  open,
  candidates,
  selected,
  loading,
  sourceEntityCount,
  reviewedIds,
  loadingReviewId,
  search,
  onClose,
  onToggle,
  onReviewCandidate,
  onApply,
}: Props) {
  const selectedCount = useMemo(
    () =>
      candidates.filter(
        (c) => selected[c.candidate_id] && !reviewedIds.has(c.candidate_id),
      ).length,
    [candidates, selected, reviewedIds],
  );
  const expandedTerms = useMemo(() => expandSearchTerms(search), [search]);

  const mismatchCount = useMemo(
    () =>
      candidates.filter((c) => {
        if (reviewedIds.has(c.candidate_id)) return false;
        return parseEntities(c.entities_json).length !== sourceEntityCount;
      }).length,
    [candidates, sourceEntityCount, reviewedIds],
  );

  const totalAccepted = selectedCount + reviewedIds.size;

  return (
    <Dialog open={open} onClose={() => !loading && onClose()} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <span>Apply to similar candidates</span>
          {reviewedIds.size > 0 && (
            <Chip
              icon={<CheckCircleIcon />}
              label={`${reviewedIds.size} reviewed`}
              color="success"
              size="small"
              variant="outlined"
            />
          )}
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Alert severity="info">
            Each encounter is different. Use <strong>Review</strong> to open the full editor
            — fix entity types, SNOMED codes, and assertions before accepting. For candidates
            where the extraction looks correct, tick the checkbox to accept as-is.
          </Alert>

          {mismatchCount > 0 && (
            <Alert severity="warning" icon={<WarningAmberIcon />}>
              {mismatchCount} candidate{mismatchCount > 1 ? "s have" : " has"} a different
              number of entities than the one you just reviewed. Those rows are unticked by
              default — review them individually.
            </Alert>
          )}

          <Box sx={{ maxHeight: 460, overflowY: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox" />
                  <TableCell>Encounter text</TableCell>
                  <TableCell>Extracted entities</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    Entities
                  </TableCell>
                  <TableCell align="right">Similarity</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {candidates.map((item) => {
                  const isReviewed = reviewedIds.has(item.candidate_id);
                  const isLoadingReview = loadingReviewId === item.candidate_id;
                  const entities = parseEntities(item.entities_json);
                  const countMismatch =
                    !isReviewed && entities.length !== sourceEntityCount;
                  const truncatedText = truncate(item.text, 200);
                  const matchRationale = computeMatchRationale(
                    item.text,
                    expandedTerms,
                  );
                  const highlightTerms = collectHighlightTerms(
                    search,
                    matchRationale.hitTerms,
                  );
                  const showRationale =
                    expandedTerms.length > 0 && matchRationale.hitTerms.length > 0;

                  return (
                    <TableRow
                      key={item.candidate_id}
                      hover
                      sx={
                        isReviewed
                          ? { backgroundColor: "rgba(46,125,50,0.05)" }
                          : countMismatch
                          ? { backgroundColor: "rgba(237,108,2,0.06)" }
                          : undefined
                      }
                    >
                      {/* Checkbox — hidden for reviewed rows */}
                      <TableCell padding="checkbox">
                        {isReviewed ? (
                          <CheckCircleIcon
                            sx={{ fontSize: 18, color: "success.main", ml: 1 }}
                          />
                        ) : (
                          <Checkbox
                            checked={Boolean(selected[item.candidate_id])}
                            onChange={(e) => onToggle(item.candidate_id, e.target.checked)}
                            disabled={loading || isLoadingReview}
                          />
                        )}
                      </TableCell>

                      {/* Encounter text */}
                      <TableCell sx={{ maxWidth: 260 }}>
                        <Typography
                          variant="body2"
                          sx={isReviewed ? { color: "text.secondary" } : undefined}
                        >
                          {highlightTerms.length > 0 ? (
                            <HighlightedText
                              text={truncatedText}
                              terms={highlightTerms}
                              testId="similar-candidate-row-highlight"
                            />
                          ) : (
                            truncatedText
                          )}
                        </Typography>
                        {showRationale && (
                          <Box
                            data-testid="similar-candidate-row-match-rationale"
                            sx={{
                              mt: 0.5,
                              display: "flex",
                              flexWrap: "wrap",
                              gap: 0.5,
                            }}
                          >
                            {matchRationale.hitTerms.slice(0, 4).map((term, idx) => (
                              <Chip
                                key={`${item.candidate_id}-mr-${idx}-${term}`}
                                size="small"
                                label={term}
                                variant="outlined"
                                data-testid="similar-candidate-row-match-rationale-chip"
                                sx={{ height: 20, fontSize: "0.65rem" }}
                              />
                            ))}
                          </Box>
                        )}
                        {isReviewed && (
                          <Typography
                            variant="caption"
                            sx={{ color: "success.main", fontWeight: 600 }}
                          >
                            Reviewed and accepted
                          </Typography>
                        )}
                      </TableCell>

                      {/* Entities */}
                      <TableCell>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          {entities.map((entity, index) => (
                            <Chip
                              key={`${entity.text}-${index}`}
                              size="small"
                              label={entity.snomed_term || entity.text}
                              color={entity.snomed_concept_id ? "primary" : "warning"}
                              variant="outlined"
                              sx={isReviewed ? { opacity: 0.5 } : undefined}
                            />
                          ))}
                          {entities.length === 0 && (
                            <Typography variant="caption" sx={{ color: "text.disabled" }}>
                              No entities
                            </Typography>
                          )}
                        </Stack>
                      </TableCell>

                      {/* Entity count */}
                      <TableCell align="right">
                        {countMismatch ? (
                          <Tooltip
                            title={`Source has ${sourceEntityCount} ${sourceEntityCount === 1 ? "entity" : "entities"} — this has ${entities.length}. Review before including.`}
                          >
                            <Stack
                              direction="row"
                              alignItems="center"
                              justifyContent="flex-end"
                              spacing={0.5}
                            >
                              <WarningAmberIcon
                                sx={{ fontSize: 14, color: "warning.main" }}
                              />
                              <Typography
                                variant="caption"
                                sx={{ color: "warning.main", fontWeight: 600 }}
                              >
                                {entities.length} vs {sourceEntityCount}
                              </Typography>
                            </Stack>
                          </Tooltip>
                        ) : (
                          <Typography
                            variant="caption"
                            sx={isReviewed ? { color: "text.disabled" } : undefined}
                          >
                            {entities.length}
                          </Typography>
                        )}
                      </TableCell>

                      {/* Similarity */}
                      <TableCell align="right">
                        <Typography
                          variant="caption"
                          sx={isReviewed ? { color: "text.disabled" } : undefined}
                        >
                          {Math.round((item.similarity || 0) * 100)}%
                        </Typography>
                      </TableCell>

                      {/* Review action */}
                      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                        {isReviewed ? null : (
                          <Tooltip title="Open the full editor — fix entity types, codes, and assertions before accepting">
                            <span>
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={
                                  isLoadingReview ? (
                                    <CircularProgress size={12} />
                                  ) : (
                                    <EditNoteIcon />
                                  )
                                }
                                disabled={loading || !!loadingReviewId}
                                onClick={() => onReviewCandidate(item.candidate_id)}
                                sx={{ textTransform: "none", fontSize: "0.75rem" }}
                              >
                                Review
                              </Button>
                            </span>
                          </Tooltip>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading} sx={{ textTransform: "none" }}>
          Skip all
        </Button>
        <Button
          variant="contained"
          onClick={onApply}
          disabled={loading || totalAccepted < 1}
          sx={{ textTransform: "none" }}
        >
          {loading
            ? "Applying..."
            : selectedCount === 0 && reviewedIds.size > 0
            ? "Done"
            : selectedCount > 0
            ? `Accept ${selectedCount} as gold`
            : "Accept as gold"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
