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
import Collapse from "@mui/material/Collapse";
import ExpandMore from "@mui/icons-material/ExpandMore";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import {
  fetchPatientEncounters,
  resetAndRecodeEncounter,
} from "@/lib/missionControlApi";
import type { MissionEpisode } from "@/lib/missionControlApi";
import Link from "next/link";
import { fetchEncounterCodedLinks } from "@/lib/api";
import type { CodedLink } from "@/lib/types";
import ConfirmDialog from "@/components/ConfirmDialog";

// -- Semantic tag colour palette (SNOMED CT parenthetical suffixes) ----
interface TagStyle {
  borderColor: string;
  bgcolor: string;
  color: string;
  label: string;
}

const TAG_STYLE_MAP: Record<string, TagStyle> = {
  disorder:             { borderColor: "#ef4444", bgcolor: "#fef2f2", color: "#991b1b", label: "Disorder" },
  disease:              { borderColor: "#ef4444", bgcolor: "#fef2f2", color: "#991b1b", label: "Disorder" },
  "clinical finding":   { borderColor: "#f97316", bgcolor: "#fff7ed", color: "#9a3412", label: "Finding" },
  finding:              { borderColor: "#f97316", bgcolor: "#fff7ed", color: "#9a3412", label: "Finding" },
  procedure:            { borderColor: "#3b82f6", bgcolor: "#eff6ff", color: "#1d4ed8", label: "Procedure" },
  "regime/therapy":     { borderColor: "#3b82f6", bgcolor: "#eff6ff", color: "#1d4ed8", label: "Procedure" },
  "observable entity":  { borderColor: "#d97706", bgcolor: "#fffbeb", color: "#92400e", label: "Observable" },
  observable:           { borderColor: "#d97706", bgcolor: "#fffbeb", color: "#92400e", label: "Observable" },
  situation:            { borderColor: "#8b5cf6", bgcolor: "#f5f3ff", color: "#5b21b6", label: "Situation" },
  substance:            { borderColor: "#10b981", bgcolor: "#ecfdf5", color: "#065f46", label: "Substance" },
  "medicinal product":  { borderColor: "#10b981", bgcolor: "#ecfdf5", color: "#065f46", label: "Medication" },
  product:              { borderColor: "#10b981", bgcolor: "#ecfdf5", color: "#065f46", label: "Medication" },
  "body structure":     { borderColor: "#06b6d4", bgcolor: "#ecfeff", color: "#155e75", label: "Body struct." },
  "qualifier value":    { borderColor: "#64748b", bgcolor: "#f8fafc", color: "#334155", label: "Qualifier" },
  event:                { borderColor: "#f43f5e", bgcolor: "#fff1f2", color: "#9f1239", label: "Event" },
  organism:             { borderColor: "#84cc16", bgcolor: "#f7fee7", color: "#3f6212", label: "Organism" },
  environment:          { borderColor: "#06b6d4", bgcolor: "#ecfeff", color: "#155e75", label: "Environment" },
};

const DEFAULT_TAG_STYLE: TagStyle = {
  borderColor: "#94a3b8",
  bgcolor: "#f8fafc",
  color: "#334155",
  label: "Other",
};

function getTagStyle(semanticTag: string | null | undefined): TagStyle {
  if (!semanticTag) return DEFAULT_TAG_STYLE;
  return TAG_STYLE_MAP[semanticTag.toLowerCase().trim()] ?? DEFAULT_TAG_STYLE;
}

