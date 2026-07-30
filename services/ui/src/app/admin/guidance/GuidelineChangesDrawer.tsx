/**
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AffectedRule {
  rule_id: string;
  description: string;
  status: string;
}

interface AddedRec {
  number: string;
  text: string;
  section_title: string;
}

interface RemovedRec {
  number: string;
  text: string;
  section_title: string;
  rules: AffectedRule[];
}

interface ModifiedRec {
  number: string;
  section_title: string;
  old_text: string;
  new_text: string;
  rules: AffectedRule[];
}

/**
 * A "clears the similarity floor but not the margin" pairing between a
 * recommendation that disappeared (removed_number) and one that newly
 * appeared (added_number) -- see recommendation_key_matcher.py's module
 * docstring. Genuinely ambiguous: a plausible move exists but isn't
 * confident enough for the ingest-time matcher to carry the identity
 * forward silently, so the reviewer must say yes or no explicitly before
 * re-ingest can be confirmed.
 */
interface PossibleMove {
  removed_number: string;
  added_number: string;
  score: number | null;
}

interface DiffResult {
  added: AddedRec[];
  removed: RemovedRec[];
  modified: ModifiedRec[];
  unchanged_count: number;
  total_stored: number;
  total_remote: number;
  _unchanged_numbers: string[];
  possible_moves: PossibleMove[];
}

/** One admin answer per possible-move pairing, keyed by
 * "removed_number|added_number". Undefined = not yet answered. */
type PossibleMoveAnswers = Record<string, "moved" | "unrelated">;

function moveKey(move: PossibleMove): string {
  return `${move.removed_number}|${move.added_number}`;
}

interface DiffJob {
  status: "queued" | "running" | "done" | "error";
  diff?: DiffResult;
  error?: string;
}

