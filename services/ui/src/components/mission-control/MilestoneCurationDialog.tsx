/**
 * MilestoneCurationDialog -- inline curation of episode milestones
 * from the EncounterCard "Add to milestone" / "Linked: <slot>"
 * buttons. Same-day grouping, multi-slot picking (DI-F5E030ED),
 * conflict warning and replace flow, and per-slot remove chips.
 *
 * Atlas trace:
 *   DO: DO-7986A957 (single-slot baseline)
 *       DO-128CB534 (multi-slot picker)
 *   DI: DI-4B99678C (single-slot baseline)
 *       DI-F5E030ED (one encounter can fill multiple slots)
 *   Risk: R-56B52B64 (same-day grouping attaches an unrelated encounter)
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
  attachEncounterDayToMultipleMilestones,
  detachEncounterDayFromMilestone,
  type MilestoneDayResult,
  type MilestoneMultiSlotResult,
  type MissionEpisode,
  type EpisodeMilestone,
} from "@/lib/missionControlApi";
import { shortDate } from "./encounterTextUtils";
import { isContextMilestone, milestoneLabel } from "./milestoneOptions";
import {
  ConflictAlert,
  DialogActionsRow,
  MultiSlotResultAlert,
  NoticeAlert,
  PickStage,
  ResultAlert,
  isoDay,
  snippet,
  type Busy,
  type ExistingLink,
  type MilestoneCurationEncounter,
  type SlotConflict,
  type SlotNotice,
  type Stage,
} from "./MilestoneCurationParts";

export type { MilestoneCurationEncounter } from "./MilestoneCurationParts";

interface Props {
  open: boolean;
  triggerEncounter: MilestoneCurationEncounter | null;
  sameDayEncounters: MilestoneCurationEncounter[];
  episodes: MissionEpisode[];
  defaultEpisodeId: string;
  // Every milestone slot the trigger encounter currently fills.
  // One encounter can hold multiple slots on the same episode
  // (DI-F5E030ED) so each is rendered as its own removable chip.
  existingLinks: ExistingLink[];
  reviewerRole: string;
  onClose: () => void;
  onChanged: () => void;
}

// The picker now opens with NO slot pre-selected AND no episode
// pre-selected (DI-74AF7AD8). The previous heuristics auto-picked
// the first un-taken pathway slot AND seeded episodeId from
// defaultEpisodeId, which made it too easy to attach an encounter
// to the wrong pathway in one click ("its too easy to addatch to
// the wrong epside"). Continue stays disabled until the curator
// explicitly picks BOTH an episode and at least one slot, so adding
// always requires a deliberate two-click choice.
// Tier-aware conflict / notice detection (DI-50C7E89C, DI-F5E030ED):
//
//   * Pathway-tier slots (first_presentation, referral, ..., the 9
//     canonical values the AI engine emits) are exclusive per
//     episode. Same slot on a different day is a hard CONFLICT and
//     the UI offers Replace (detach old + attach new) so date
//     roll-ups stay coherent.
//
//   * Context-tier slots (related_gp_visit, primary_care_
//     investigations, referral_admin, referral_sent,
//     related_specialist_visit, specialist_diagnostics,
//     related_correspondence) are descriptive tags that may
//     legitimately repeat across many days for the same episode --
//     a patient often has several primary-care investigation days
//     before referral. Same slot on a different day is therefore a
//     soft NOTICE and the UI offers Add anyway (no detach), which
//     is the fix for "milestones keep undoing themselves".
//
// Same-day same-slot is neither a conflict nor a notice -- the
// backend MERGE on (encounter, episode, slot) is idempotent and the
// "already linked" count surfaces in the result banner.
interface ConflictBuckets {
  conflicts: SlotConflict[];
  notices: SlotNotice[];
}

function detectConflicts(
  episode: MissionEpisode | undefined,
  milestoneTypes: string[],
  chosenDay: string,
  encountersById: Map<string, MilestoneCurationEncounter>
): ConflictBuckets {
  const conflicts: SlotConflict[] = [];
  const notices: SlotNotice[] = [];
  if (!episode || !chosenDay || milestoneTypes.length === 0) {
    return { conflicts, notices };
  }
  for (const mt of milestoneTypes) {
    const slotMatches = (episode.milestones ?? []).filter(
      (m: EpisodeMilestone) => m.milestone_type === mt
    );
    if (slotMatches.length === 0) continue;
    const others = slotMatches.filter((m) => isoDay(m.date) !== chosenDay);
    if (others.length === 0) continue;
    if (isContextMilestone(mt)) {
      // Context tags repeat freely. Surface a soft notice with the
      // distinct other days (deduped) so the curator knows what
      // they are adding to but no Replace path is offered.
      const otherDays = Array.from(
        new Set(others.map((m) => isoDay(m.date)))
      ).sort();
      notices.push({ milestoneType: mt, otherDays });
      continue;
    }
    const first = others[0];
    const enc = encountersById.get(String(first.encounter_id));
    conflicts.push({
      milestoneType: mt,
      date: isoDay(first.date),
      encounterIds: others.map((m) => String(m.encounter_id)),
      preview: snippet(enc?.text ?? null),
    });
  }
  return { conflicts, notices };
}

// LONG FUNCTION: orchestrates the whole multi-slot flow (pick ->
// conflict -> confirm -> result) plus the per-chip remove path.
// Splitting further would require passing every state setter
// through props and obscure the flow. ~360 LOC, well under the
// 500 file budget.
export default function MilestoneCurationDialog({
  open,
  triggerEncounter,
  sameDayEncounters,
  episodes,
  defaultEpisodeId: _defaultEpisodeId,
  existingLinks,
  reviewerRole: _reviewerRole,
  onClose,
  onChanged,
}: Props) {
  // Episode pull-down always opens blank (DI-74AF7AD8) so the
  // curator cannot silently attach to whichever pathway happened to
  // be open in the drawer. defaultEpisodeId is intentionally
  // ignored; we keep the prop in the public signature for callers
  // that still pass it.
  const [episodeId, setEpisodeId] = useState("");
  // Multi-slot state (DI-F5E030ED). The picker can attach the
  // chosen encounters to several slots in one click.
  const [milestoneTypes, setMilestoneTypes] = useState<string[]>([]);
  const [stage, setStage] = useState<Stage>("pick");
  const [busy, setBusy] = useState<Busy>(null);
  const [busyLinkKey, setBusyLinkKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [multiResult, setMultiResult] =
    useState<MilestoneMultiSlotResult | null>(null);
  // Single-slot result is only used by the per-chip remove flow,
  // which still calls the legacy day-detach helper.
  const [removeResult, setRemoveResult] = useState<MilestoneDayResult | null>(
    null
  );
  // Encounters the curator has chosen to include in this milestone.
  // Mitigates R-56B52B64: explicit per-encounter selection. Default
  // seed = the encounter the curator clicked on.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Reset every time the dialog opens against a new trigger.
  useEffect(() => {
    if (!open) return;
    // Always blank on open (DI-74AF7AD8) -- defaultEpisodeId is
    // ignored on purpose so the curator picks the pathway
    // deliberately every time.
    setEpisodeId("");
    setMilestoneTypes([]);
    setStage("pick");
    setBusy(null);
    setBusyLinkKey(null);
    setError(null);
    setMultiResult(null);
    setRemoveResult(null);
    const seed = new Set<string>();
    if (triggerEncounter) seed.add(String(triggerEncounter.encounter_id));
    setSelectedIds(seed);
  }, [open, triggerEncounter, existingLinks]);

  // When the reviewer changes episode mid-flow, clear the slot
  // selection. The curator must re-pick deliberately for the new
  // episode -- we never auto-pick, see DI-74AF7AD8.
  const handleEpisodeChange = (next: string) => {
    setEpisodeId(next);
    setMilestoneTypes([]);
  };

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectAll = () =>
    setSelectedIds(
      new Set(sameDayEncounters.map((e) => String(e.encounter_id)))
    );
  const clearAll = () => setSelectedIds(new Set());
  const selectedList = sameDayEncounters
    .map((e) => String(e.encounter_id))
    .filter((id) => selectedIds.has(id));
  const selectedCount = selectedList.length;

  const chosenDay = isoDay(triggerEncounter?.date);
  const encountersById = useMemo(() => {
    const map = new Map<string, MilestoneCurationEncounter>();
    sameDayEncounters.forEach((e) => map.set(String(e.encounter_id), e));
    return map;
  }, [sameDayEncounters]);
  const targetEpisode = episodes.find((e) => e.episode_id === episodeId);
  const { conflicts, notices } = useMemo(
    () =>
      detectConflicts(targetEpisode, milestoneTypes, chosenDay, encountersById),
    [targetEpisode, milestoneTypes, chosenDay, encountersById]
  );

  // Pathway conflicts win over context notices in routing -- the
  // Replace flow lists every pathway slot needing detach, and the
  // notice slots ride along on the subsequent multi-slot attach
  // without their own ceremony. DI-50C7E89C, DI-F5E030ED.
  const handleProceed = () => {
    if (conflicts.length > 0) {
      setStage("conflict");
      return;
    }
    if (notices.length > 0) {
      setStage("notice");
      return;
    }
    setStage("confirm");
  };

  const runAttach = async () => {
    if (!chosenDay || selectedList.length === 0 || milestoneTypes.length === 0)
      return;
    setBusy("attach");
    setError(null);
    try {
      const res = await attachEncounterDayToMultipleMilestones({
        episodeId,
        milestoneTypes,
        date: chosenDay,
        encounterIds: selectedList,
      });
      setMultiResult(res);
      setStage("result");
      if (res.allSucceeded) onChanged();
      else if (res.failed === 0) onChanged();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not attach the milestone."
      );
    } finally {
      setBusy(null);
    }
  };

  // Replace runs detach-then-attach for every conflicting slot, then
  // attaches the non-conflicting slots in the same multi-slot call.
  // If a detach fails the whole replace aborts so the graph stays
  // coherent.
  const runReplace = async () => {
    if (conflicts.length === 0 || !chosenDay || selectedList.length === 0)
      return;
    setBusy("replace");
    setError(null);
    try {
      for (const c of conflicts) {
        const detachRes = await detachEncounterDayFromMilestone({
          episodeId,
          encounterIds: c.encounterIds,
          milestoneType: c.milestoneType,
        });
        if (!detachRes.success) {
          setError(
            `Detach of the existing ${milestoneLabel(c.milestoneType)} failed for ${detachRes.failed.length} encounter(s).`
          );
          setBusy(null);
          return;
        }
      }
      const attachRes = await attachEncounterDayToMultipleMilestones({
        episodeId,
        milestoneTypes,
        date: chosenDay,
        encounterIds: selectedList,
      });
      setMultiResult(attachRes);
      setStage("result");
      if (attachRes.allSucceeded) onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Replace failed.");
    } finally {
      setBusy(null);
    }
  };

  const handleRemoveExistingLink = async (link: ExistingLink) => {
    if (!triggerEncounter) return;
    const linkKey = `${link.episodeId}:${link.milestoneType}`;
    setBusy("detach");
    setBusyLinkKey(linkKey);
    setError(null);
    try {
      const res = await detachEncounterDayFromMilestone({
        episodeId: link.episodeId,
        encounterIds: [String(triggerEncounter.encounter_id)],
        milestoneType: link.milestoneType,
      });
      setRemoveResult({
        ...res,
        milestone_type: link.milestoneType,
        date: chosenDay,
      });
      setMultiResult(null);
      setStage("result");
      if (res.success) onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed.");
    } finally {
      setBusy(null);
      setBusyLinkKey(null);
    }
  };

  const titleText =
    existingLinks.length === 0
      ? "Add encounter day to milestone"
      : existingLinks.length === 1
      ? `Linked as ${milestoneLabel(existingLinks[0].milestoneType)}`
      : `Linked as ${existingLinks
          .map((l) => milestoneLabel(l.milestoneType))
          .join(" + ")}`;

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      fullWidth
      maxWidth="sm"
      data-testid="milestone-curation-dialog"
    >
      <DialogTitle>{titleText}</DialogTitle>
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
                  ({selectedCount} of {sameDayEncounters.length}{" "}
                  {sameDayEncounters.length === 1 ? "encounter" : "encounters"}{" "}
                  on this day selected)
                </Typography>
              </Typography>
            </Box>
            {stage === "pick" && (
              <PickStage
                episodeId={episodeId}
                setEpisodeId={handleEpisodeChange}
                milestoneTypes={milestoneTypes}
                setMilestoneTypes={setMilestoneTypes}
                episodes={episodes}
                sameDayEncounters={sameDayEncounters}
                existingLinks={existingLinks}
                onRemoveExistingLink={handleRemoveExistingLink}
                busyLinkKey={busyLinkKey}
                selectedIds={selectedIds}
                toggleSelected={toggleSelected}
                selectAll={selectAll}
                clearAll={clearAll}
              />
            )}
            {stage === "conflict" && conflicts.length > 0 && (
              <ConflictAlert conflicts={conflicts} />
            )}
            {stage === "notice" && notices.length > 0 && (
              <NoticeAlert notices={notices} />
            )}
            {stage === "confirm" && (
              <Alert severity="info" data-testid="milestone-dialog-confirm">
                Linking {selectedCount}{" "}
                {selectedCount === 1 ? "encounter" : "encounters"} on{" "}
                {shortDate(chosenDay)} to{" "}
                <strong>
                  {milestoneTypes.map((mt) => milestoneLabel(mt)).join(" + ")}
                </strong>
                {milestoneTypes.length > 1
                  ? ` (${milestoneTypes.length} slots)`
                  : ""}
                .
              </Alert>
            )}
            {stage === "result" && multiResult && (
              <MultiSlotResultAlert result={multiResult} />
            )}
            {stage === "result" && !multiResult && removeResult && (
              <ResultAlert result={removeResult} />
            )}
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
          episodesEmpty={episodes.length === 0}
          noEpisode={!episodeId}
          selectedCount={selectedCount}
          slotCount={milestoneTypes.length}
          onClose={onClose}
          onProceed={handleProceed}
          onPickDifferent={() => setStage("pick")}
          onReplace={runReplace}
          onConfirmAttach={runAttach}
        />
      </DialogActions>
    </Dialog>
  );
}