// Tag filter pills shown above the chip list.
// When 2+ distinct types exist, pills become clickable toggles.
function TagLegend({
  links,
  activeTagLabels,
  onToggle,
  onClear,
}: {
  links: CodedLink[];
  activeTagLabels: Set<string>;
  onToggle: (label: string) => void;
  onClear: () => void;
}) {
  const seen = new Map<string, TagStyle>();
  for (const link of links) {
    const style = getTagStyle(link.semantic_tag);
    if (!seen.has(style.label)) seen.set(style.label, style);
  }
  if (seen.size < 2) return null;

  const hasFilter = activeTagLabels.size > 0;

  return (
    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 0.75, alignItems: "center" }}>
      {Array.from(seen.entries()).map(([label, style]) => {
        const isActive = activeTagLabels.has(label);
        const isDimmed = hasFilter && !isActive;
        return (
          <Box
            key={label}
            role="button"
            tabIndex={0}
            aria-pressed={isActive}
            aria-label={`Filter by ${label}`}
            onClick={() => onToggle(label)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") onToggle(label);
            }}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.4,
              px: 0.75,
              py: 0.25,
              borderRadius: "4px",
              border: "1px solid",
              borderColor: isDimmed ? "#e2e8f0" : style.borderColor,
              bgcolor: isActive ? style.borderColor : isDimmed ? "#f8fafc" : style.bgcolor,
              cursor: "pointer",
              opacity: isDimmed ? 0.55 : 1,
              transition: "all 0.12s ease",
              userSelect: "none",
              outline: "none",
              "&:hover": { opacity: 1, borderColor: style.borderColor },
              "&:focus-visible": { outline: `2px solid ${style.borderColor}`, outlineOffset: 1 },
            }}
          >
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                bgcolor: isActive ? "white" : style.borderColor,
                flexShrink: 0,
              }}
            />
            <Typography
              variant="caption"
              sx={{
                fontSize: "0.68rem",
                color: isActive ? "white" : isDimmed ? "#94a3b8" : style.color,
                lineHeight: 1,
              }}
            >
              {label}
            </Typography>
          </Box>
        );
      })}
      {hasFilter && (
        <Box
          role="button"
          tabIndex={0}
          aria-label="Clear type filter"
          onClick={onClear}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onClear(); }}
          sx={{
            px: 0.75,
            py: 0.25,
            borderRadius: "4px",
            border: "1px solid #e2e8f0",
            bgcolor: "transparent",
            cursor: "pointer",
            userSelect: "none",
            outline: "none",
            "&:hover": { borderColor: "#94a3b8" },
            "&:focus-visible": { outline: "2px solid #94a3b8", outlineOffset: 1 },
          }}
        >
          <Typography variant="caption" sx={{ fontSize: "0.68rem", color: "#64748b", lineHeight: 1 }}>
            Clear filter
          </Typography>
        </Box>
      )}
    </Box>
  );
}

// Owns per-encounter tag-filter state and renders coded concept chips.
interface CodesPanelProps {
  enc: Encounter;
  codingLoading: boolean;
  codingLinks: CodedLink[];
  codingError: string | undefined;
}

