/**
 * Curator sign-off panel.
 *
 * Replaces the pre-verdict "Mark reviewed" + "Override pathway status"
 * dual-path with a single verdict-driven sign-off (DI-E2498DF6).
 *
 * The curator picks ONE verdict -- confirm active / completed / benign /
 * merged / rejected -- and clicks Save sign-off. The UI calls
 * PATCH /mission-control/episodes/{id}/sign-off which records the
 * verdict, the mapped status, and the reviewed_at / reviewed_by stamps
 * in a single Cypher transaction, so the episode cannot be left in a
 * "reviewed but status unchanged" or "closed but not reviewed" state.
 *
 * Atlas trace:
 *   DO: DO-2A124BA0
 *   DI: DI-E2498DF6
 *   VT: VT-2487F804
 *   R:  R-2AA626E7
 */
"use client";

import { useEffect, useState } from "react";
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
import type { MissionEpisode } from "@/lib/missionControlApi";
import { patchEpisodeSignOff } from "@/lib/missionControlApi";
import {
  REVIEW_VERDICT_HELP,
  REVIEW_VERDICT_LABELS,
  REVIEW_VERDICT_VALUES,
} from "@/lib/episodeStatus";
import { getStatusLabel } from "@/lib/pathwayLabels";

interface Props {
  episode: MissionEpisode;
  userEmail: string;
  onReviewed: (updated: Partial<MissionEpisode>) => void;
}

export default function ReviewActionsPanel({
  episode,
  userEmail,
  onReviewed,
}: Props) {
  const isSignedOff = Boolean(episode.reviewed_at);
  const [verdict, setVerdict] = useState<string>(
    episode.review_verdict ?? "",
  );
  const [notes, setNotes] = useState(episode.audit_notes ?? "");
  const [flagged, setFlagged] = useState(episode.audit_flag ?? false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setVerdict(episode.review_verdict ?? "");
    setNotes(episode.audit_notes ?? "");
    setFlagged(episode.audit_flag ?? false);
  }, [
    episode.episode_id,
    episode.review_verdict,
    episode.audit_notes,
    episode.audit_flag,
  ]);

  const handleSignOff = async () => {
    setSaving(true);
    setError(null);
    try {
      const result = await patchEpisodeSignOff(episode.episode_id, {
        verdict,
        reviewed_by: userEmail,
        audit_notes: notes,
        audit_flag: flagged,
      });
      onReviewed({
        review_verdict: result.review_verdict,
        status: result.status,
        reviewed_by: result.reviewed_by,
        reviewed_at: result.reviewed_at,
        audit_notes: notes,
        audit_flag: flagged,
      });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not save sign-off. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  };

  const saveDisabled = saving || !verdict;
  const verdictHelp = verdict ? REVIEW_VERDICT_HELP[verdict] : "";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {isSignedOff && episode.review_verdict ? (
        <Chip
          icon={<CheckCircleOutline />}
          label={`${REVIEW_VERDICT_LABELS[episode.review_verdict] ?? episode.review_verdict} by ${episode.reviewed_by ?? "reviewer"}`}
          color="success"
          size="small"
          variant="outlined"
        />
      ) : null}

      {isSignedOff && !episode.review_verdict ? (
        <Chip
          icon={<CheckCircleOutline />}
          label={`Reviewed by ${episode.reviewed_by ?? "reviewer"} (no verdict recorded)`}
          color="warning"
          size="small"
          variant="outlined"
        />
      ) : null}

      <Box>
        <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 500 }}>
          Your verdict
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mb: 1 }}
        >
          Pick one. This records what you decided about the pathway and sets
          the status in one step.
        </Typography>
        <TextField
          select
          size="small"
          fullWidth
          value={verdict}
          onChange={(e) => setVerdict(e.target.value)}
          label="Verdict"
          inputProps={{ "aria-label": "Review verdict" }}
        >
          {REVIEW_VERDICT_VALUES.map((v) => (
            <MenuItem key={v} value={v}>
              {REVIEW_VERDICT_LABELS[v] ?? v}
            </MenuItem>
          ))}
        </TextField>
        {verdictHelp ? (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.5 }}
          >
            {verdictHelp} (pathway status will become{" "}
            {getStatusLabel(
              REVIEW_VERDICT_VALUES.includes(verdict) ? verdict : episode.status,
            )}
            )
          </Typography>
        ) : null}
      </Box>

      <Box>
        <Typography variant="body2" sx={{ mb: 0.5, fontWeight: 500 }}>
          Audit notes
        </Typography>
        <TextField
          multiline
          rows={3}
          fullWidth
          size="small"
          placeholder="Why did you pick this verdict? (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          inputProps={{ "aria-label": "Audit notes" }}
        />
      </Box>

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
            <FlagOutlined
              fontSize="small"
              color={flagged ? "warning" : "disabled"}
            />
            <Typography variant="body2">Flag for follow-up</Typography>
          </Box>
        }
      />

      {error ? (
        <Typography variant="caption" color="error">
          {error}
        </Typography>
      ) : null}

      <Divider />

      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Button
          size="small"
          variant="contained"
          onClick={handleSignOff}
          disabled={saveDisabled}
          startIcon={<CheckCircleOutline />}
          disableElevation
        >
          {isSignedOff ? "Update sign-off" : "Save sign-off"}
        </Button>
      </Box>
    </Box>
  );
}
