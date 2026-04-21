/**
 * Sub-components for MilestoneCurationDialog. Lives in its own
 * file to keep the dialog itself under the 500-LOC limit.
 *
 * Atlas trace:
 *   DO: DO-7986A957
 *   DI: DI-4B99678C
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { MilestoneDayResult, MissionEpisode } from "@/lib/missionControlApi";
import { getCancerTypeLabel } from "@/lib/pathwayLabels";
import { shortDate } from "./encounterTextUtils";
import { MILESTONE_OPTIONS, milestoneLabel } from "./milestoneOptions";

export type Stage = "pick" | "conflict" | "confirm" | "result";
export type Busy = "attach" | "detach" | "replace" | null;
export type ExistingLink = { episodeId: string; milestoneType: string } | null;

export interface MilestoneCurationEncounter {
  encounter_id: string;
  date: string | null;
  text: string | null;
}

export interface ConflictDescription {
  date: string;
  encounterIds: string[];
  preview: string;
}

export function snippet(text: string | null | undefined, max = 80): string {
  if (!text) return "";
  const collapsed = text.replace(/\s+/g, " ").trim();
  return collapsed.length <= max ? collapsed : `${collapsed.slice(0, max)}...`;
}

export function isoDay(value: string | null | undefined): string {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function formatEpisodeOption(ep: MissionEpisode): string {
  const label = ep.cancer_type
    ? getCancerTypeLabel(ep.cancer_type)
    : ep.condition_type ?? ep.status;
  const from = ep.referral_date ? shortDate(ep.referral_date) : "no referral";
  const to = ep.end_date ? shortDate(ep.end_date) : "open";
  return `${label} - ${from} -> ${to}`;
}

export function PickStage({
  episodeId,
  setEpisodeId,
  milestoneType,
  setMilestoneType,
  episodes,
  sameDayEncounters,
  existingLink,
}: {
  episodeId: string;
  setEpisodeId: (v: string) => void;
  milestoneType: string;
  setMilestoneType: (v: string) => void;
  episodes: MissionEpisode[];
  sameDayEncounters: MilestoneCurationEncounter[];
  existingLink: ExistingLink;
}) {
  return (
    <Stack spacing={2}>
      <TextField
        select
        size="small"
        label="Episode"
        value={episodeId}
        onChange={(e) => setEpisodeId(e.target.value)}
        disabled={Boolean(existingLink) || episodes.length === 0}
        inputProps={{ "aria-label": "Episode" }}
        data-testid="milestone-dialog-episode"
        helperText={
          existingLink
            ? "Locked to the episode that currently owns this milestone."
            : "Pick the episode this milestone belongs to."
        }
      >
        {episodes.map((ep) => (
          <MenuItem key={ep.episode_id} value={ep.episode_id}>
            {formatEpisodeOption(ep)}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        size="small"
        label="Milestone slot"
        value={milestoneType}
        onChange={(e) => setMilestoneType(e.target.value)}
        inputProps={{ "aria-label": "Milestone slot" }}
        data-testid="milestone-dialog-slot"
      >
        {MILESTONE_OPTIONS.map((opt) => (
          <MenuItem key={opt.value} value={opt.value}>
            {opt.label}
          </MenuItem>
        ))}
      </TextField>
      <Divider />
      <Typography variant="caption" color="text.secondary">
        Encounters that will be linked
      </Typography>
      <Box
        data-testid="milestone-dialog-day-encounters"
        sx={{
          border: 1,
          borderColor: "divider",
          borderRadius: 1,
          p: 1,
          maxHeight: 160,
          overflowY: "auto",
        }}
      >
        {sameDayEncounters.map((enc) => (
          <Box key={enc.encounter_id} sx={{ mb: 0.5 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block" }}
            >
              {shortDate(enc.date)}
            </Typography>
            <Typography variant="body2" sx={{ fontSize: "0.8rem" }}>
              {snippet(enc.text, 120) || "(no text)"}
            </Typography>
          </Box>
        ))}
      </Box>
    </Stack>
  );
}

export function ConflictAlert({
  conflict,
  milestoneType,
}: {
  conflict: ConflictDescription;
  milestoneType: string;
}) {
  return (
    <Alert severity="warning" data-testid="milestone-dialog-conflict">
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
        This episode already has a {milestoneLabel(milestoneType)} on{" "}
        {shortDate(conflict.date)}.
      </Typography>
      {conflict.preview && (
        <Typography variant="caption" sx={{ display: "block" }}>
          Existing text: {conflict.preview}
        </Typography>
      )}
      <Typography variant="caption" sx={{ display: "block", mt: 0.5 }}>
        Choose: keep the existing milestone, replace it with the new one
        (the old encounters will be detached), or pick a different slot
        for this day.
      </Typography>
    </Alert>
  );
}

export function ResultAlert({ result }: { result: MilestoneDayResult }) {
  return (
    <Alert
      severity={result.success ? "success" : "error"}
      data-testid="milestone-dialog-result"
    >
      {result.success
        ? `Done. ${result.succeeded.length} encounter(s) updated.`
        : `Partial update: ${result.succeeded.length} succeeded, ${result.failed.length} failed.`}
      {result.failed.length > 0 && (
        <Box sx={{ mt: 0.5 }}>
          {result.failed.map((f) => (
            <Typography
              key={f.encounter_id}
              variant="caption"
              sx={{ display: "block" }}
            >
              {f.encounter_id}: {f.error}
            </Typography>
          ))}
        </Box>
      )}
    </Alert>
  );
}

export function DialogActionsRow({
  stage,
  busy,
  existingLink,
  episodesEmpty,
  onClose,
  onProceed,
  onPickDifferent,
  onReplace,
  onConfirmAttach,
  onRemove,
}: {
  stage: Stage;
  busy: Busy;
  existingLink: ExistingLink;
  episodesEmpty: boolean;
  onClose: () => void;
  onProceed: () => void;
  onPickDifferent: () => void;
  onReplace: () => void;
  onConfirmAttach: () => void;
  onRemove: () => void;
}) {
  if (stage === "result") {
    return (
      <Button onClick={onClose} data-testid="milestone-dialog-close">
        Close
      </Button>
    );
  }
  return (
    <>
      <Button
        onClick={onClose}
        disabled={Boolean(busy)}
        data-testid="milestone-dialog-cancel"
      >
        Cancel
      </Button>
      {existingLink && stage === "pick" && (
        <Button
          color="error"
          onClick={onRemove}
          disabled={Boolean(busy)}
          startIcon={
            busy === "detach" ? (
              <CircularProgress size={14} color="inherit" />
            ) : null
          }
          data-testid="milestone-dialog-remove"
        >
          Remove from milestone
        </Button>
      )}
      {!existingLink && stage === "pick" && (
        <Button
          variant="contained"
          onClick={onProceed}
          disabled={Boolean(busy) || episodesEmpty}
          data-testid="milestone-dialog-next"
        >
          Continue
        </Button>
      )}
      {stage === "conflict" && (
        <>
          <Button
            onClick={onPickDifferent}
            disabled={Boolean(busy)}
            data-testid="milestone-dialog-pick-different-slot"
          >
            Pick a different slot
          </Button>
          <Button
            color="warning"
            variant="contained"
            onClick={onReplace}
            disabled={Boolean(busy)}
            startIcon={
              busy === "replace" ? (
                <CircularProgress size={14} color="inherit" />
              ) : null
            }
            data-testid="milestone-dialog-replace"
          >
            Replace existing
          </Button>
        </>
      )}
      {stage === "confirm" && (
        <Button
          variant="contained"
          onClick={onConfirmAttach}
          disabled={Boolean(busy)}
          startIcon={
            busy === "attach" ? (
              <CircularProgress size={14} color="inherit" />
            ) : null
          }
          data-testid="milestone-dialog-confirm-attach"
        >
          Confirm
        </Button>
      )}
    </>
  );
}
