/**
 * ReconcilePathwayDrawer -- the right-hand drawer where a clinician
 * or QA / RA lead reconciles a pathway that landed in the in_review
 * lifecycle bucket.
 *
 * Composition:
 *   - one MilestoneSlotRow per slot (engine pick + rationale + actions)
 *   - reviewer notes textarea
 *   - bucket flip warning + type-the-name confirm gate
 *   - single primary "Confirm and lock" action
 *
 * The drawer never PATCHes incrementally. It collects every staged
 * action, calls patchEpisodeReconcile once with confirm_bucket_flip
 * exactly when the warning has been satisfied, and surfaces the
 * server's 412 ("would silently flip the bucket") response by
 * showing the warning on the next render.
 *
 * Atlas trace:
 *   DO: services/ui/src/components/mission-control/ReconcilePathwayDrawer.tsx
 *   DI: DI-9DCC9F84 (Reconcile pathway)
 *   DI: DI-C424BB44 (VerificationLock primitive)
 *   VT: VT-CABCEC8B (reconcile router), VT-96455BC1 (lock service)
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Close from "@mui/icons-material/Close";
import LockOutlined from "@mui/icons-material/LockOutlined";
import BucketFlipWarning, { bucketMatch } from "./BucketFlipWarning";
import MilestoneSlotRow, {
  type SlotRowData,
  type StagedAction,
} from "./MilestoneSlotRow";
import {
  patchEpisodeReconcile,
  type EpisodeLocksResponse,
  type MissionEpisode,
  type ReconcileRequestBody,
  type ReviewerRole,
  type VerificationLockSummary,
} from "@/lib/missionControlApi";

const DRAWER_WIDTH = "44vw";

interface Props {
  open: boolean;
  episode: MissionEpisode;
  /** Slot rows pre-built by the parent from the episode + engine pick. */
  rows: SlotRowData[];
  /** Reviewer email (from session). */
  reviewerEmail: string;
  /** Reviewer role -- gated upstream so this is always one of two values. */
  reviewerRole: ReviewerRole;
  /** Existing locks (used to populate row.lock if not pre-merged). */
  locks?: EpisodeLocksResponse | null;
  /** Open the patient-scoped encounter picker for the Replace flow. */
  onReplaceClick: (slot: string) => void;
  /** Replacement encounter chosen by the parent picker, keyed by slot. */
  replacements?: Record<string, { encounterId: string; milestoneType?: string }>;
  onClose: () => void;
  /** Notify the parent so it can refresh the episode/lock view. */
  onSaved: () => void;
}

interface SubmitState {
  saving: boolean;
  error: string | null;
  bucketFlip: { current: string; proposed: string } | null;
}

