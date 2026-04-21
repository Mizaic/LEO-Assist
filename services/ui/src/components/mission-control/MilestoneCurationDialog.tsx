/**
 * MilestoneCurationDialog -- inline curation of episode milestones
 * from the EncounterCard "Add to milestone" / "Linked: <slot>"
 * buttons. Same-day grouping, conflict warning, and replace flow
 * live here so the existing per-encounter attach / detach endpoints
 * stay unchanged for v1.
 *
 * Atlas trace:
 *   DO: DO-7986A957
 *   DI: DI-4B99678C
 *   Risk: R-56B52B64 (same-day grouping attaches an unrelated encounter)
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7986A957")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  attachEncounterDayToMilestone,
  detachEncounterDayFromMilestone,
  type MilestoneDayResult,
  type MissionEpisode,
  type EpisodeMilestone,
} from "@/lib/missionControlApi";
import { shortDate } from "./encounterTextUtils";
import { milestoneLabel } from "./milestoneOptions";
import {
  ConflictAlert,
  DialogActionsRow,
  PickStage,
  ResultAlert,
  isoDay,
  snippet,
  type Busy,
  type ConflictDescription,
  type ExistingLink,
  type MilestoneCurationEncounter,
  type Stage,
} from "./MilestoneCurationParts";

export type { MilestoneCurationEncounter } from "./MilestoneCurationParts";

interface Props {
  open: boolean;
  triggerEncounter: MilestoneCurationEncounter | null;
  sameDayEncounters: MilestoneCurationEncounter[];
  episodes: MissionEpisode[];
  defaultEpisodeId: string;
  // When the trigger encounter is already linked to the focused
  // episode, this is the milestone slot it currently fills. The
  // dialog opens in "manage existing link" mode and offers a
  // Remove button.
  existingLink: ExistingLink;
  reviewerRole: string;
  onClose: () => void;
  onChanged: () => void;
}

function detectConflict(
  episode: MissionEpisode | undefined,
  milestoneType: string,
  chosenDay: string,
  encountersById: Map<string, MilestoneCurationEncounter>
): ConflictDescription | null {
  if (!episode || !milestoneType || !chosenDay) return null;
  const slotMatches = (episode.milestones ?? []).filter(
    (m: EpisodeMilestone) => m.milestone_type === milestoneType
  );
  if (slotMatches.length === 0) return null;
  const others = slotMatches.filter((m) => isoDay(m.date) !== chosenDay);
  if (others.length === 0) return null;
  const first = others[0];
  const enc = encountersById.get(String(first.encounter_id));
  return {
    date: isoDay(first.date),
    encounterIds: others.map((m) => String(m.encounter_id)),
    preview: snippet(enc?.text ?? null),
  };
}

export default function MilestoneCurationDialog({
  open,
  triggerEncounter,
  sameDayEncounters,
  episodes,
  defaultEpisodeId,
  existingLink,
  reviewerRole: _reviewerRole,
  onClose,
  onChanged,
}: Props) {
  const [episodeId, setEpisodeId] = useState(defaultEpisodeId);
  const [milestoneType, setMilestoneType] = useState<string>(
    existingLink?.milestoneType ?? "presentation"
  );
  const [stage, setStage] = useState<Stage>("pick");
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MilestoneDayResult | null>(null);

  useEffect(() => {
    if (!open) return;
    setEpisodeId(existingLink?.episodeId ?? defaultEpisodeId);
    setMilestoneType(existingLink?.milestoneType ?? "presentation");
    setStage("pick");
    setBusy(null);
    setError(null);
    setResult(null);
  }, [open, defaultEpisodeId, existingLink?.episodeId, existingLink?.milestoneType]);

  const chosenDay = isoDay(triggerEncounter?.date);
  const encountersById = useMemo(() => {
    const map = new Map<string, MilestoneCurationEncounter>();
    sameDayEncounters.forEach((e) => map.set(String(e.encounter_id), e));
    return map;
  }, [sameDayEncounters]);
  const targetEpisode = episodes.find((e) => e.episode_id === episodeId);
  const conflict = useMemo(
    () => detectConflict(targetEpisode, milestoneType, chosenDay, encountersById),
    [targetEpisode, milestoneType, chosenDay, encountersById]
  );

  const handleProceed = () => {
    if (conflict) {
      setStage("conflict");
      return;
    }
    setStage("confirm");
  };

  const runAttach = async () => {
    if (!chosenDay) return;
    setBusy("attach");
    setError(null);
    try {
      const dayIds = sameDayEncounters.map((e) => String(e.encounter_id));
      const res = await attachEncounterDayToMilestone({
        episodeId,
        milestoneType,
        date: chosenDay,
        encounterIds: dayIds,
      });
      setResult(res);
      setStage("result");
      if (res.success) onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not attach the day group.");
    } finally {
      setBusy(null);
    }
  };

  const runReplace = async () => {
    if (!conflict || !chosenDay) return;
    setBusy("replace");
    setError(null);
    try {
      const detachRes = await detachEncounterDayFromMilestone({
        episodeId,
        encounterIds: conflict.encounterIds,
      });
      if (!detachRes.success) {
        setError(
          `Detach of the existing milestone failed for ${detachRes.failed.length} encounter(s).`
        );
        setBusy(null);
        return;
      }
      const attachRes = await attachEncounterDayToMilestone({
        episodeId,
        milestoneType,
        date: chosenDay,
        encounterIds: sameDayEncounters.map((e) => String(e.encounter_id)),
      });
      setResult(attachRes);
      setStage("result");
      if (attachRes.success) onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Replace failed.");
    } finally {
      setBusy(null);
    }
  };

  const runRemove = async () => {
    if (!existingLink || !chosenDay) return;
    setBusy("detach");
    setError(null);
    try {
      const dayIds = sameDayEncounters.map((e) => String(e.encounter_id));
      const res = await detachEncounterDayFromMilestone({
        episodeId: existingLink.episodeId,
        encounterIds: dayIds,
      });
      setResult({
        ...res,
        milestone_type: existingLink.milestoneType,
        date: chosenDay,
      });
      setStage("result");
      if (res.success) onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      fullWidth
      maxWidth="sm"
      data-testid="milestone-curation-dialog"
    >
      <DialogTitle>
        {existingLink
          ? `Linked as ${milestoneLabel(existingLink.milestoneType)}`
          : "Add encounter day to milestone"}
      </DialogTitle>
      <DialogContent dividers>
        {triggerEncounter ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Encounter day
              </Typography>
              <Typography variant="body2" data-testid="milestone-dialog-day">
                {chosenDay ? shortDate(chosenDay) : "(no date)"}
                <Typography
                  component="span"
                  variant="caption"
                  color="text.secondary"
                  sx={{ ml: 1 }}
                >
                  ({sameDayEncounters.length}{" "}
                  {sameDayEncounters.length === 1 ? "encounter" : "encounters"} on
                  this day)
                </Typography>
              </Typography>
            </Box>
            {stage === "pick" && (
              <PickStage
                episodeId={episodeId}
                setEpisodeId={setEpisodeId}
                milestoneType={milestoneType}
                setMilestoneType={setMilestoneType}
                episodes={episodes}
                sameDayEncounters={sameDayEncounters}
                existingLink={existingLink}
              />
            )}
            {stage === "conflict" && conflict && (
              <ConflictAlert conflict={conflict} milestoneType={milestoneType} />
            )}
            {stage === "confirm" && (
              <Alert severity="info" data-testid="milestone-dialog-confirm">
                Linking {sameDayEncounters.length}{" "}
                {sameDayEncounters.length === 1 ? "encounter" : "encounters"} on{" "}
                {shortDate(chosenDay)} as{" "}
                <strong>{milestoneLabel(milestoneType)}</strong>.
              </Alert>
            )}
            {stage === "result" && result && <ResultAlert result={result} />}
            {error && (
              <Alert severity="error" data-testid="milestone-dialog-error">
                {error}
              </Alert>
            )}
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary">
            No encounter selected.
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <DialogActionsRow
          stage={stage}
          busy={busy}
          existingLink={existingLink}
          episodesEmpty={episodes.length === 0}
          onClose={onClose}
          onProceed={handleProceed}
          onPickDifferent={() => setStage("pick")}
          onReplace={runReplace}
          onConfirmAttach={runAttach}
          onRemove={runRemove}
        />
      </DialogActions>
    </Dialog>
  );
}
