/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CheckCircleOutline from "@mui/icons-material/CheckCircleOutline";
import FlagOutlined from "@mui/icons-material/FlagOutlined";
import LockOutlined from "@mui/icons-material/LockOutlined";
import { useRole } from "@leo/design-system";
import ConfirmDialog from "@/components/ConfirmDialog";
import { getStatusLabel } from "@/lib/pathwayLabels";
import type {
  EpisodeLocksResponse,
  MissionEpisode,
  ReviewerRole,
} from "@/lib/missionControlApi";
import {
  patchEpisodeReview,
  patchEpisodeStatus,
} from "@/lib/missionControlApi";
import {
  STATUS_COMPLETED,
  STATUS_CLOSED_BENIGN,
  STATUS_STALE_NO_DIAGNOSIS,
  STATUS_STALE_POST_SPECIALIST,
  STATUS_IN_PROGRESS,
  STATUS_REVIEW,
} from "@/lib/episodeStatus";

const OVERRIDEABLE_STATUSES = [
  STATUS_COMPLETED,
  STATUS_CLOSED_BENIGN,
  STATUS_STALE_NO_DIAGNOSIS,
  STATUS_STALE_POST_SPECIALIST,
  STATUS_IN_PROGRESS,
];

interface Props {
  episode: MissionEpisode;
  userEmail: string;
  onReviewed: (updated: Partial<MissionEpisode>) => void;
}

export default function ReviewActionsPanel({ episode, userEmail, onReviewed }: Props) {
  const [notes, setNotes] = useState(episode.audit_notes ?? "");
  const [flagged, setFlagged] = useState(episode.audit_flag ?? false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overrideStatus, setOverrideStatus] = useState("");
  const [confirmOverride, setConfirmOverride] = useState(false);

  const { selectedRole } = useRole();
  const reviewerRole: ReviewerRole | null =
    selectedRole === "clinician" || selectedRole === "qa_ra_lead"
      ? selectedRole
      : null;

  const isReviewed = Boolean(episode.reviewed_by);
  // The reconcile-pathway flow is now reached via the patient
  // drawer's "Edit episode" button (EditEpisodeDialog -> Review tab).
  // We keep reviewerRole here only because the existing override UI
  // below still gates on it.
  void reviewerRole;

  const handleMarkReviewed = async () => {
    setSaving(true);
    setError(null);
    try {
      await patchEpisodeReview(episode.episode_id, {
        reviewed_by: userEmail,
        audit_notes: notes,
        audit_flag: flagged,
      });
      onReviewed({ reviewed_by: userEmail, reviewed_at: new Date().toISOString(), audit_notes: notes, audit_flag: flagged });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save review. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveNotes = async () => {
    setSaving(true);
    setError(null);
    try {
      await patchEpisodeReview(episode.episode_id, {
        reviewed_by: episode.reviewed_by ?? userEmail,
        audit_notes: notes,
        audit_flag: flagged,
      });
      onReviewed({ audit_notes: notes, audit_flag: flagged });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleConfirmOverride = async () => {
    setConfirmOverride(false);
    setSaving(true);
    setError(null);
    try {
      await patchEpisodeStatus(episode.episode_id, overrideStatus, "Manual override by auditor");
      onReviewed({ status: overrideStatus });
      setOverrideStatus("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change status. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Review status indicator */}
      {isReviewed && (
        <Chip
          icon={<CheckCircleOutline />}
          label={`Reviewed by ${episode.reviewed_by}`}
          color="success"
          size="small"
          variant="outlined"
        />
      )}

      {/* Notes */}
      <Box>
        <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 500 }}>
          Audit notes
        </Typography>
        <TextField
          multiline
          rows={3}
          fullWidth
          size="small"
          placeholder="Add notes about this pathway here..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          inputProps={{ "aria-label": "Audit notes" }}
        />
      </Box>

      {/* Flag toggle */}
      <FormControlLabel
        control={
          <Switch
            checked={flagged}
            onChange={(e) => setFlagged(e.target.checked)}
            color="warning"
            size="small"
          />
        }
        label={
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <FlagOutlined fontSize="small" color={flagged ? "warning" : "disabled"} />
            <Typography variant="body2">Flag for follow-up</Typography>
          </Box>
        }
      />

      {/* Error */}
      {error && (
        <Typography variant="caption" color="error">
          {error}
        </Typography>
      )}

      {/* Actions */}
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {isReviewed ? (
          <Button
            size="small"
            variant="outlined"
            onClick={handleSaveNotes}
            disabled={saving}
          >
            Save notes
          </Button>
        ) : (
          <Button
            size="small"
            variant="contained"
            onClick={handleMarkReviewed}
            disabled={saving}
            startIcon={<CheckCircleOutline />}
            disableElevation
          >
            Mark as reviewed
          </Button>
        )}
        {episode.status === STATUS_REVIEW && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ alignSelf: "center" }}
          >
            Use the &quot;Edit episode&quot; button at the top of the drawer
            to reconcile pathway milestones.
          </Typography>
        )}
      </Box>

      <Divider />

      {/* Status override */}
      <Box>
        <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 500 }}>
          Override pathway status
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          Only use this when the pipeline status is clearly wrong. This is recorded in the audit trail.
        </Typography>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <TextField
            select
            size="small"
            value={overrideStatus}
            onChange={(e) => setOverrideStatus(e.target.value)}
            sx={{ minWidth: 200 }}
            label="New status"
            inputProps={{ "aria-label": "Override pathway status" }}
          >
            {OVERRIDEABLE_STATUSES
              .filter((s) => s !== episode.status)
              .map((s) => (
                <MenuItem key={s} value={s}>
                  {getStatusLabel(s)}
                </MenuItem>
              ))}
          </TextField>
          <Button
            size="small"
            variant="outlined"
            color="warning"
            disabled={!overrideStatus || saving}
            onClick={() => setConfirmOverride(true)}
          >
            Override
          </Button>
        </Box>
      </Box>

      {confirmOverride && (
        <ConfirmDialog
          title="Override pathway status?"
          body={`You are changing this pathway to "${getStatusLabel(overrideStatus)}". This action will be recorded in the audit trail and cannot be undone automatically.`}
          confirmLabel="Yes, override"
          variant="danger"
          onConfirm={handleConfirmOverride}
          onCancel={() => setConfirmOverride(false)}
        />
      )}
    </Box>
  );
}
