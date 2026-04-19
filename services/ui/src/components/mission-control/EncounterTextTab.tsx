"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import type { MissionEpisode } from "@/lib/missionControlApi";
import { fetchEncounterCodedLinks } from "@/lib/api";
import type { CodedLink } from "@/lib/types";
import ConfirmDialog from "@/components/ConfirmDialog";
import { sortByIsoDateAsc } from "@/lib/dateSort";
import EncounterCard from "./EncounterCard";
import EncounterTimelineScrubber from "./EncounterTimelineScrubber";
import { MILESTONE_LABELS, shortDate } from "./encounterTextUtils";
import { applyCommonFilters } from "./encounterFilters";
import { useEncounterLoad, type Encounter } from "./useEncounterLoad";
import { useEncounterRecode } from "./useEncounterRecode";

interface Props {
  patientId: string;
  episode: MissionEpisode;
}

interface MilestoneJump {
  key: string;
  encounterId: string;
  label: string;
  date: string | null;
}

// Pads the episode-linked window by ~10% of the patient's full
// history span on each side so the default brush opens with a bit of
// "before / after" context visible. Clamped to the patient range.
function padRange(
  fromMs: number,
  toMs: number,
  fullMinMs: number,
  fullMaxMs: number
): { fromMs: number; toMs: number } | null {
  if (
    !Number.isFinite(fromMs) ||
    !Number.isFinite(toMs) ||
    !Number.isFinite(fullMinMs) ||
    !Number.isFinite(fullMaxMs)
  ) {
    return null;
  }
  const span = Math.max(0, fullMaxMs - fullMinMs);
  const pad = span > 0 ? span * 0.1 : 0;
  return {
    fromMs: Math.max(fullMinMs, fromMs - pad),
    toMs: Math.min(fullMaxMs, toMs + pad),
  };
}

export default function EncounterTextTab({ patientId, episode }: Props) {
  const { encounters, loading, error, refresh } = useEncounterLoad(patientId);
  const [codedOnly, setCodedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [codedByEncounter, setCodedByEncounter] = useState<Record<string, CodedLink[]>>({});
  const [codingErrorByEncounter, setCodingErrorByEncounter] = useState<
    Record<string, string>
  >({});
  const [codingLoadingFor, setCodingLoadingFor] = useState<Record<string, boolean>>({});
  const [collapsedEncounters, setCollapsedEncounters] = useState<Record<string, boolean>>({});
  const [confirmResetEncounterId, setConfirmResetEncounterId] = useState<string | null>(null);
  const [focusedEncounterId, setFocusedEncounterId] = useState<string | null>(null);
  const [visibleEncounterId, setVisibleEncounterId] = useState<string | null>(null);
  const [timelineRange, setTimelineRange] = useState<
    { fromMs: number; toMs: number } | null
  >(null);
  const encounterRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const loadedRef = useRef<Set<string>>(new Set());
  const loadingRef = useRef<Set<string>>(new Set());
  const defaultRangeAppliedRef = useRef<string | null>(null);

  useEffect(() => {
    loadedRef.current = new Set();
    loadingRef.current = new Set();
    setCodedByEncounter({});
    setCodingErrorByEncounter({});
    setCodingLoadingFor({});
    setCollapsedEncounters({});
    defaultRangeAppliedRef.current = null;
  }, [patientId, episode.episode_id]);

  const fetchCodesForEncounter = useCallback(
    async (encounterId: string) => {
      const key = String(encounterId);
      if (loadedRef.current.has(key) || loadingRef.current.has(key)) return;
      loadingRef.current.add(key);
      setCodingLoadingFor((prev) => ({ ...prev, [key]: true }));
      setCodingErrorByEncounter((prev) => ({ ...prev, [key]: "" }));
      try {
        const links = await fetchEncounterCodedLinks(patientId, key);
        loadedRef.current.add(key);
        setCodedByEncounter((prev) => ({ ...prev, [key]: links }));
      } catch (e) {
        setCodingErrorByEncounter((prev) => ({
          ...prev,
          [key]:
            e instanceof Error
              ? e.message
              : "Could not load coded concepts for this encounter.",
        }));
      } finally {
        loadingRef.current.delete(key);
        setCodingLoadingFor((prev) => ({ ...prev, [key]: false }));
      }
    },
    [patientId]
  );

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

  useEffect(() => {
    if (loading) return;
    visibleEncounters.forEach((enc) => {
      if ((enc.coded_count ?? 0) === 0) return;
      void fetchCodesForEncounter(String(enc.encounter_id));
    });
  }, [visibleEncounters, loading, fetchCodesForEncounter]);

  const handleRecodeCleared = useCallback((encounterId: string) => {
    setCodedByEncounter((prev) => ({ ...prev, [encounterId]: [] }));
    loadedRef.current.delete(String(encounterId));
  }, []);
  const recode = useEncounterRecode({
    patientId,
    refresh,
    onCleared: handleRecodeCleared,
  });
  const handleResetAndRecode = (encounterId: string) => {
    setConfirmResetEncounterId(null);
    void recode.start(encounterId);
  };

  const milestoneJumps = useMemo<MilestoneJump[]>(() => {
    const rows = milestones
      .filter((m) => Boolean(m.encounter_id))
      .map((m, idx) => ({
        key: `${m.milestone_type}-${m.encounter_id}-${idx}`,
        encounterId: String(m.encounter_id),
        label: MILESTONE_LABELS[m.milestone_type] ?? m.milestone_type.replaceAll("_", " "),
        date: m.date ?? null,
      }));
    return rows.sort((a, b) => {
      const ta = Date.parse(a.date ?? "");
      const tb = Date.parse(b.date ?? "");
      if (!Number.isFinite(ta)) return 1;
      if (!Number.isFinite(tb)) return -1;
      return ta - tb;
    });
  }, [milestones]);

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
        onToggle={() =>
          setCollapsedEncounters((prev) => ({ ...prev, [encounterKey]: isExpanded }))
        }
        onRequestReset={() => setConfirmResetEncounterId(encounterKey)}
        onCodingChanged={() => {
          // Invalidate the cached coded links for this encounter so the
          // next render re-fetches from /coded-links and shows the
          // post-edit live state.  See DI-LEO-AI-221.
          loadedRef.current.delete(encounterKey);
          void fetchCodesForEncounter(encounterKey);
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
      {milestoneJumps.length > 0 && (
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
          <Typography variant="caption" color="text.secondary">
            Jump to milestone encounter:
          </Typography>
          {milestoneJumps.map((milestone) => (
            <Chip
              key={milestone.key}
              size="small"
              clickable
              onClick={() => jumpToEncounter(milestone.encounterId)}
              color={focusedEncounterId === milestone.encounterId ? "primary" : "default"}
              variant={focusedEncounterId === milestone.encounterId ? "filled" : "outlined"}
              label={`${milestone.label} - ${shortDate(milestone.date)}`}
            />
          ))}
        </Box>
      )}

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
    </Box>
  );
}
