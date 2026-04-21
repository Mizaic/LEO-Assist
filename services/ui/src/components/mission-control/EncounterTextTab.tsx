/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-146D93D0
 *   Also implements: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-146D93D0")
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { MissionEpisode } from "@/lib/missionControlApi";
import { useEpisodeEncounterLocks } from "./useEpisodeEncounterLocks";
import { useEncounterCodedLinks } from "./useEncounterCodedLinks";
import { padRange } from "./encounterTextRange";
import ConfirmDialog from "@/components/ConfirmDialog";
import { sortByIsoDateAsc } from "@/lib/dateSort";
import EncounterCard from "./EncounterCard";
import EncounterTimelineScrubber from "./EncounterTimelineScrubber";
import MilestoneJumpChips from "./MilestoneJumpChips";
import MilestoneCurationDialog from "./MilestoneCurationDialog";
import { shortDate } from "./encounterTextUtils";
import { applyCommonFilters } from "./encounterFilters";
import { useEncounterLoad, type Encounter } from "./useEncounterLoad";
import { useEncounterRecode } from "./useEncounterRecode";
import {
  buildMilestoneLookup,
  useMilestoneCuration,
} from "./useMilestoneCuration";

interface Props {
  patientId: string;
  episode: MissionEpisode;
  /** Sibling episodes for this patient. The MilestoneCurationDialog
   *  picker offers any of these as the milestone target so a
   *  reviewer can re-attach an encounter to a different episode
   *  without leaving the drawer. Defaults to [episode]. */
  episodes?: MissionEpisode[];
  /** Reviewer role; threaded through to the curation dialog so its
   *  audit-event payload picks up the right actor. */
  reviewerRole?: string;
  /** Bubbles a coding-change signal so the drawer refreshes
   *  sibling tabs (CodedDataTab, AuditTrailTab) live. */
  onCodingChanged?: () => void;
}

