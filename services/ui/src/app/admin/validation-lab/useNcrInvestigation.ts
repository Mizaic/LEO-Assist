/**
 * Load and persist investigation cases for a linked Atlas ticket.
 *
 * Atlas: DI-ED5A9AC3
 */
"use client";

import { useEffect, useRef } from "react";

import type { useClinicalDoor } from "./clinicalDoorState";
import type { ClinicalPipelineRun } from "./labFindingsApi";
import { investigationKey } from "./ncrInvestigationCases";
import {
  getInvestigation,
  logInvestigationEvent,
  saveInvestigationCases,
} from "./ncrInvestigationApi";

type Door = ReturnType<typeof useClinicalDoor>;

export function useNcrInvestigation(ncId: string | undefined, door: Door) {
  const ready = useRef(false);
  const prev = useRef<ClinicalPipelineRun[]>([]);

  useEffect(() => {
    if (!ncId) return;
    ready.current = false;
    void getInvestigation(ncId)
      .then((data) => {
        const cases = data.cases || [];
        door.hydrateCases(cases);
        prev.current = cases;
        ready.current = true;
      })
      .catch(() => {
        ready.current = true;
      });
  }, [ncId]);

  useEffect(() => {
    if (!ncId || !ready.current) return;
    syncCases(ncId, prev.current, door.linkedCases);
    prev.current = door.linkedCases;
  }, [ncId, door.linkedCases]);

  return {
    logReview: () => {
      if (!ncId) return;
      const why = door.why.trim() || "Opened a case review.";
      const run = door.picked?.run_id || "unknown";
      void logInvestigationEvent(ncId, "review_opened", `${why} Local run ${run}.`);
    },
  };
}

function syncCases(
  ncId: string,
  before: ClinicalPipelineRun[],
  next: ClinicalPipelineRun[],
) {
  if (sameKeys(before, next)) return;
  void saveInvestigationCases(ncId, next);
  for (const row of diff(next, before)) {
    void logInvestigationEvent(ncId, "case_added", eventText("Added", row));
  }
  for (const row of diff(before, next)) {
    void logInvestigationEvent(ncId, "case_removed", eventText("Removed", row));
  }
}

function eventText(verb: string, row: ClinicalPipelineRun): string {
  return `${verb} a case. Local run ${row.run_id || "unknown"}.`;
}

function sameKeys(left: ClinicalPipelineRun[], right: ClinicalPipelineRun[]) {
  return keysOf(left) === keysOf(right);
}

function keysOf(rows: ClinicalPipelineRun[]): string {
  return rows.map(investigationKey).join("|");
}

function diff(
  left: ClinicalPipelineRun[],
  right: ClinicalPipelineRun[],
): ClinicalPipelineRun[] {
  const seen = new Set(right.map(investigationKey));
  return left.filter((row) => !seen.has(investigationKey(row)));
}
