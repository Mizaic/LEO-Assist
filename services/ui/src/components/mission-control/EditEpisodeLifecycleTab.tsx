/**
 * EditEpisodeLifecycleTab -- shared content for the Review, Close,
 * and Merge sections of EditEpisodeDialog. Each section owns its own
 * sub-form so the dialog shell stays compact.
 *
 * Atlas trace:
 *   DOs: DO-9530152E (mission-control review),
 *        DO-EE78E305 (timeline view),
 *        DO-13EA9B93 (encounter manage),
 *        DO-BDBEDA43 (manual update)
 *   DIs: DI-6EA84931, DI-DD67ACFF, DI-F4C06C92
 *   VTs: VT-80AAC194 (Edit episode UI + drawer integration)
 */
"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormLabel from "@mui/material/FormLabel";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { closeEpisode, mergeEpisodes } from "@/lib/analyticsApi";
import { patchEpisodeReview } from "@/lib/missionControlApi";
import type { MissionEpisode } from "@/lib/missionControlApi";
import {
  STATUS_CLOSED,
  STATUS_CLOSED_BENIGN,
  STATUS_COMPLETED,
  STATUS_MERGED,
  availableActions,
  episodeStatusLabel,
  isReviewed,
  normaliseStatus,
} from "@/lib/episodeLifecycle";

type ManualCloseStatus =
  | typeof STATUS_COMPLETED
  | typeof STATUS_CLOSED
  | typeof STATUS_CLOSED_BENIGN;

interface Props {
  section: "review" | "close" | "merge";
  episode: MissionEpisode;
  siblingEpisodes: MissionEpisode[];
  reviewerEmail: string;
  reviewerRole: string;
  disabled: boolean;
  onSaved: (info?: string) => void;
  onError: (message: string) => void;
  onEpisodeRemoved: () => void;
}

export default function EditEpisodeLifecycleTab(props: Props) {
  if (props.section === "review") return <ReviewSection {...props} />;
  if (props.section === "close") return <CloseSection {...props} />;
  return <MergeSection {...props} />;
}

// ---------------------------------------------------------------------------
// Review section -- mark reviewed, set audit notes / flag.
// ---------------------------------------------------------------------------