export default function EncounterTextTab({
  patientId,
  episode,
  episodes,
  reviewerRole = "developer",
  onCodingChanged,
}: Props) {
  const { encounters, loading, error, refresh } = useEncounterLoad(patientId);
  const [codedOnly, setCodedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const codedLinks = useEncounterCodedLinks(patientId);
  const {
    codedByEncounter,
    codingErrorByEncounter,
    codingLoadingFor,
    fetchFor: fetchCodesForEncounter,
    invalidate: invalidateCodedFor,
    clearLinks: clearCodedFor,
    reset: resetCodedCache,
  } = codedLinks;
  const [collapsedEncounters, setCollapsedEncounters] = useState<Record<string, boolean>>({});
  const [confirmResetEncounterId, setConfirmResetEncounterId] = useState<string | null>(null);
  const [focusedEncounterId, setFocusedEncounterId] = useState<string | null>(null);
  const [visibleEncounterId, setVisibleEncounterId] = useState<string | null>(null);
  const [timelineRange, setTimelineRange] = useState<
    { fromMs: number; toMs: number } | null
  >(null);
  const encounterRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const encounterLocks = useEpisodeEncounterLocks(episode.episode_id);
  const dialogEpisodes = useMemo(
    () => (episodes && episodes.length > 0 ? episodes : [episode]),
    [episodes, episode]
  );
  const milestoneLookup = useMemo(
    () => buildMilestoneLookup(dialogEpisodes),
    [dialogEpisodes]
  );
  const curate = useMilestoneCuration(encounters);

  const defaultRangeAppliedRef = useRef<string | null>(null);

  useEffect(() => {
    resetCodedCache();
    setCollapsedEncounters({});
    defaultRangeAppliedRef.current = null;
  }, [patientId, episode.episode_id, resetCodedCache]);

  // Stabilise milestones/linked_encounter_ids so downstream memos and
  // effects do not refire when the field is undefined (`?? []` would
  // create a fresh array each render). This was a contributor to
  // "Maximum update depth exceeded" inside the timeline scrubber.
  const milestones = useMemo(
    () => episode.milestones ?? [],
    [episode.milestones]
  );
  const linkedEncounterIds = useMemo(() => {
    const ids: string[] = [];
    (episode.linked_encounter_ids ?? []).forEach((id) => ids.push(String(id)));
    milestones.forEach((m) => {
      if (m.encounter_id) ids.push(String(m.encounter_id));
    });
    return new Set(ids);
  }, [episode.linked_encounter_ids, milestones]);
  const from = episode.referral_date ?? null;
  const to = episode.end_date ?? null;

  // Patient-history bounds (used for default brush padding).
  const { fullMinMs, fullMaxMs } = useMemo(() => {
    let lo = Number.POSITIVE_INFINITY;
    let hi = Number.NEGATIVE_INFINITY;
    encounters.forEach((enc) => {
      const t = Date.parse(enc.date ?? "");
      if (!Number.isFinite(t)) return;
      if (t < lo) lo = t;
      if (t > hi) hi = t;
    });
    return { fullMinMs: lo, fullMaxMs: hi };
  }, [encounters]);

  // Tight episode footprint: min/max dates of episode-linked
  // encounters, falling back to episode.referral_date / end_date.
  // Returned as primitive numbers so the values stay stable across
  // renders even when the upstream arrays change reference.
  const episodeLinkedFromMs = useMemo(() => {
    let lo = Number.POSITIVE_INFINITY;
    encounters.forEach((enc) => {
      if (!linkedEncounterIds.has(String(enc.encounter_id))) return;
      const t = Date.parse(enc.date ?? "");
      if (!Number.isFinite(t)) return;
      if (t < lo) lo = t;
    });
    if (Number.isFinite(lo)) return lo;
    const fb = Date.parse(from ?? "");
    return Number.isFinite(fb) ? fb : Number.NaN;
  }, [encounters, linkedEncounterIds, from]);
  const episodeLinkedToMs = useMemo(() => {
    let hi = Number.NEGATIVE_INFINITY;
    encounters.forEach((enc) => {
      if (!linkedEncounterIds.has(String(enc.encounter_id))) return;
      const t = Date.parse(enc.date ?? "");
      if (!Number.isFinite(t)) return;
      if (t > hi) hi = t;
    });
    if (Number.isFinite(hi)) return hi;
    const ft = Date.parse(to ?? "");
    return Number.isFinite(ft) ? ft : Number.NaN;
  }, [encounters, linkedEncounterIds, to]);

  // On first encounter load (or episode switch) initialise the brush
  // to the padded episode window so the list opens already focused
  // on the episode plus a bit of context.
  useEffect(() => {
    if (loading) return;
    if (encounters.length === 0) return;
    if (!Number.isFinite(episodeLinkedFromMs)) return;
    if (!Number.isFinite(episodeLinkedToMs)) return;
    if (defaultRangeAppliedRef.current === episode.episode_id) return;
    const padded = padRange(
      episodeLinkedFromMs,
      episodeLinkedToMs,
      fullMinMs,
      fullMaxMs
    );
    if (!padded) return;
    setTimelineRange(padded);
    defaultRangeAppliedRef.current = episode.episode_id;
  }, [
    loading,
    encounters.length,
    episodeLinkedFromMs,
    episodeLinkedToMs,
    fullMinMs,
    fullMaxMs,
    episode.episode_id,
  ]);

  const visibleEncounters = useMemo(() => {
    const filtered = applyCommonFilters(encounters, {
      codedOnly,
      search,
      timelineRange,
    });
    return sortByIsoDateAsc(filtered, (e) => e.date ?? null);
  }, [encounters, codedOnly, search, timelineRange]);

  // Search match overlay for the histogram (DI-15E0094F). Only the
  // free-text search affects which bars are highlighted -- the
  // Coded-only switch and the brush window stay independent so the
  // reviewer can see "where in the patient's life is this term"
  // without the brush hiding any bars. `undefined` means "no
  // search active"; an empty Set means "search active but zero
  // matches anywhere".
  const searchMatchEncounterIds = useMemo<Set<string> | undefined>(() => {
    if (!search.trim()) return undefined;
    const matched = applyCommonFilters(encounters, {
      codedOnly: false,
      search,
      timelineRange: null,
    });
    return new Set(matched.map((e) => String(e.encounter_id)));
  }, [encounters, search]);

  useEffect(() => {
    if (loading) return;
    visibleEncounters.forEach((enc) => {
      if ((enc.coded_count ?? 0) === 0) return;
      void fetchCodesForEncounter(String(enc.encounter_id));
    });
  }, [visibleEncounters, loading, fetchCodesForEncounter]);

  const handleRecodeCleared = useCallback(
    (encounterId: string) => {
      clearCodedFor(encounterId);
    },
    [clearCodedFor]
  );
  const recode = useEncounterRecode({
    patientId,
    refresh,
    onCleared: handleRecodeCleared,
  });
  const handleResetAndRecode = (encounterId: string) => {
    setConfirmResetEncounterId(null);
    void recode.start(encounterId);
  };

  const jumpToEncounter = useCallback((encounterId: string) => {
    setCodedOnly(false);
    setSearch("");
    setTimelineRange(null);
    setCollapsedEncounters((prev) => ({ ...prev, [encounterId]: false }));
    setFocusedEncounterId(encounterId);
    setVisibleEncounterId(encounterId);
  }, []);

  const handleTimelineRangeChange = useCallback(
    (fromMs: number | null, toMs: number | null) => {
      setTimelineRange(
        fromMs == null || toMs == null ? null : { fromMs, toMs }
      );
    },
    []
  );

  useEffect(() => {
    if (!focusedEncounterId) return;
    const target = encounterRefs.current[focusedEncounterId];
    if (!target) return;
    if (typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    const timer = window.setTimeout(() => setFocusedEncounterId(null), 2200);
    return () => window.clearTimeout(timer);
  }, [focusedEncounterId, codedOnly, search, visibleEncounters.length]);

  const allVisibleIds = useMemo(
    () => visibleEncounters.map((e) => String(e.encounter_id)),
    [visibleEncounters]
  );
  // Stable key so the IntersectionObserver effect does not tear down
  // and recreate when `visibleEncounters` gets a fresh reference.
  const allVisibleIdsKey = allVisibleIds.join("|");

  const anyExpanded = allVisibleIds.some((id) => !collapsedEncounters[id]);
  const anyCollapsed = allVisibleIds.some((id) => !!collapsedEncounters[id]);

  const collapseAll = () =>
    setCollapsedEncounters((prev) => ({
      ...prev,
      ...Object.fromEntries(allVisibleIds.map((id) => [id, true])),
    }));
  const expandAll = () =>
    setCollapsedEncounters((prev) => ({
      ...prev,
      ...Object.fromEntries(allVisibleIds.map((id) => [id, false])),
    }));

  useEffect(() => {
    if (typeof window === "undefined" || !("IntersectionObserver" in window)) return;
    const ids = allVisibleIdsKey ? allVisibleIdsKey.split("|") : [];
    const candidates = ids
      .map((id) => encounterRefs.current[id])
      .filter((node): node is HTMLDivElement => Boolean(node));
    if (candidates.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const top = visible[0]?.target as HTMLElement | undefined;
        const id = top?.dataset?.encounterCardId;
        if (id) setVisibleEncounterId(id);
      },
      { threshold: [0.25, 0.5, 0.75], rootMargin: "-30% 0px -50% 0px" }
    );
    candidates.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [allVisibleIdsKey]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress aria-label="Loading encounter text" />
      </Box>
    );
  }
  if (error) return <Alert severity="error">{error}</Alert>;
  if (!encounters.length) {
    return <Alert severity="info">No encounter records found for this patient.</Alert>;
  }

  const renderCard = (enc: Encounter) => {
    const encounterKey = String(enc.encounter_id);
    const isExpanded = !collapsedEncounters[encounterKey];
    const isLinked = linkedEncounterIds.has(encounterKey);
    return (
      <EncounterCard
        key={encounterKey}
        ref={(node) => {
          encounterRefs.current[encounterKey] = node;
        }}
        enc={enc}
        patientId={patientId}
        search={search}
        isExpanded={isExpanded}
        isFocused={focusedEncounterId === encounterKey}
        isLinkedToEpisode={isLinked}
        isResetting={recode.resettingEncounterId === encounterKey}
        codingLoading={!!codingLoadingFor[encounterKey]}
        codingLinks={codedByEncounter[encounterKey] ?? []}
        codingError={codingErrorByEncounter[encounterKey]}
        lockSummary={encounterLocks[encounterKey] ?? null}
        currentMilestoneType={
          milestoneLookup.get(encounterKey)?.milestoneType ?? null
        }
        onCurateMilestone={() => curate.open(enc)}
        onToggle={() =>
          setCollapsedEncounters((prev) => ({ ...prev, [encounterKey]: isExpanded }))
        }
        onRequestReset={() => setConfirmResetEncounterId(encounterKey)}
        onCodingChanged={() => {
          // Invalidate the cached coded links for this encounter so the
          // next render re-fetches from /coded-links and shows the
          // post-edit live state. Then bubble to the drawer so
          // sibling tabs refetch too. See DI-LEO-AI-221.
          invalidateCodedFor(encounterKey);
          void fetchCodesForEncounter(encounterKey);
          onCodingChanged?.();
        }}
      />
    );
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="caption" color="text.secondary">
        The patient timeline below shows every encounter. Drag the focus band to widen or narrow which encounters appear in the list.
      </Typography>
      {recode.recodeMessage && (
        <Alert
          severity={
            recode.recodeJobState === "failed"
              ? "error"
              : recode.recodeJobState === "running" ||
                  recode.recodeJobState === "queued"
                ? "info"
                : "success"
          }
        >
          {recode.recodeMessage}
        </Alert>
      )}
      <MilestoneJumpChips
        milestones={milestones}
        focusedEncounterId={focusedEncounterId}
        onJump={jumpToEncounter}
      />

      <EncounterTimelineScrubber
        encounters={encounters}
        linkedEncounterIds={linkedEncounterIds}
        episodeFrom={from}
        episodeTo={to}
        milestones={milestones}
        activeEncounterId={focusedEncounterId ?? visibleEncounterId}
        onJumpToEncounter={jumpToEncounter}
        visibleFromMs={timelineRange?.fromMs ?? null}
        visibleToMs={timelineRange?.toMs ?? null}
        onVisibleRangeChange={handleTimelineRangeChange}
        searchMatchEncounterIds={searchMatchEncounterIds}
      />
      {timelineRange && (
        <Alert
          severity="info"
          variant="outlined"
          data-testid="timeline-filter-banner"
          sx={{ py: 0.25 }}
          action={
            <Button
              size="small"
              color="inherit"
              onClick={() => setTimelineRange(null)}
            >
              Clear
            </Button>
          }
        >
          Encounters filtered to timeline window {shortDate(new Date(timelineRange.fromMs).toISOString())} - {shortDate(new Date(timelineRange.toMs).toISOString())}
        </Alert>
      )}

      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={codedOnly}
              onChange={(_, v) => setCodedOnly(v)}
            />
          }
          label={<Typography variant="caption">Coded only</Typography>}
        />
        {anyExpanded && (
          <Button size="small" variant="text" sx={{ ml: "auto" }} onClick={collapseAll}>
            Collapse all
          </Button>
        )}
        {anyCollapsed && (
          <Button size="small" variant="text" sx={{ ml: anyExpanded ? 0 : "auto" }} onClick={expandAll}>
            Expand all
          </Button>
        )}
      </Box>
      <TextField
        size="small"
        label="Search text in shown encounters"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {visibleEncounters.length === 0 && (
        <Alert severity="info">
          No encounters match this filter. Drag the focus band wider or clear Coded only / Search to see more.
        </Alert>
      )}
      {visibleEncounters.map((enc) => renderCard(enc))}

      {confirmResetEncounterId && (
        <ConfirmDialog
          title="Reset and recode this encounter?"
          body="This clears coding created for this encounter, removes stale review artefacts, and queues fresh coding for this encounter."
          confirmLabel="Reset and recode"
          variant="danger"
          onCancel={() => setConfirmResetEncounterId(null)}
          onConfirm={() => void handleResetAndRecode(confirmResetEncounterId)}
        />
      )}
      <MilestoneCurationDialog
        open={Boolean(curate.target)}
        triggerEncounter={curate.triggerEncounter}
        sameDayEncounters={curate.sameDayEncounters}
        episodes={dialogEpisodes}
        defaultEpisodeId={episode.episode_id}
        existingLink={
          curate.target
            ? milestoneLookup.get(String(curate.target.encounter_id)) ?? null
            : null
        }
        reviewerRole={reviewerRole}
        onClose={curate.close}
        onChanged={() => {
          curate.close();
          refresh();
          onCodingChanged?.();
        }}
      />
    </Box>
  );
}