export default function ReconcilePathwayDrawer({
  open,
  episode,
  rows,
  reviewerEmail,
  reviewerRole,
  locks,
  onReplaceClick,
  replacements,
  onClose,
  onSaved,
}: Props) {
  const [staged, setStaged] = useState<Record<string, StagedAction>>({});
  const [reason, setReason] = useState("");
  const [bucketTyped, setBucketTyped] = useState("");
  const [submit, setSubmit] = useState<SubmitState>({
    saving: false,
    error: null,
    bucketFlip: null,
  });

  // Re-merge replacements when the parent picker resolves.
  useEffect(() => {
    if (!replacements) return;
    setStaged((prev) => {
      const next = { ...prev };
      for (const [slot, pick] of Object.entries(replacements)) {
        next[slot] = {
          slot,
          action: "replace",
          encounterId: pick.encounterId,
          milestoneType: pick.milestoneType ?? null,
        };
      }
      return next;
    });
  }, [replacements]);

  // Reset transient state every time the drawer is reopened on a new episode.
  useEffect(() => {
    if (!open) return;
    setStaged({});
    setReason("");
    setBucketTyped("");
    setSubmit({ saving: false, error: null, bucketFlip: null });
  }, [open, episode.episode_id]);

  const lockedBySlot = useMemo(() => {
    const map = new Map<string, VerificationLockSummary>();
    if (!locks) return map;
    for (const lock of locks.locks) {
      if (lock.entity_type === "is_part_of_edge") {
        const [, ep] = lock.entity_id.split(":");
        if (ep === episode.episode_id) {
          map.set(lock.entity_id, lock);
        }
      }
    }
    return map;
  }, [locks, episode.episode_id]);

  const enrichedRows: SlotRowData[] = useMemo(
    () =>
      rows.map((row) => {
        if (row.lock) return row;
        const composite = `${row.engineEncounterId ?? "__unfilled__"}:${
          episode.episode_id
        }`;
        const lock = lockedBySlot.get(composite) ?? null;
        return { ...row, lock };
      }),
    [rows, lockedBySlot, episode.episode_id]
  );

  const stagedCount = Object.keys(staged).length;
  const flipPending = Boolean(submit.bucketFlip);
  const flipConfirmed = flipPending
    ? bucketMatch(bucketTyped, submit.bucketFlip!.proposed)
    : true;
  const canSubmit =
    stagedCount > 0 &&
    reason.trim().length > 0 &&
    !submit.saving &&
    flipConfirmed;

  const handleStage = (action: StagedAction) => {
    setStaged((prev) => ({ ...prev, [action.slot]: action }));
  };

  const handleSubmit = async () => {
    setSubmit((s) => ({ ...s, saving: true, error: null }));
    const body: ReconcileRequestBody = {
      reviewed_by: reviewerEmail,
      reviewer_role: reviewerRole,
      reason,
      confirm_bucket_flip: flipPending,
      actions: Object.values(staged).map((a) => ({
        slot: a.slot,
        action: a.action,
        encounter_id: a.encounterId,
        milestone_type: a.milestoneType,
      })),
    };
    try {
      await patchEpisodeReconcile(episode.episode_id, body);
      onSaved();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not save.";
      // The router returns a structured 412 detail; fall back to a generic
      // bucket flip prompt if we can spot the marker phrase in the message.
      const flip = parseFlipFromError(message);
      setSubmit((s) => ({
        saving: false,
        error: flip ? null : message,
        bucketFlip: flip ?? s.bucketFlip,
      }));
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      ModalProps={{ keepMounted: false }}
      PaperProps={{ sx: { width: DRAWER_WIDTH, maxWidth: "100vw", p: 3 } }}
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="h6">Reconcile pathway</Typography>
          <IconButton aria-label="Close" onClick={onClose}>
            <Close />
          </IconButton>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Confirm or correct the pathway milestones for episode{" "}
          <strong>{episode.episode_id}</strong>. Each confirmed slot is
          locked so the engine cannot overwrite it.
        </Typography>

        {flipPending && submit.bucketFlip ? (
          <BucketFlipWarning
            currentBucket={submit.bucketFlip.current}
            proposedBucket={submit.bucketFlip.proposed}
            typed={bucketTyped}
            onTypedChange={setBucketTyped}
          />
        ) : null}

        {submit.error ? (
          <Alert severity="error" data-testid="reconcile-error">
            {submit.error}
          </Alert>
        ) : null}

        <Stack spacing={2}>
          {enrichedRows.map((row) => (
            <MilestoneSlotRow
              key={row.slot}
              row={row}
              staged={staged[row.slot]}
              onStage={handleStage}
              onReplaceClick={onReplaceClick}
              disabled={submit.saving}
            />
          ))}
        </Stack>

        <TextField
          label="Reviewer notes (audit trail)"
          required
          multiline
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          inputProps={{ "aria-label": "Reviewer notes" }}
          helperText="Plain English. These notes are saved with the lock."
        />

        <TextField
          select
          label="Your role"
          value={reviewerRole}
          disabled
          inputProps={{ "aria-label": "Reviewer role" }}
        >
          <MenuItem value="clinician">Clinician</MenuItem>
          <MenuItem value="qa_ra_lead">QA / RA lead</MenuItem>
        </TextField>

        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button onClick={onClose} disabled={submit.saving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="primary"
            startIcon={
              submit.saving ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <LockOutlined />
              )
            }
            disabled={!canSubmit}
            onClick={handleSubmit}
            data-testid="reconcile-confirm-button"
          >
            Confirm and lock ({stagedCount})
          </Button>
        </Stack>
      </Box>
    </Drawer>
  );
}

const FLIP_RE =
  /(?:from\s+)?(\w[\w_]*)\s+to\s+(\w[\w_]*)|current_bucket["']?\s*[:=]\s*["']?(\w[\w_]*)/i;

function parseFlipFromError(
  message: string
): { current: string; proposed: string } | null {
  if (!/bucket/i.test(message)) return null;
  const m = FLIP_RE.exec(message);
  if (!m) return null;
  if (m[1] && m[2]) return { current: m[1], proposed: m[2] };
  return null;
}