function ReviewSection({ episode, reviewerEmail, disabled, onSaved, onError }: Props) {
  const [notes, setNotes] = useState(episode.audit_notes ?? "");
  const [flag, setFlag] = useState(Boolean(episode.audit_flag));
  const [saving, setSaving] = useState(false);

  const allowed = useMemo(() => new Set(availableActions(episode)), [episode]);
  const reviewed = isReviewed(episode);
  const statusLabel = episodeStatusLabel(episode.status);

  const handleMarkReviewed = async () => {
    setSaving(true);
    try {
      await patchEpisodeReview(episode.episode_id, {
        reviewed_by: reviewerEmail,
        audit_notes: notes || undefined,
        audit_flag: flag,
      });
      onSaved(`Marked ${episode.episode_id} as reviewed.`);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not mark as reviewed.");
    } finally {
      setSaving(false);
    }
  };

  if (reviewed && !allowed.has("review.mark")) {
    return (
      <Stack spacing={2} data-testid="edit-episode-review-already-signed-off">
        <Typography variant="body2" color="text.secondary">
          This pathway is already signed off (status:{" "}
          <strong>{statusLabel}</strong>; reviewed by{" "}
          <strong>{episode.reviewed_by ?? "a curator"}</strong> on{" "}
          {episode.reviewed_at ?? "an earlier date"}). Use Close or Merge
          to take a new action.
        </Typography>
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Confirm the pathway is correct and add a note for the audit trail.
        Marking as reviewed records you as the reviewer with a timestamp.
        Current status: <strong>{statusLabel}</strong>.
      </Typography>
      <TextField
        label="Reviewer notes"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        disabled={disabled || saving}
        multiline
        minRows={3}
        inputProps={{ "aria-label": "Reviewer notes" }}
        helperText="Plain English. Saved on the audit trail."
      />
      <FormControlLabel
        control={
          <Checkbox
            checked={flag}
            onChange={(e) => setFlag(e.target.checked)}
            inputProps={{ "aria-label": "Audit flag" }}
            disabled={disabled || saving}
          />
        }
        label="Flag for further audit (audit_flag)"
      />
      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        <Button
          type="button"
          variant="contained"
          onClick={handleMarkReviewed}
          disabled={disabled || saving}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : null}
          data-testid="edit-episode-review-save"
        >
          Mark reviewed
        </Button>
      </Box>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Close section -- close or complete the episode.
// ---------------------------------------------------------------------------

function CloseSection({ episode, disabled, onSaved, onError, onEpisodeRemoved }: Props) {
  const [status, setStatus] = useState<"closed" | "completed">("closed");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  const canClose =
    episode.status !== "merged" &&
    episode.status !== "completed" &&
    episode.status !== "closed";

  const handleClose = async () => {
    if (!reason.trim()) return;
    setSaving(true);
    try {
      await closeEpisode(episode.episode_id, status, reason.trim());
      onSaved(`Episode ${episode.episode_id} marked ${status}.`);
      onEpisodeRemoved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not close the episode.");
    } finally {
      setSaving(false);
    }
  };

  if (!canClose) {
    return (
      <Typography variant="body2" color="text.secondary">
        This episode is already <strong>{episode.status}</strong>. There is
        nothing to close.
      </Typography>
    );
  }

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Close or complete this pathway. The episode stays in the audit
        trail; only its lifecycle status changes.
      </Typography>
      <FormControl>
        <FormLabel id="close-status-label">Status</FormLabel>
        <RadioGroup
          row
          aria-labelledby="close-status-label"
          value={status}
          onChange={(e) => setStatus(e.target.value as "closed" | "completed")}
        >
          <FormControlLabel value="closed" control={<Radio />} label="Closed (no diagnosis)" />
          <FormControlLabel value="completed" control={<Radio />} label="Completed (diagnosis confirmed)" />
        </RadioGroup>
      </FormControl>
      <TextField
        label="Reason (required)"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        disabled={disabled || saving}
        multiline
        minRows={2}
        inputProps={{ "aria-label": "Reason for closing" }}
        helperText="Plain English. Why is this pathway being closed?"
      />
      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        <Button
          type="button"
          variant="contained"
          color="warning"
          onClick={handleClose}
          disabled={disabled || saving || !reason.trim()}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : null}
          data-testid="edit-episode-close-confirm"
        >
          {status === "completed" ? "Mark completed" : "Close pathway"}
        </Button>
      </Box>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Merge section -- merge sibling episodes into this one.
// ---------------------------------------------------------------------------

function MergeSection({
  episode,
  siblingEpisodes,
  disabled,
  onSaved,
  onError,
  onEpisodeRemoved,
}: Props) {
  const candidates = siblingEpisodes.filter(
    (s) => s.episode_id !== episode.episode_id && s.status !== "merged"
  );
  const [secondaryId, setSecondaryId] = useState(candidates[0]?.episode_id ?? "");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  if (candidates.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        There are no other open episodes for this patient that could be
        merged into this one.
      </Typography>
    );
  }

  const handleMerge = async () => {
    if (!secondaryId || !reason.trim()) return;
    setSaving(true);
    try {
      await mergeEpisodes(episode.episode_id, [secondaryId], reason.trim());
      onSaved(
        `Merged ${secondaryId} into ${episode.episode_id}. The secondary episode is now status=merged.`
      );
      onEpisodeRemoved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not merge the episodes.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Merge another episode into this one. Linked encounters move to
        this episode and the secondary becomes <strong>merged</strong>.
      </Typography>
      <TextField
        select
        label="Secondary episode to merge in"
        value={secondaryId}
        onChange={(e) => setSecondaryId(e.target.value)}
        disabled={disabled || saving}
        inputProps={{ "aria-label": "Secondary episode" }}
      >
        {candidates.map((s) => (
          <MenuItem key={s.episode_id} value={s.episode_id}>
            {s.episode_id}
            {s.cancer_type ? ` - ${s.cancer_type}` : ""}
            {s.status ? ` (${s.status})` : ""}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        label="Reason (required)"
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        disabled={disabled || saving}
        multiline
        minRows={2}
        inputProps={{ "aria-label": "Reason for merging" }}
        helperText="Plain English. Why are these the same pathway?"
      />
      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        <Button
          type="button"
          variant="contained"
          color="warning"
          onClick={handleMerge}
          disabled={disabled || saving || !secondaryId || !reason.trim()}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : null}
          data-testid="edit-episode-merge-confirm"
        >
          Merge into this pathway
        </Button>
      </Box>
    </Stack>
  );
}
