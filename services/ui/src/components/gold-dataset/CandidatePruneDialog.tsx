/**
 * CandidatePruneDialog -- DI-LEO-AI-197 / DO-LEO-AI-196.
 *
 * Confidence-gated auto-prune of non-completed TrainingCandidate rows.
 * Two-step contract:
 *   1. Run /api/training/candidates/prune/preview (read-only verdict
 *      ladder over candidates in `pending|processing|failed`).
 *   2. After the user explicitly acknowledges the deletion warning,
 *      send the explicit candidate_ids to
 *      /api/training/candidates/prune/execute.
 *
 * Safety rails (mirrored from DO-LEO-AI-195):
 *   - Destructive button is disabled until previewLoaded &&
 *     deleteCount > 0 && confirmAcknowledged.
 *   - The Dialog onClose handler is a no-op while loading is true.
 *   - Closing the dialog clears preview + confirmation so the next
 *     open starts from a clean slate.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

const PRUNE_STATUSES = ["pending", "processing", "failed"] as const;

type PruneStatus = (typeof PRUNE_STATUSES)[number];
type PruneVerdict = "keep" | "delete" | "review";

interface PruneAssessment {
  candidate_id: string;
  status: string;
  source: string;
  text: string;
  entity_count: number;
  accepted_count: number;
  rejected_count: number;
  blocked_assertion_count: number;
  verdict: PruneVerdict;
  rejection_reasons: string[];
}

interface PrunePreviewResponse {
  params: {
    min_surface_match: number;
    semantic_vector_floor: number;
    semantic_min_surface: number;
    statuses: string[];
    limit: number;
  };
  summary: {
    candidate_count: number;
    by_verdict: Record<PruneVerdict, number>;
    by_rejection_reason: Record<string, number>;
    entity_total: number;
    entity_accepted: number;
    entity_rejected: number;
  };
  candidates: PruneAssessment[];
}

interface PruneExecuteResponse {
  requested: number;
  deleted: number;
  skipped_completed: number;
  not_found: number;
  deleted_ids: string[];
  skipped_completed_ids: string[];
  not_found_ids: string[];
  cascade_counts: Record<string, { gold_labels_deleted: number; surface_form_tasks_deleted: number }>;
}

interface CandidatePruneDialogProps {
  open: boolean;
  onClose: () => void;
  onPruned?: (result: PruneExecuteResponse) => void;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) {
    let message = `${res.status}`;
    try {
      const payload = (await res.json()) as { detail?: unknown; message?: string };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail.trim();
      } else if (typeof payload.message === "string" && payload.message.trim()) {
        message = payload.message.trim();
      }
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return (await res.json()) as T;
}

function clamp01(value: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function VerdictChip({ verdict }: { verdict: PruneVerdict }) {
  const colorByVerdict: Record<PruneVerdict, "success" | "error" | "warning"> = {
    keep: "success",
    delete: "error",
    review: "warning",
  };
  return (
    <Chip
      size="small"
      label={verdict}
      color={colorByVerdict[verdict]}
      sx={{ textTransform: "capitalize", fontWeight: 600, minWidth: 64 }}
    />
  );
}

export default function CandidatePruneDialog({
  open,
  onClose,
  onPruned,
}: CandidatePruneDialogProps) {
  const [minSurfaceMatch, setMinSurfaceMatch] = useState<number>(0.7);
  const [semanticVectorFloor, setSemanticVectorFloor] = useState<number>(0.92);
  const [semanticMinSurface, setSemanticMinSurface] = useState<number>(0.66);
  const [statuses, setStatuses] = useState<PruneStatus[]>([
    "pending",
    "processing",
    "failed",
  ]);
  const [limit, setLimit] = useState<number>(500);

  const [preview, setPreview] = useState<PrunePreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const [executeLoading, setExecuteLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmAcknowledged, setConfirmAcknowledged] = useState<boolean>(false);
  const [executeResult, setExecuteResult] = useState<PruneExecuteResponse | null>(
    null,
  );

  const loading = previewLoading || executeLoading;
  const previewLoaded = preview !== null;
  const deleteCount = preview?.summary.by_verdict.delete ?? 0;
  const reviewCount = preview?.summary.by_verdict.review ?? 0;
  const keepCount = preview?.summary.by_verdict.keep ?? 0;

  const deleteIds = useMemo(
    () =>
      (preview?.candidates ?? [])
        .filter((c) => c.verdict === "delete")
        .map((c) => c.candidate_id),
    [preview],
  );

  function reset() {
    setPreview(null);
    setError(null);
    setConfirmAcknowledged(false);
    setExecuteResult(null);
  }

  function handleClose() {
    if (loading) return;
    reset();
    onClose();
  }

  async function runPreview() {
    if (loading) return;
    setPreviewLoading(true);
    setError(null);
    setExecuteResult(null);
    setConfirmAcknowledged(false);
    try {
      const payload = {
        min_surface_match: clamp01(minSurfaceMatch, 0.7),
        semantic_vector_floor: clamp01(semanticVectorFloor, 0.92),
        semantic_min_surface: clamp01(semanticMinSurface, 0.66),
        statuses,
        limit: Math.max(1, Math.min(2000, Math.round(limit || 500))),
      };
      const result = await jsonFetch<PrunePreviewResponse>(
        "/api/training/candidates/prune/preview",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      setPreview(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Preview failed");
      setPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function runExecute() {
    if (loading) return;
    if (!previewLoaded || deleteCount === 0 || !confirmAcknowledged) return;
    setExecuteLoading(true);
    setError(null);
    try {
      const result = await jsonFetch<PruneExecuteResponse>(
        "/api/training/candidates/prune/execute",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ candidate_ids: deleteIds }),
        },
      );
      setExecuteResult(result);
      if (onPruned) onPruned(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Execute failed");
    } finally {
      setExecuteLoading(false);
    }
  }

  function toggleStatus(status: PruneStatus) {
    setStatuses((prev) =>
      prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status],
    );
  }

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="lg" fullWidth>
      <DialogTitle>Auto-prune low-confidence candidates</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Re-runs the SNOMED proposal validator over non-completed
            training candidates. Candidates whose every entity is rejected
            at the supplied confidence floors are eligible for deletion.
            Run a preview first; nothing is deleted until you confirm.
          </Typography>

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Confidence floors
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="min_surface_match"
                type="number"
                size="small"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={minSurfaceMatch}
                disabled={loading}
                onChange={(e) => setMinSurfaceMatch(parseFloat(e.target.value))}
                helperText="default 0.7"
              />
              <TextField
                label="semantic_vector_floor"
                type="number"
                size="small"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={semanticVectorFloor}
                disabled={loading}
                onChange={(e) =>
                  setSemanticVectorFloor(parseFloat(e.target.value))
                }
                helperText="default 0.92"
              />
              <TextField
                label="semantic_min_surface"
                type="number"
                size="small"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={semanticMinSurface}
                disabled={loading}
                onChange={(e) =>
                  setSemanticMinSurface(parseFloat(e.target.value))
                }
                helperText="default 0.66"
              />
              <TextField
                label="limit"
                type="number"
                size="small"
                inputProps={{ step: 50, min: 1, max: 2000 }}
                value={limit}
                disabled={loading}
                onChange={(e) => setLimit(parseInt(e.target.value, 10))}
                helperText="max 2000"
              />
            </Stack>
          </Box>

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Status scope
            </Typography>
            <Stack direction="row" spacing={1}>
              {PRUNE_STATUSES.map((s) => (
                <FormControlLabel
                  key={s}
                  control={
                    <Checkbox
                      size="small"
                      checked={statuses.includes(s)}
                      disabled={loading}
                      onChange={() => toggleStatus(s)}
                    />
                  }
                  label={s}
                />
              ))}
              <TextField
                select
                size="small"
                value=""
                disabled
                sx={{ display: "none" }}
              >
                <MenuItem value="">unused</MenuItem>
              </TextField>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              Status &apos;completed&apos; is never targeted (gold record protection).
            </Typography>
          </Box>

          {error && <Alert severity="error">{error}</Alert>}

          <Box>
            <Button
              variant="outlined"
              onClick={runPreview}
              disabled={loading || statuses.length === 0}
            >
              {previewLoading ? "Running preview..." : "Run preview"}
            </Button>
          </Box>

          {previewLoaded && preview && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Preview results -- scanned {preview.summary.candidate_count} candidates
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
                <Chip color="error" label={`Delete: ${deleteCount}`} />
                <Chip color="warning" label={`Review: ${reviewCount}`} />
                <Chip color="success" label={`Keep: ${keepCount}`} />
              </Stack>
              <TableContainer sx={{ maxHeight: 360 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Verdict</TableCell>
                      <TableCell>Candidate</TableCell>
                      <TableCell>Source</TableCell>
                      <TableCell align="right">Entities</TableCell>
                      <TableCell>Top reasons</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {preview.candidates.slice(0, 200).map((c) => (
                      <TableRow key={c.candidate_id}>
                        <TableCell>
                          <VerdictChip verdict={c.verdict} />
                        </TableCell>
                        <TableCell sx={{ maxWidth: 360 }}>
                          <Typography variant="body2" noWrap title={c.text}>
                            {c.text || c.candidate_id}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {c.candidate_id}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption">{c.source || "-"}</Typography>
                        </TableCell>
                        <TableCell align="right">
                          {c.accepted_count}/{c.entity_count}
                        </TableCell>
                        <TableCell sx={{ maxWidth: 240 }}>
                          <Typography variant="caption" color="text.secondary">
                            {c.rejection_reasons.slice(0, 3).join(", ") || "-"}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              {preview.candidates.length > 200 && (
                <Typography variant="caption" color="text.secondary">
                  Showing first 200 rows; full list will be deleted on confirmation.
                </Typography>
              )}
            </Box>
          )}

          {previewLoaded && deleteCount > 0 && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={confirmAcknowledged}
                  disabled={loading}
                  onChange={(e) => setConfirmAcknowledged(e.target.checked)}
                />
              }
              label={`I understand this will permanently delete ${deleteCount} candidates and their draft GoldLabel / SurfaceFormTask rows.`}
            />
          )}

          {executeResult && (
            <Alert severity="success">
              Deleted {executeResult.deleted} of {executeResult.requested}.
              Skipped (completed): {executeResult.skipped_completed}.
              Not found: {executeResult.not_found}.
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={loading}>
          Close
        </Button>
        <Button
          onClick={runExecute}
          variant="contained"
          color="error"
          disabled={
            loading ||
            !previewLoaded ||
            deleteCount === 0 ||
            !confirmAcknowledged
          }
        >
          {executeLoading
            ? "Deleting..."
            : `Delete ${deleteCount} candidates`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