function CodesPanel({ enc, codingLoading, codingLinks, codingError }: CodesPanelProps) {
  const [activeTagLabels, setActiveTagLabels] = useState<Set<string>>(new Set());

  const toggleTag = (label: string) =>
    setActiveTagLabels((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });

  const clearFilter = () => setActiveTagLabels(new Set());

  const hasCodes = (enc.coded_count ?? 0) > 0;
  if (!hasCodes && !codingLoading && !codingError) return null;

  const filteredLinks =
    activeTagLabels.size === 0
      ? codingLinks
      : codingLinks.filter((l) => activeTagLabels.has(getTagStyle(l.semantic_tag).label));

  return (
    <Box sx={{ mb: 1, px: 0.5 }}>
      {codingLoading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5 }}>
          <CircularProgress size={14} aria-label="Loading coded concepts" />
          <Typography variant="caption" color="text.secondary">
            Loading coded concepts...
          </Typography>
        </Box>
      )}
      {!codingLoading && codingError && (
        <Alert severity="error" sx={{ py: 0 }}>
          {codingError}
        </Alert>
      )}
      {!codingLoading && !codingError && codingLinks.length === 0 && hasCodes && (
        <Typography variant="caption" color="text.secondary">
          {enc.coded_count} coded {enc.coded_count === 1 ? "concept" : "concepts"} -- loading...
        </Typography>
      )}
      {!codingLoading && !codingError && codingLinks.length > 0 && (
        <>
          <TagLegend
            links={codingLinks}
            activeTagLabels={activeTagLabels}
            onToggle={toggleTag}
            onClear={clearFilter}
          />
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
            {filteredLinks.map((link, linkIndex) => {
              const style = getTagStyle(link.semantic_tag);
              const sentenceEvidence =
                link.evidence_sentence ?? deriveEvidenceSentence(enc.text, link.evidence);
              const tooltipRows = [
                `Coded term: ${link.term || "Unknown term"}`,
                `Concept ID: ${link.concept_id}`,
              ];
              if (link.semantic_tag) tooltipRows.push(`Type: ${link.semantic_tag}`);
              if (sentenceEvidence) tooltipRows.push(`Sentence: ${sentenceEvidence}`);
              if (link.evidence) tooltipRows.push(`Mention: ${link.evidence}`);
              if (
                typeof link.evidence_start === "number" &&
                typeof link.evidence_end === "number"
              ) {
                tooltipRows.push(`Mention offsets: ${link.evidence_start}-${link.evidence_end}`);
              }
              if (typeof link.sentence_index === "number") {
                tooltipRows.push(`Sentence index: ${link.sentence_index}`);
              }
              return (
                <Tooltip
                  key={`${enc.encounter_id}-${link.concept_id}-${link.sentence_index ?? "na"}-${linkIndex}`}
                  placement="top"
                  title={
                    <Box sx={{ whiteSpace: "pre-wrap", fontSize: "0.75rem" }}>
                      {tooltipRows.join("\n")}
                    </Box>
                  }
                >
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`${link.term || "Unknown term"} (${link.concept_id})`}
                    sx={{
                      borderColor: style.borderColor,
                      bgcolor: style.bgcolor,
                      color: style.color,
                      "& .MuiChip-label": { color: style.color },
                    }}
                  />
                </Tooltip>
              );
            })}
          </Box>
          {activeTagLabels.size > 0 && filteredLinks.length < codingLinks.length && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              Showing {filteredLinks.length} of {codingLinks.length} coded concepts
            </Typography>
          )}
        </>
      )}
    </Box>
  );
}

interface Encounter {
  encounter_id: string;
  date: string;
  text: string | null;
  coded_count: number;
}

interface Props {
  patientId: string;
  episode: MissionEpisode;
}

const MILESTONE_LABELS: Record<string, string> = {
  first_presentation: "First seen",
  gp_referral: "Referred",
  specialist_visit: "Specialist",
  specialist_outcome_letter: "Outcome letter",
  cancer_diagnosis: "Diagnosed",
  benign_closure: "Closed",
};

interface MilestoneJump {
  key: string;
  encounterId: string;
  label: string;
  date: string | null;
}

function inRange(date: string, from: string | null, to: string | null): boolean {
  if (!date) return false;
  if (from && date < from) return false;
  if (to && date > to) return false;
  return true;
}

function shortDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    });
  } catch {
    return String(iso).slice(0, 10);
  }
}

function deriveEvidenceSentence(
  encounterText: string | null | undefined,
  mention: string | null | undefined
): string | null {
  const text = (encounterText ?? "").trim();
  const span = (mention ?? "").trim();
  if (!text || !span) return null;
  const lowerText = text.toLowerCase();
  const lowerSpan = span.toLowerCase();
  const idx = lowerText.indexOf(lowerSpan);
  if (idx < 0) return null;

  const leftBoundary = Math.max(
    text.lastIndexOf(".", idx),
    text.lastIndexOf("\n", idx)
  );
  const rightDot = text.indexOf(".", idx + span.length);
  const rightNl = text.indexOf("\n", idx + span.length);
  const rightCandidates = [rightDot, rightNl].filter((v) => v >= 0);
  const rightBoundary =
    rightCandidates.length > 0 ? Math.min(...rightCandidates) : text.length;
  const start = leftBoundary >= 0 ? leftBoundary + 1 : 0;
  const end = rightBoundary < text.length ? rightBoundary + 1 : text.length;
  const sentence = text.slice(start, end).trim();
  return sentence || null;
}