interface Props {
  code: string | null;
  onClose: () => void;
  onConfirmIngest: (code: string, diffJobId: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(s: string): "default" | "warning" | "success" | "error" {
  if (s === "pending_review") return "warning";
  if (s === "active") return "success";
  if (s === "superseded") return "error";
  return "default";
}

function RuleChips({ rules }: { rules: AffectedRule[] }) {
  if (rules.length === 0) return null;
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
      {rules.map((r) => (
        <Chip
          key={r.rule_id}
          label={r.description || r.rule_id}
          size="small"
          color={statusColor(r.status)}
          variant="outlined"
          sx={{ maxWidth: 240, fontSize: 11 }}
        />
      ))}
    </Stack>
  );
}

function RecSection({
  number,
  section,
}: {
  number: string;
  section: string;
}) {
  return (
    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
      <strong>{number}</strong>
      {section ? ` \u2014 ${section}` : ""}
    </Typography>
  );
}

function SideBySide({
  left,
  right,
}: {
  left: string | null;
  right: string | null;
}) {
  return (
    <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
      {left !== null && (
        <Box
          sx={{
            flex: 1,
            bgcolor: "#FEF2F2",
            border: "1px solid #FECACA",
            borderRadius: 1,
            p: 1,
            fontSize: 13,
            lineHeight: 1.5,
            color: "#7F1D1D",
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 700, color: "#B91C1C", display: "block", mb: 0.5 }}>
            Current version
          </Typography>
          {left}
        </Box>
      )}
      {right !== null && (
        <Box
          sx={{
            flex: 1,
            bgcolor: "#F0FDF4",
            border: "1px solid #BBF7D0",
            borderRadius: 1,
            p: 1,
            fontSize: 13,
            lineHeight: 1.5,
            color: "#14532D",
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 700, color: "#15803D", display: "block", mb: 0.5 }}>
            Updated version
          </Typography>
          {right}
        </Box>
      )}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Possible moves -- ambiguous renumber pairings needing an explicit yes/no
// ---------------------------------------------------------------------------

function PossibleMovesSection({
  moves,
  answers,
  onAnswer,
}: {
  moves: PossibleMove[];
  answers: PossibleMoveAnswers;
  onAnswer: (move: PossibleMove, answer: "moved" | "unrelated") => void;
}) {
  if (moves.length === 0) return null;
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, color: "#5B21B6" }}>
        <HelpOutlineIcon fontSize="small" sx={{ verticalAlign: "middle", mr: 0.5 }} />
        Possible moves needing your check ({moves.length})
      </Typography>
      <Typography variant="body2" sx={{ mb: 1.5, color: "text.secondary" }}>
        These recommendations look similar enough that they might be the same
        one, just renumbered. We are not sure, so please check each one
        before you can confirm.
      </Typography>
      <Stack spacing={1.5}>
        {moves.map((move) => {
          const key = moveKey(move);
          const answer = answers[key];
          return (
            <Box
              key={key}
              data-testid={`possible-move-${key}`}
              sx={{
                border: "1px solid #DDD6FE",
                borderRadius: 1,
                p: 1.5,
                bgcolor: "#F5F3FF",
              }}
            >
              <Typography variant="body2" sx={{ mb: 1 }}>
                Did <strong>{move.removed_number}</strong> move to become{" "}
                <strong>{move.added_number}</strong>?
                {move.score !== null && (
                  <Typography
                    component="span"
                    variant="caption"
                    color="text.secondary"
                    sx={{ ml: 1 }}
                  >
                    ({Math.round(move.score * 100)}% text match)
                  </Typography>
                )}
              </Typography>
              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  variant={answer === "moved" ? "contained" : "outlined"}
                  color="secondary"
                  onClick={() => onAnswer(move, "moved")}
                >
                  Yes, it moved
                </Button>
                <Button
                  size="small"
                  variant={answer === "unrelated" ? "contained" : "outlined"}
                  color="inherit"
                  onClick={() => onAnswer(move, "unrelated")}
                >
                  No, unrelated
                </Button>
              </Stack>
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Summary banner
// ---------------------------------------------------------------------------

// Atlas: DI-C2DE7FDF / DO-F8CDEBBA -- a guideline update must never claim
// an approved rule "moves to awaiting review" when it actually stays
// active and is only flagged for a re-review.
function countRulesByStatus(diff: DiffResult, status: string): number {
  const affected = [...diff.modified, ...diff.removed];
  return affected.reduce(
    (n, r) => n + r.rules.filter((rule) => rule.status === status).length,
    0
  );
}

function DiffSummary({ diff }: { diff: DiffResult }) {
  const approvedAffected = countRulesByStatus(diff, "active");
  const pendingAffected = countRulesByStatus(diff, "pending_review");
  const rulesAffected = approvedAffected + pendingAffected;

  return (
    <Box
      sx={{
        bgcolor: "#FFFBEB",
        border: "1px solid #FDE68A",
        borderRadius: 1,
        p: 2,
        mb: 2,
      }}
    >
      <Stack direction="row" spacing={2} flexWrap="wrap">
        {diff.modified.length > 0 && (
          <Chip
            icon={<SwapHorizIcon fontSize="small" />}
            label={`${diff.modified.length} modified`}
            size="small"
            sx={{ bgcolor: "#FEF3C7", color: "#92400E", border: "1px solid #FDE68A" }}
          />
        )}
        {diff.added.length > 0 && (
          <Chip
            icon={<AddCircleOutlineIcon fontSize="small" />}
            label={`${diff.added.length} new`}
            size="small"
            sx={{ bgcolor: "#ECFDF5", color: "#065F46", border: "1px solid #A7F3D0" }}
          />
        )}
        {diff.removed.length > 0 && (
          <Chip
            icon={<RemoveCircleOutlineIcon fontSize="small" />}
            label={`${diff.removed.length} removed`}
            size="small"
            sx={{ bgcolor: "#FEF2F2", color: "#7F1D1D", border: "1px solid #FECACA" }}
          />
        )}
        <Chip
          icon={<CheckCircleOutlineIcon fontSize="small" />}
          label={`${diff.unchanged_count} unchanged`}
          size="small"
          sx={{ bgcolor: "#F1F5F9", color: "#475569", border: "1px solid #CBD5E1" }}
        />
      </Stack>
      {approvedAffected > 0 && (
        <Typography variant="body2" sx={{ mt: 1, color: "#92400E" }}>
          {approvedAffected} already-approved rule{approvedAffected !== 1 ? "s" : ""} will
          stay active and keep being enforced -- confirming this update never retires an
          approval automatically. {approvedAffected !== 1 ? "They" : "It"} will be flagged
          for a quick re-review, since the guideline wording changed underneath{" "}
          {approvedAffected !== 1 ? "them" : "it"}.
        </Typography>
      )}
      {pendingAffected > 0 && (
        <Typography variant="body2" sx={{ mt: 1, color: "#92400E" }}>
          {pendingAffected} rule{pendingAffected !== 1 ? "s" : ""} awaiting review will be
          archived (history is kept). You will need to generate new rules for those
          recommendations afterwards.
        </Typography>
      )}
      {rulesAffected === 0 && (diff.modified.length > 0 || diff.removed.length > 0) && (
        <Typography variant="body2" sx={{ mt: 1, color: "#92400E" }}>
          No existing rules are linked to the changed recommendations.
        </Typography>
      )}
      <Typography variant="body2" sx={{ mt: 1, color: "text.secondary" }}>
        Rules for unchanged recommendations will be preserved as-is.
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function GuidelineChangesDrawer({
  code,
  onClose,
  onConfirmIngest,
}: Props) {
  const [diffJobId, setDiffJobId] = useState<string | null>(null);
  const [diffJob, setDiffJob] = useState<DiffJob | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [moveAnswers, setMoveAnswers] = useState<PossibleMoveAnswers>({});
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleAnswerMove = useCallback(
    (move: PossibleMove, answer: "moved" | "unrelated") => {
      setMoveAnswers((prev) => ({ ...prev, [moveKey(move)]: answer }));
    },
    []
  );

  const stopPolling = useCallback(() => {
    if (pollRef.current) clearTimeout(pollRef.current);
  }, []);

  const pollDiff = useCallback(
    (jobId: string, guidelineCode: string) => {
      async function tick() {
        try {
          const r = await fetch(`/api/nice/${guidelineCode}/diff/${jobId}`);
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const job = (await r.json()) as DiffJob;
          setDiffJob(job);
          if (job.status === "done" || job.status === "error") return;
          pollRef.current = setTimeout(tick, 2000);
        } catch {
          setDiffJob({ status: "error", error: "Lost contact with the server." });
        }
      }
      pollRef.current = setTimeout(tick, 1000);
    },
    []
  );

  // Start diff when the drawer opens for a new code
  useEffect(() => {
    if (!code) {
      stopPolling();
      setDiffJobId(null);
      setDiffJob(null);
      setStartError(null);
      setMoveAnswers({});
      return;
    }

    let active = true;
    stopPolling();
    setDiffJobId(null);
    setDiffJob(null);
    setStartError(null);
    setMoveAnswers({});

    fetch(`/api/nice/${code}/diff/start`, { method: "POST" })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.statusText);
        return r.json() as Promise<{ job_id: string }>;
      })
      .then(({ job_id }) => {
        if (!active) return;
        setDiffJobId(job_id);
        pollDiff(job_id, code);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setStartError(
          e instanceof Error ? e.message : "Could not start comparison."
        );
      });

    return () => {
      active = false;
      stopPolling();
    };
  }, [code, pollDiff, stopPolling]);

  const handleConfirm = useCallback(() => {
    if (!code || !diffJobId) return;
    onConfirmIngest(code, diffJobId);
    onClose();
  }, [code, diffJobId, onConfirmIngest, onClose]);

  const diff = diffJob?.status === "done" ? diffJob.diff : undefined;
  const hasChanges = diff
    ? diff.added.length + diff.removed.length + diff.modified.length > 0
    : false;
  const possibleMoves = diff?.possible_moves ?? [];
  const allMovesAnswered = possibleMoves.every(
    (move) => moveAnswers[moveKey(move)] !== undefined
  );

  return (
    <Drawer
      anchor="right"
      open={!!code}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", md: 800 }, p: 0 } }}
    >
      {/* Header */}
      <Box sx={{ px: 3, pt: 3, pb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              What has changed in {code}?
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Comparing what is stored in LEO against the latest NICE version.
            </Typography>
          </Box>
          <Button variant="text" size="small" onClick={onClose} sx={{ mt: -0.5 }}>
            Close
          </Button>
        </Stack>
      </Box>

      {/* Body */}
      <Box sx={{ px: 3, py: 2, overflowY: "auto", flex: 1 }}>
        {/* Loading */}
        {(!diffJob || diffJob.status === "queued" || diffJob.status === "running") && !startError && (
          <Stack alignItems="center" spacing={2} sx={{ py: 6 }}>
            <CircularProgress />
            <Typography color="text.secondary">Comparing recommendations with NICE...</Typography>
          </Stack>
        )}

        {/* Start error */}
        {startError && (
          <Alert severity="error">{startError}</Alert>
        )}

        {/* Diff error */}
        {diffJob?.status === "error" && (
          <Alert severity="error">{diffJob.error || "Comparison failed. Please try again."}</Alert>
        )}

        {/* No changes */}
        {diff && !hasChanges && (
          <Alert severity="success" icon={<CheckCircleOutlineIcon />}>
            No changes detected. All {diff.unchanged_count} recommendations match the latest NICE version.
          </Alert>
        )}

        {/* Diff results */}
        {diff && hasChanges && (
          <Box>
            <DiffSummary diff={diff} />

            <PossibleMovesSection
              moves={possibleMoves}
              answers={moveAnswers}
              onAnswer={handleAnswerMove}
            />

            {/* Modified */}
            {diff.modified.length > 0 && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, color: "#92400E" }}>
                  <SwapHorizIcon fontSize="small" sx={{ verticalAlign: "middle", mr: 0.5 }} />
                  Modified recommendations ({diff.modified.length})
                </Typography>
                <Stack spacing={2}>
                  {diff.modified.map((rec) => (
                    <Box key={rec.number} sx={{ border: "1px solid #FDE68A", borderRadius: 1, p: 1.5 }}>
                      <RecSection number={rec.number} section={rec.section_title} />
                      <SideBySide left={rec.old_text} right={rec.new_text} />
                      <RuleChips rules={rec.rules} />
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            {/* Added */}
            {diff.added.length > 0 && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, color: "#065F46" }}>
                  <AddCircleOutlineIcon fontSize="small" sx={{ verticalAlign: "middle", mr: 0.5 }} />
                  New recommendations ({diff.added.length})
                </Typography>
                <Stack spacing={1}>
                  {diff.added.map((rec) => (
                    <Box key={rec.number} sx={{ border: "1px solid #BBF7D0", borderRadius: 1, p: 1.5 }}>
                      <RecSection number={rec.number} section={rec.section_title} />
                      <SideBySide left={null} right={rec.text} />
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            {/* Removed */}
            {diff.removed.length > 0 && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, color: "#7F1D1D" }}>
                  <RemoveCircleOutlineIcon fontSize="small" sx={{ verticalAlign: "middle", mr: 0.5 }} />
                  Removed recommendations ({diff.removed.length})
                </Typography>
                <Stack spacing={1}>
                  {diff.removed.map((rec) => (
                    <Box key={rec.number} sx={{ border: "1px solid #FECACA", borderRadius: 1, p: 1.5 }}>
                      <RecSection number={rec.number} section={rec.section_title} />
                      <SideBySide left={rec.text} right={null} />
                      <RuleChips rules={rec.rules} />
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}
          </Box>
        )}
      </Box>

      {/* Footer */}
      {diff && (
        <Box sx={{ px: 3, py: 2, borderTop: 1, borderColor: "divider" }}>
          <Divider sx={{ mb: 2 }} />
          {hasChanges ? (
            <Stack alignItems="flex-end" spacing={1}>
              {!allMovesAnswered && (
                <Typography variant="caption" color="text.secondary">
                  Please answer yes or no for every possible move above
                  before you confirm.
                </Typography>
              )}
              <Stack direction="row" spacing={1} justifyContent="flex-end">
                <Button variant="outlined" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  variant="contained"
                  color="warning"
                  onClick={handleConfirm}
                  disabled={!allMovesAnswered}
                >
                  Confirm re-ingest
                </Button>
              </Stack>
            </Stack>
          ) : (
            <Stack direction="row" justifyContent="flex-end">
              <Button variant="outlined" onClick={onClose}>
                Close
              </Button>
            </Stack>
          )}
        </Box>
      )}
    </Drawer>
  );
}
