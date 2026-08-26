/**
 * DeleteEpisodeConfirm -- destructive confirm dialog with a
 * type-the-id gate. The reviewer must type the exact episode_id
 * before the Delete button enables, and the same value is sent in
 * the body as ``confirm_episode_id``. The server enforces the same
 * check before any graph write so the UI gate is defence in depth,
 * not the only barrier.
 *
 * Atlas trace:
 *   DO: DO-CFB91205, DI: DI-41B71BF8
 *   Risks: R-DD23FB44 (accidental deletion), R-A737EE12 (audit)
 *   VT: VT-4A333473 (delete confirm gate)
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Close from "@mui/icons-material/Close";
import { deleteEpisode } from "@/lib/missionControlApi";

const CURATOR_ROLES = new Set(["triage_clinician", "clinician_admin", "regulatory_reviewer", "administrator"]);

interface Props {
  open: boolean;
  episodeId: string;
  /** Cancer type / condition shown in the confirmation copy. */
  episodeLabel?: string | null;
  reviewerRole: string;
  onClose: () => void;
  /** Notify the parent on a successful deletion so it can drop the
   *  episode from the focused list. */
  onDeleted: (episodeId: string) => void;
}

export default function DeleteEpisodeConfirm({
  open,
  episodeId,
  episodeLabel,
  reviewerRole,
  onClose,
  onDeleted,
}: Props) {
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTyped("");
      setReason("");
      setError(null);
    }
  }, [open, episodeId]);

  const isCurator = CURATOR_ROLES.has(reviewerRole);
  const matches = typed === episodeId;
  const canDelete = isCurator && matches && reason.trim().length > 0 && !saving;

  const handleDelete = async () => {
    if (!canDelete) return;
    setSaving(true);
    setError(null);
    try {
      await deleteEpisode(episodeId, {
        confirm_episode_id: typed,
        reason: reason.trim(),
      });
      onDeleted(episodeId);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete the episode.");
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    if (saving) return;
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      fullWidth
      maxWidth="xs"
      aria-labelledby="delete-episode-dialog-title"
    >
      <DialogTitle id="delete-episode-dialog-title" sx={{ pr: 6 }}>
        Delete this episode?
        <IconButton
          aria-label="Close delete episode dialog"
          onClick={handleClose}
          disabled={saving}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <Close />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {!isCurator && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Your current role can only view episodes. Switch to a
            clinical or administrator role to delete one.
          </Alert>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        <Stack spacing={2}>
          <Alert severity="warning">
            This deletes the episode permanently. The audit trail keeps a
            full record of what was deleted, but the episode node itself
            and its links to encounters will be removed. Encounters are not
            deleted.
          </Alert>
          <Typography variant="body2" color="text.secondary">
            About to delete{" "}
            <strong>{episodeLabel ?? "the episode"}</strong> with id{" "}
            <code>{episodeId}</code>.
          </Typography>
          <TextField
            label="Type the episode id to confirm"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            disabled={!isCurator || saving}
            inputProps={{ "aria-label": "Type the episode id to confirm" }}
            helperText={
              matches
                ? "Match. You can now delete."
                : "Type the exact episode id shown above."
            }
            error={typed.length > 0 && !matches}
            data-testid="delete-episode-confirm-input"
          />
          <TextField
            label="Reason (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={!isCurator || saving}
            multiline
            minRows={2}
            inputProps={{ "aria-label": "Reason for deletion" }}
            helperText="Plain English. Saved on the audit trail."
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          onClick={handleDelete}
          variant="contained"
          color="error"
          disabled={!canDelete}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : null}
          data-testid="delete-episode-confirm-button"
        >
          Delete episode
        </Button>
      </DialogActions>
    </Dialog>
  );
}