export default function EncounterTextTab({ patientId, episode }: Props) {
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
  const [confirmResetEncounterId, setConfirmResetEncounterId] = useState<string | null>(
    null
  );
  const [resettingEncounterId, setResettingEncounterId] = useState<string | null>(null);
  const [recodeMessage, setRecodeMessage] = useState<string | null>(null);
  const [recodeJobState, setRecodeJobState] = useState<
    "queued" | "running" | "completed" | "failed" | null
  >(null);
  const [focusedEncounterId, setFocusedEncounterId] = useState<string | null>(null);
  const encounterRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Refs prevent duplicate in-flight fetches without causing re-renders
  const loadedRef = useRef<Set<string>>(new Set());
  const loadingRef = useRef<Set<string>>(new Set());

  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      setTimeout(resolve, ms);
    });

  const refreshEncounters = async () => {
    const refreshed = await fetchPatientEncounters(patientId);
    setEncounters(refreshed);
    return refreshed;
  };

  useEffect(() => {
    setLoading(true);
    fetchPatientEncounters(patientId)
      .then(setEncounters)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load encounter text."))
      .finally(() => setLoading(false));
  }, [patientId]);

  useEffect(() => {
    loadedRef.current = new Set();
    loadingRef.current = new Set();
    setCodedByEncounter({});
    setCodingErrorByEncounter({});
    setCodingLoadingFor({});
    setCollapsedEncounters({});
  }, [patientId, episode.episode_id]);

  useEffect(() => {
    if (scope === "window") {
      setWindowSectionExpanded(true);
    }
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

  // Auto-fetch coded concepts for all visible encounters that have codes
  useEffect(() => {
    if (loading) return;
    const episodeFrom = episode.referral_date ?? null;
    const episodeTo = episode.end_date ?? null;
    const linkedIds = new Set([
      ...(episode.linked_encounter_ids ?? []).map(String),
      ...(episode.milestones ?? []).map((m) => String(m.encounter_id)),
    ]);

    encounters.forEach((enc) => {
      if ((enc.coded_count ?? 0) === 0) return;
      const encId = String(enc.encounter_id);
      const isLinked = linkedIds.has(encId);
      const isInWindow =
        !isLinked &&
        inRange(String(enc.date).slice(0, 10), episodeFrom, episodeTo);

      if (scope === "linked" && !isLinked) return;
      if (scope === "window" && !isLinked && !isInWindow) return;

      void fetchCodesForEncounter(encId);
    });
  }, [encounters, scope, episode, loading, fetchCodesForEncounter]);

  const handleResetAndRecode = async (encounterId: string) => {
    setConfirmResetEncounterId(null);
    setResettingEncounterId(encounterId);
    setRecodeMessage(null);
    try {
      const result = await resetAndRecodeEncounter(patientId, encounterId, false, false);
      // Clear cached codes so they re-fetch after recode completes
      setCodedByEncounter((prev) => ({ ...prev, [encounterId]: [] }));
      loadedRef.current.delete(String(encounterId));
      setRecodeJobState("queued");
      setRecodeMessage(
        `Queued: ${result.links_deleted} coded links cleared. Run ${result.run_id.slice(0, 8)} is waiting for worker pickup.`
      );

      await new Promise<void>((resolve, reject) => {
        const source = new EventSource(
          `${window.location.origin}/api/pipeline/progress/${encodeURIComponent(result.run_id)}`
        );
        let settled = false;
        const complete = (nextState: "completed" | "failed", message: string) => {
          if (settled) return;
          settled = true;
          setRecodeJobState(nextState);
          setRecodeMessage(message);
          source.close();
          if (nextState === "completed") resolve();
          else reject(new Error(message));
        };

        const onEvent = (ev: MessageEvent) => {
          try {
            const payload = JSON.parse(ev.data) as { type?: string; message?: string };
            const type = payload.type ?? "";
            if (
              type === "run_started" ||
              type === "patient_started" ||
              type === "encounter_started"
            ) {
              setRecodeJobState("running");
              setRecodeMessage(`Running: ${payload.message ?? "pipeline is processing this encounter."}`);
            }
            if (type === "run_completed" || type === "extraction_done" || type === "pipeline_done") {
              complete("completed", "Completed: pipeline finished for this encounter.");
            }
            if (type === "pipeline_error" || type === "run_error") {
              complete("failed", `Failed: ${payload.message ?? "pipeline execution error."}`);
            }
          } catch {
            // Ignore malformed progress events.
          }
        };

        source.addEventListener("run_started", onEvent as EventListener);
        source.addEventListener("patient_started", onEvent as EventListener);
        source.addEventListener("encounter_started", onEvent as EventListener);
        source.addEventListener("run_completed", onEvent as EventListener);
        source.addEventListener("pipeline_done", onEvent as EventListener);
        source.addEventListener("extraction_done", onEvent as EventListener);
        source.addEventListener("pipeline_error", onEvent as EventListener);
        source.addEventListener("run_error", onEvent as EventListener);
        source.onerror = () => {
          complete("failed", "Failed: connection to live pipeline status was lost.");
        };
      });

      let latest = await refreshEncounters();
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const target = latest.find((e) => String(e.encounter_id) === String(encounterId));
        if ((target?.coded_count ?? 0) > 0) {
          setRecodeMessage(
            `Completed: ${target?.coded_count ?? 0} coded concepts now linked to this encounter.`
          );
          break;
        }
        await sleep(2000);
        latest = await refreshEncounters();
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

  const linkedIdsFromEdges = episode.linked_encounter_ids ?? [];
  const linkedIdsFromMilestones = (episode.milestones ?? []).map((m) => m.encounter_id);
  const linkedEncounterIds = new Set(
    [...linkedIdsFromEdges, ...linkedIdsFromMilestones].map((id) => String(id))
  );
  const from = episode.referral_date ?? null;
  const to = episode.end_date ?? null;

  const linked = encounters.filter((e) => linkedEncounterIds.has(String(e.encounter_id)));
  const windowOnly = encounters.filter(
    (e) => !linkedEncounterIds.has(String(e.encounter_id)) && inRange(String(e.date).slice(0, 10), from, to)
  );
  const other = encounters.filter(
    (e) =>
      !linkedEncounterIds.has(String(e.encounter_id)) &&
      !inRange(String(e.date).slice(0, 10), from, to)
  );

  const applyCommonFilters = (items: Encounter[]) =>
    items.filter((e) => {
      if (codedOnly && (e.coded_count ?? 0) <= 0) return false;
      if (search.trim()) {
        const q = search.trim().toLowerCase();
        if (!(e.text ?? "").toLowerCase().includes(q)) return false;
      }
      return true;
    });

  const linkedVisible = applyCommonFilters(linked);
  const windowVisible = applyCommonFilters(windowOnly);
  const otherVisible = applyCommonFilters(other);
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
    rows.sort((a, b) => {
      if (!a.date && !b.date) return 0;
      if (!a.date) return 1;
      if (!b.date) return -1;
      return a.date.localeCompare(b.date);
    });
    return rows;
  }, [episode.milestones]);

  const jumpToMilestoneEncounter = (encounterId: string) => {
    setScope("all");
    setCodedOnly(false);
    setSearch("");
    setCollapsedEncounters((prev) => ({ ...prev, [encounterId]: false }));
    setFocusedEncounterId(encounterId);
  };

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

  const renderCodesPanel = (enc: Encounter) => {
    const key = String(enc.encounter_id);
    return (
      <CodesPanel
        enc={enc}
        codingLoading={!!codingLoadingFor[key]}
        codingLinks={codedByEncounter[key] ?? []}
        codingError={codingErrorByEncounter[key]}
      />
    );
  };

  const renderEncounterCard = (enc: Encounter, keyPrefix = "") => {
    const encounterKey = String(enc.encounter_id);
    const isExpanded = !collapsedEncounters[encounterKey];
    const toggle = () =>
      setCollapsedEncounters((prev) => ({ ...prev, [encounterKey]: isExpanded }));

    return (
      <Box
        key={`${keyPrefix}${encounterKey}`}
        ref={(node: HTMLDivElement | null) => {
          encounterRefs.current[encounterKey] = node;
        }}
        sx={{
          mb: 1.5,
          border: "2px solid",
          borderColor:
            focusedEncounterId === encounterKey ? "primary.main" : "divider",
          borderRadius: "6px",
          transition: "border-color 0.25s ease",
          overflow: "hidden",
        }}
      >
        {/* Header row — plain div so action buttons are valid descendants */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            px: 1,
            py: 0.5,
            flexWrap: "wrap",
            cursor: "pointer",
            userSelect: "none",
            "&:hover": { bgcolor: "action.hover" },
          }}
          onClick={toggle}
        >
          <IconButton
            size="small"
            aria-label={isExpanded ? "Collapse encounter" : "Expand encounter"}
            sx={{
              p: 0.25,
              transition: "transform 0.2s ease",
              transform: isExpanded ? "rotate(0deg)" : "rotate(-90deg)",
            }}
            onClick={(e) => { e.stopPropagation(); toggle(); }}
          >
            <ExpandMore fontSize="small" />
          </IconButton>

          <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
            {enc.date?.slice(0, 10) ?? "--"}
            {!isExpanded && enc.coded_count > 0 && (
              <Typography component="span" variant="caption" color="text.disabled" sx={{ ml: 1 }}>
                &middot; {enc.coded_count} coded {enc.coded_count === 1 ? "concept" : "concepts"}
              </Typography>
            )}
          </Typography>

          <Box
            sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}
            onClick={(e) => e.stopPropagation()}
          >
            {isExpanded && (
              <Typography variant="caption" color="text.secondary">
                {enc.coded_count} coded {enc.coded_count === 1 ? "concept" : "concepts"}
              </Typography>
            )}
            <Button
              size="small"
              variant="outlined"
              component={Link}
              href={`/care/patients/${encodeURIComponent(
                patientId
              )}/encounters/${encodeURIComponent(encounterKey)}`}
            >
              Edit codes
            </Button>
            <Button
              size="small"
              color="error"
              variant="outlined"
              disabled={resettingEncounterId === encounterKey}
              onClick={() => setConfirmResetEncounterId(encounterKey)}
            >
              {resettingEncounterId === encounterKey ? "Resetting..." : "Reset and recode"}
            </Button>
          </Box>
        </Box>

        <Collapse in={isExpanded} unmountOnExit>
          <Box sx={{ px: 1, pb: 1 }}>
            {renderCodesPanel(enc)}
            <Box
              sx={{
                bgcolor: "grey.50",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                p: 1.5,
                fontFamily: "inherit",
                fontSize: "0.8rem",
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: enc.text ? "text.primary" : "text.disabled",
                fontStyle: enc.text ? "normal" : "italic",
              }}
            >
              {enc.text ?? "No text available for this encounter."}
            </Box>
          </Box>
        </Collapse>
      </Box>
    );
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress aria-label="Loading encounter text" />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!encounters.length) {
    return (
      <Alert severity="info">
        No encounter records found for this patient.
      </Alert>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="caption" color="text.secondary">
        {hasExplicitLinks
          ? "Default view shows only encounters linked to this episode. Expand other sections when you need more context."
          : "No direct encounter links were found for this episode. Use Episode window or All encounters while linkage is rebuilt."}
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
              onClick={() => jumpToMilestoneEncounter(milestone.encounterId)}
              color={
                focusedEncounterId === milestone.encounterId ? "primary" : "default"
              }
              variant={
                focusedEncounterId === milestone.encounterId ? "filled" : "outlined"
              }
              label={`${milestone.label} - ${shortDate(milestone.date)}`}
            />
          ))}
        </Box>
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

      {(scope === "linked" ? linkedVisible : []).map((enc) => renderEncounterCard(enc))}
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
            {windowVisible.map((enc) => renderEncounterCard(enc, "win-"))}
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
            {otherVisible.map((enc) => renderEncounterCard(enc, "other-"))}
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
