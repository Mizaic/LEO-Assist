/**
 * Clinical door investigation state -- simplified.
 * Patient loading and search are now owned by RunPickerGrid.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import { useState } from "react";

import {
  addInvestigationCase,
  removeInvestigationCase,
} from "./ncrInvestigationCases";
import type { ClinicalPipelineRun } from "./labFindingsApi";
import type { RunReviewTarget } from "./RunReviewLightbox";

export function useClinicalDoor(onReview: (target: RunReviewTarget) => void) {
  const [linkedCases, setLinkedCases] = useState<ClinicalPipelineRun[]>([]);
  const [picked, setPicked] = useState<ClinicalPipelineRun | null>(null);
  const [why, setWhy] = useState("");
  const [error] = useState("");

  return {
    linkedCases,
    picked,
    why,
    setWhy,
    error,
    onPick: (row: ClinicalPipelineRun) => {
      setLinkedCases((prev) => addInvestigationCase(prev, row));
      setPicked(row);
    },
    onSelectCase: (row: ClinicalPipelineRun) => setPicked(row),
    onRemoveCase: (row: ClinicalPipelineRun) => {
      setLinkedCases((prev) => removeInvestigationCase(prev, row));
      setPicked((cur) =>
        cur && investigationMatch(cur, row) ? null : cur,
      );
    },
    onBackPick: () => setPicked(null),
    onClearInvestigation: () => {
      setPicked(null);
      setLinkedCases([]);
    },
    hydrateCases: (rows: ClinicalPipelineRun[]) => setLinkedCases(rows),
    onOpen: () => openPicked(picked, why, onReview),
  };
}

function investigationMatch(
  left: ClinicalPipelineRun,
  right: ClinicalPipelineRun,
): boolean {
  return (
    (!!left.run_id && left.run_id === right.run_id) ||
    (!!left.patient_id && left.patient_id === right.patient_id)
  );
}

function openPicked(
  picked: ClinicalPipelineRun | null,
  why: string,
  onReview: (target: RunReviewTarget) => void,
) {
  if (!picked) return;
  onReview({
    title: picked.patient_name || picked.patient_id || "Clinical run",
    pipelineRunId: picked.run_id,
    status: picked.status,
    terminal: true,
    readOnly: true,
    whyOpened: why.trim(),
  });
}
