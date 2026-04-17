"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import ExpandMore from "@mui/icons-material/ExpandMore";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { resetAndRecodeEncounter } from "@/lib/missionControlApi";
import type { MissionEpisode } from "@/lib/missionControlApi";
import { fetchEncounterCodedLinks } from "@/lib/api";
import type { CodedLink } from "@/lib/types";
import ConfirmDialog from "@/components/ConfirmDialog";
import { compareIsoDateTimeAsc, sortByIsoDateAsc } from "@/lib/dateSort";
import EncounterCard from "./EncounterCard";
import EncounterTimelineScrubber from "./EncounterTimelineScrubber";
import { MILESTONE_LABELS, shortDate } from "./encounterTextUtils";
import { applyCommonFilters, splitEncounters } from "./encounterFilters";
import { waitForRecodeProgress } from "./encounterRecodeProgress";
import { useEncounterLoad, type Encounter } from "./useEncounterLoad";

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

const sleep = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

export default function EncounterTextTab({ patientId, episode }: Props) {
  const { encounters, setEncounters, loading, error, refresh } =
    useEncounterLoad(patientId);
  const [scope, setScope] = useState<"linked" | "window" | "all">("linked");
  const [windowSectionExpanded, setWindowSectionExpanded] = useState(false);
  const [codedOnly, setCodedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [codedByEncounter, setCodedByEncounter] = useState<Record<string, CodedLink[]>>({});
  const [codingErrorByEncounter, setCodingErrorByEncounter] = useState<
    Record<string, string>
  >({});
  const [codingLoadingFor, setCodingLoadingFor] = useState<Record<string, boolean>>({});
  const [collapsedEncounters, setCollapsedEncounters] = useState<Record<string, boolean>>({});
  const [confirmResetEncounterId, setConfirmResetEncounterId] = useState<string | null>(null);
  const [resettingEncounterId, setResettingEncounterId] = useState<string | null>(null);
  const [recodeMessage, setRecodeMessage] = useState<string | null>(null);
  const [recodeJobState, setRecodeJobState] = useState<
    "queued" | "running" | "completed" | "failed" | null
  >(null);
  const [focusedEncounterId, setFocusedEncounterId] = useState<string | null>(null);
  const [visibleEncounterId, setVisibleEncounterId] = useState<string | null>(null);
  const [timelineRange, setTimelineRange] = useState<
    { fromMs: number; toMs: number } | null
  >(null);
  const encounterRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const loadedRef = useRef<Set<string>>(new Set());
  const loadingRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    loadedRef.current = new Set();
    loadingRef.current = new Set();
    setCodedByEncounter({});
    setCodingErrorByEncounter({});
    setCodingLoadingFor({});
    setCollapsedEncounters({});
  }, [patientId, episode.episode_id]);

  useEffect(() => {
    if (scope === "window") setWindowSectionExpanded(true);
  }, [scope]);

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

  const linkedEncounterIds = useMemo(() => {
    const ids: string[] = [];
    (episode.linked_encounter_ids ?? []).forEach((id) => ids.push(String(id)));
    (episode.milestones ?? []).forEach((m) => {
      if (m.encounter_id) ids.push(String(m.encounter_id));
    });
    return new Set(ids);
  }, [episode.linked_encounter_ids, episode.milestones]);
  const from = episode.referral_date ?? null;
  const to = episode.end_date ?? null;

  const split = useMemo(
    () => splitEncounters({ encounters, linkedEncounterIds, episodeFrom: from, episodeTo: to }),
    [encounters, linkedEncounterIds, from, to]
  );

  useEffect(() => {
    if (loading) return;
    const targets =
      scope === "linked"
        ? split.linked
        : scope === "window"
          ? [...split.linked, ...split.windowOnly]
          : encounters;
    targets.forEach((enc) => {
      if ((enc.coded_count ?? 0) === 0) return;
      void fetchCodesForEncounter(String(enc.encounter_id));
    });
  }, [encounters, scope, split, loading, fetchCodesForEncounter]);

  const handleResetAndRecode = async (encounterId: string) => {
    setConfirmResetEncounterId(null);
    setResettingEncounterId(encounterId);
    setRecodeMessage(null);
    try {
      const result = await resetAndRecodeEncounter(patientId, encounterId, false, false);
      setCodedByEncounter((prev) => ({ ...prev, [encounterId]: [] }));
      loadedRef.current.delete(String(encounterId));
      setRecodeJobState("queued");
      setRecodeMessage(
        `Queued: ${result.links_deleted} coded links cleared. Run ${result.run_id.slice(0, 8)} is waiting for worker pickup.`
      );
      await waitForRecodeProgress(result.run_id, setRecodeJobState, setRecodeMessage);
      let latest = await refresh();
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const target = latest.find((e) => String(e.encounter_id) === String(encounterId));
        if ((target?.coded_count ?? 0) > 0) {
          setRecodeMessage(
            `Completed: ${target?.coded_count ?? 0} coded concepts now linked to this encounter.`
          );
          break;
        }
        await sleep(2000);
        latest = await refresh();
      }
    } catch (e) {
      setRecodeJobState("failed");
      setRecodeMessage(
        e instanceof Error
          ? `Reset and recode failed: ${e.message}`
          : "Reset and recode failed."
      );
    } finally {
      setResettingEncounterId(null);
    }
  };

  const { linkedVisible, windowVisible, otherVisible } = useMemo(() => {
    const args = { codedOnly, search, timelineRange };
    const dateOf = (e: Encounter) => e.date ?? null;
    return {
      linkedVisible: sortByIsoDateAsc(applyCommonFilters(split.linked, args), dateOf),
      windowVisible: sortByIsoDateAsc(applyCommonFilters(split.windowOnly, args), dateOf),
      otherVisible: sortByIsoDateAsc(applyCommonFilters(split.other, args), dateOf),
    };
  }, [split, codedOnly, search, timelineRange]);
  const hasExplicitLinks = linkedEncounterIds.size > 0;

  const milestoneJumps = useMemo<MilestoneJump[]>(() => {
    const rows = (episode.milestones ?? [])
      .filter((m) => Boolean(m.encounter_id))
      .map((m, idx) => ({
        key: `${m.milestone_type}-${m.encounter_id}-${idx}`,
        encounterId: String(m.encounter_id),
        label: MILESTONE_LABELS[m.milestone_type] ?? m.milestone_type.replaceAll("_", " "),
        date: m.date ?? null,
      }));
    rows.sort((a, b) => compareIsoDateTimeAsc(a.date, b.date));
    return rows;
  }, [episode.milestones]);

  const jumpToEncounter = useCallback((encounterId: string) => {
    setScope("all");
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
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = window.setTimeout(() => setFocusedEncounterId(null), 2200);
    return () => window.clearTimeout(timer);
  }, [
    focusedEncounterId,
    scope,
    codedOnly,
    search,
    linkedVisible.length,
    windowVisible.length,
    otherVisible.length,
  ]);

  const allVisibleIds = useMemo(() => {
    if (scope === "linked") return linkedVisible.map((e) => String(e.encounter_id));
    if (scope === "window")
      return [...linkedVisible, ...windowVisible].map((e) => String(e.encounter_id));
    return [...linkedVisible, ...windowVisible, ...otherVisible].map((e) =>
      String(e.encounter_id)
    );
  }, [scope, linkedVisible, windowVisible, otherVisible]);

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
    const candidates = allVisibleIds
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
  }, [allVisibleIds]);

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

  const renderCard = (enc: Encounter, keyPrefix = "") => {
    const encounterKey = String(enc.encounter_id);
    const isExpanded = !collapsedEncounters[encounterKey];
    return (
      <EncounterCard
        key={`${keyPrefix}${encounterKey}`}
        ref={(node) => {
          encounterRefs.current[encounterKey] = node;
        }}
        enc={enc}
        patientId={patientId}
        search={search}
        isExpanded={isExpanded}
        isFocused={focusedEncounterId === encounterKey}
        isResetting={resettingEncounterId === encounterKey}
        codingLoading={!!codingLoadingFor[encounterKey]}
        codingLinks={codedByEncounter[encounterKey] ?? []}
        codingError={codingErrorByEncounter[encounterKey]}
        onToggle={() =>
          setCollapsedEncounters((prev) => ({ ...prev, [encounterKey]: isExpanded }))
        }
        onRequestReset={() => setConfirmResetEncounterId(encounterKey)}
      />
    );
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="caption" color="text.secondary">
        {hasExplicitLinks
          ? "Default view shows only encounters linked to this episode. Use the timeline below or expand other sections when you need surrounding context."
          : "No direct encounter links were found for this episode. Use the timeline below or All encounters while linkage is rebuilt."}
      </Typography>
      {recodeMessage && (
        <Alert
          severity={
            recodeJobState === "failed"
              ? "error"
              : recodeJobState === "running" || recodeJobState === "queued"
                ? "info"
                : "success"
          }
        >
          {recodeMessage}
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
        <Chip
          label={`Episode linked (${linkedVisible.length})`}
          size="small"
          color={scope === "linked" ? "primary" : "default"}
          variant={scope === "linked" ? "filled" : "outlined"}
          onClick={() => setScope("linked")}
        />
        <Chip
          label={`Episode window (${linkedVisible.length + windowVisible.length})`}
          size="small"
          color={scope === "window" ? "primary" : "default"}
          variant={scope === "window" ? "filled" : "outlined"}
          onClick={() => setScope("window")}
        />
        <Chip
          label={`All encounters (${linkedVisible.length + windowVisible.length + otherVisible.length})`}
          size="small"
          color={scope === "all" ? "primary" : "default"}
          variant={scope === "all" ? "filled" : "outlined"}
          onClick={() => setScope("all")}
        />
        <FormControlLabel
          sx={{ ml: 0.5 }}
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
      {scope === "linked" && !hasExplicitLinks && (
        <Alert severity="warning">
          We could not find explicit encounter links for this episode.
          This means Episode linked will be empty until those links are available.
        </Alert>
      )}

      {(scope === "linked" ? linkedVisible : []).map((enc) => renderCard(enc))}
      {scope !== "linked" && windowVisible.length > 0 && (
        <Accordion
          expanded={windowSectionExpanded}
          onChange={(_, expanded) => setWindowSectionExpanded(expanded)}
          elevation={0}
        >
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="body2" color="text.secondary">
              Other encounters in episode window ({windowVisible.length})
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0 }}>
            {windowVisible.map((enc) => renderCard(enc, "win-"))}
          </AccordionDetails>
        </Accordion>
      )}
      {scope === "all" && otherVisible.length > 0 && (
        <Accordion elevation={0}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="body2" color="text.secondary">
              All other patient encounters ({otherVisible.length})
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0 }}>
            {otherVisible.map((enc) => renderCard(enc, "other-"))}
          </AccordionDetails>
        </Accordion>
      )}
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

