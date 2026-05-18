/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

import { useMemo } from "react";
import type { EncounterListItem } from "@/lib/missionControlApi";
import EncounterTimelineScrubber from "./EncounterTimelineScrubber";
import type { ScrubberEncounter } from "./timelineBins";

// Adapter that lifts the patient-drawer EncounterTimelineScrubber
// (DI-LEO-AI-179) onto the /care/encounters search-results surface.
// On this surface there is no episode context, so:
//   - linkedEncounterIds is empty (no blue "linked" sub-stack)
//   - episodeFrom / episodeTo are null (no episode window band)
//   - milestones is empty (no milestone tabs)
// which collapses the scrubber to a single-colour histogram + brush.
//
// Design Controls: UN-LEO-AI-096, DI-LEO-AI-516, DO-LEO-AI-515,
// R-LEO-AI-063, R-LEO-AI-174, R-LEO-AI-206, VT-LEO-AI-514.

// Mirrors MIN_ENCOUNTERS_FOR_SCRUBBER inside EncounterTimelineScrubber.
// Re-stated here so the wrapper can short-circuit before mounting the
// scrubber when the result set is too small for a meaningful histogram.
const MIN_DATED_ROWS = 5;

const EMPTY_LINKED: Set<string> = new Set();
const EMPTY_MILESTONES: Array<{
  milestone_type: string;
  encounter_id: string;
  date: string;
}> = [];

interface Props {
  rows: EncounterListItem[];
  activeEncounterId: string | null;
  visibleFromMs: number | null;
  visibleToMs: number | null;
  onVisibleRangeChange: (fromMs: number | null, toMs: number | null) => void;
  onJumpToEncounter: (encounterId: string) => void;
}

export default function EncounterResultsTimeline({
  rows,
  activeEncounterId,
  visibleFromMs,
  visibleToMs,
  onVisibleRangeChange,
  onJumpToEncounter,
}: Props) {
  const scrubberRows = useMemo<ScrubberEncounter[]>(() => {
    const out: ScrubberEncounter[] = [];
    for (const row of rows) {
      const ts = Date.parse(row.encounter_date ?? "");
      if (!Number.isFinite(ts)) continue;
      out.push({
        encounter_id: String(row.encounter_id),
        date: row.encounter_date as string,
        text: row.text ?? null,
        coded_count: row.coded_count ?? 0,
      });
    }
    return out;
  }, [rows]);

  if (scrubberRows.length < MIN_DATED_ROWS) return null;

  return (
    <EncounterTimelineScrubber
      encounters={scrubberRows}
      linkedEncounterIds={EMPTY_LINKED}
      episodeFrom={null}
      episodeTo={null}
      milestones={EMPTY_MILESTONES}
      activeEncounterId={activeEncounterId}
      onJumpToEncounter={onJumpToEncounter}
      visibleFromMs={visibleFromMs}
      visibleToMs={visibleToMs}
      onVisibleRangeChange={onVisibleRangeChange}
    />
  );
}
