"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AssertionChip from "./AssertionChip";
import { fetchPatientCodingTimeline } from "@/lib/analyticsApi";
import type { TimelineEvent } from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TimelineDay {
  date: string;
  encounter_id: string;
  events: TimelineEvent[];
}

type AssertionFilter = "present" | "all";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SEMANTIC_TAG_COLORS: Record<string, string> = {
  disorder:             "#7c3aed",
  disease:              "#7c3aed",
  finding:              "#0369a1",
  observable_entity:    "#0369a1",
  procedure:            "#047857",
  regime_therapy:       "#047857",
  situation:            "#b45309",
  substance:            "#be123c",
  medication:           "#be123c",
  other:                "#374151",
};

function tagColor(tag: string): string {
  const norm = tag.toLowerCase().replace(/[^a-z_]/g, "");
  return SEMANTIC_TAG_COLORS[norm] ?? SEMANTIC_TAG_COLORS.other;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function groupByEncounter(events: TimelineEvent[]): TimelineDay[] {
  const map = new Map<string, TimelineDay>();
  for (const ev of events) {
    const key = ev.encounter_id;
    if (!map.has(key)) {
      map.set(key, { date: ev.encounter_date, encounter_id: key, events: [] });
    }
    map.get(key)!.events.push(ev);
  }
  return [...map.values()].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConceptChip({ event }: { event: TimelineEvent }) {
  const color = tagColor(event.semantic_tag);
  const label = event.term || event.concept_id;
  const tooltipContent = [
    `SNOMED: ${event.concept_id}`,
    event.read_code && `Read: ${event.read_code}`,
    event.semantic_tag && `Type: ${event.semantic_tag}`,
    event.confidence != null && `Confidence: ${Math.round(event.confidence * 100)}%`,
    event.domain && `Domain: ${event.domain}`,
    event.decision_tier != null && `Tier: ${event.decision_tier}`,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <Tooltip title={<Box sx={{ whiteSpace: "pre-wrap", fontSize: "0.72rem" }}>{tooltipContent}</Box>} arrow placement="top">
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Chip
          label={label}
          size="small"
          sx={{
            height: 22,
            fontSize: "0.73rem",
            fontWeight: 500,
            bgcolor: `${color}14`,
            color,
            border: `1px solid ${color}30`,
            "& .MuiChip-label": { px: 1 },
          }}
        />
        <AssertionChip assertion={event.assertion} />
      </Stack>
    </Tooltip>
  );
}

function EncounterRow({ day, isLast }: { day: TimelineDay; isLast: boolean }) {
  const dateLabel = formatDate(day.date);
  return (
    <Stack direction="row" spacing={0} sx={{ position: "relative" }}>
      {/* Timeline rail */}
      <Box sx={{ width: 120, flexShrink: 0, position: "relative", pr: 2 }}>
        <Typography
          variant="caption"
          sx={{
            fontWeight: 600,
            color: "text.secondary",
            whiteSpace: "nowrap",
            display: "block",
            textAlign: "right",
            pt: 0.25,
          }}
        >
          {dateLabel}
        </Typography>
        {/* Vertical line */}
        {!isLast && (
          <Box
            sx={{
              position: "absolute",
              right: 0,
              top: 20,
              bottom: -16,
              width: 2,
              bgcolor: "divider",
            }}
          />
        )}
        {/* Dot */}
        <Box
          sx={{
            position: "absolute",
            right: -5,
            top: 6,
            width: 10,
            height: 10,
            borderRadius: "50%",
            bgcolor: "primary.main",
            border: "2px solid",
            borderColor: "background.paper",
          }}
        />
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, pl: 2, pb: 3 }}>
        <Typography variant="caption" sx={{ color: "text.disabled", mb: 0.75, display: "block" }}>
          Encounter {day.encounter_id.slice(0, 8)}
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={0.75}>
          {day.events.map((ev, i) => (
            <ConceptChip key={`${ev.concept_id}-${i}`} event={ev} />
          ))}
        </Stack>
      </Box>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  patientId: string;
}

export default function PatientTimeline({ patientId }: Props) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<AssertionFilter>("present");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPatientCodingTimeline(patientId);
      setEvents(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load timeline. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    return events.filter((ev) => ev.assertion === "present" || ev.assertion === "historical");
  }, [events, filter]);

  const days = useMemo(() => groupByEncounter(filtered), [filtered]);

  const nonPresentCount = useMemo(
    () => events.filter((ev) => ev.assertion !== "present" && ev.assertion !== "historical").length,
    [events],
  );

  return (
    <Box sx={{ maxWidth: 900, mx: "auto", p: 3 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Coding timeline
          </Typography>
          <Typography variant="body2" color="text.secondary">
            SNOMED codes recorded across all encounters, in date order.
          </Typography>
        </Box>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={filter}
          onChange={(_, v) => { if (v) setFilter(v); }}
          sx={{ "& .MuiToggleButton-root": { textTransform: "none", fontSize: "0.8rem", px: 1.5, py: 0.5 } }}
        >
          <ToggleButton value="present">Present only</ToggleButton>
          <ToggleButton value="all">
            Show all
            {nonPresentCount > 0 && (
              <Chip
                label={nonPresentCount}
                size="small"
                color="warning"
                sx={{ ml: 0.75, height: 16, fontSize: "0.65rem", "& .MuiChip-label": { px: 0.5 } }}
              />
            )}
          </ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Divider sx={{ mb: 3 }} />

      {loading && (
        <Stack alignItems="center" sx={{ py: 6 }} spacing={1}>
          <CircularProgress aria-label="Loading" size={28} />
          <Typography variant="body2" color="text.secondary">Loading timeline...</Typography>
        </Stack>
      )}

      {error && (
        <Typography color="error.main" sx={{ py: 2, fontSize: "0.9rem" }}>{error}</Typography>
      )}

      {!loading && !error && days.length === 0 && (
        <Typography color="text.secondary" sx={{ py: 6, textAlign: "center", fontSize: "0.9rem" }}>
          {events.length === 0
            ? "No coded terms found for this patient."
            : "No present or historical codes to show. Switch to 'Show all' to see declined and absent records."}
        </Typography>
      )}

      {!loading && !error && days.length > 0 && (
        <Box>
          {days.map((day, idx) => (
            <EncounterRow
              key={day.encounter_id}
              day={day}
              isLast={idx === days.length - 1}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}
