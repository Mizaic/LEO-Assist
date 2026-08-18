/**
 * Clinical door lookup and used-patient state.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import { useEffect, useMemo, useState } from "react";

import {
  frequentPickerRows,
  readUsedPatients,
  recentPickerRows,
  recordUsedPatient,
  type UsedPatient,
} from "./clinicalUsedPatients";
import {
  listClinicalPatients,
  listClinicalPipelineRuns,
  type ClinicalPipelineRun,
  type ClinicalSearchMode,
} from "./labFindingsApi";
import {
  addInvestigationCase,
  removeInvestigationCase,
} from "./ncrInvestigationCases";
import type { RunReviewTarget } from "./RunReviewLightbox";

interface LookupMutators {
  setRows: (rows: ClinicalPipelineRun[]) => void;
  setSearched: (value: boolean) => void;
  setPicked: (row: ClinicalPipelineRun | null) => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string) => void;
}

export function useClinicalDoor(onReview: (target: RunReviewTarget) => void) {
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<ClinicalSearchMode>("patient");
  const [rows, setRows] = useState<ClinicalPipelineRun[]>([]);
  const [patients, setPatients] = useState<ClinicalPipelineRun[]>([]);
  const [used, setUsed] = useState<UsedPatient[]>([]);
  const [picked, setPicked] = useState<ClinicalPipelineRun | null>(null);
  const [linkedCases, setLinkedCases] = useState<ClinicalPipelineRun[]>([]);
  const [why, setWhy] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const mut: LookupMutators = {
    setRows,
    setSearched,
    setPicked,
    setBusy,
    setError,
  };

  useEffect(() => {
    setUsed(readUsedPatients());
    void loadAllPatients(setPatients, setBusy, setError);
  }, []);

  const recent = useMemo(
    () => recentPickerRows(used, patients),
    [used, patients],
  );
  const frequent = useMemo(
    () => frequentPickerRows(used, patients),
    [used, patients],
  );

  return {
    query,
    setQuery,
    searchMode,
    setSearchMode: (mode: ClinicalSearchMode) => {
      setSearchMode(mode);
      setRows([]);
      setSearched(false);
    },
    rows,
    patients,
    picked,
    linkedCases,
    why,
    setWhy,
    error,
    busy,
    searched,
    recent,
    frequent,
    onFind: () => void findRuns(query, searchMode, mut, setLinkedCases),
    onPick: (row: ClinicalPipelineRun) =>
      void pickPatient(row, mut, setLinkedCases),
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
    onOpen: () => openPicked(picked, why, setUsed, onReview),
  };
}

async function loadAllPatients(
  setPatients: (rows: ClinicalPipelineRun[]) => void,
  setBusy: (busy: boolean) => void,
  setError: (error: string) => void,
) {
  setBusy(true);
  setError("");
  try {
    setPatients(await listClinicalPatients());
  } catch (err: unknown) {
    setError(err instanceof Error ? err.message : "Could not load patients");
  } finally {
    setBusy(false);
  }
}

async function findRuns(
  query: string,
  mode: ClinicalSearchMode,
  mut: LookupMutators,
  setLinkedCases?: (
    fn: (prev: ClinicalPipelineRun[]) => ClinicalPipelineRun[],
  ) => void,
) {
  const q = query.trim();
  if (!q) return;
  mut.setBusy(true);
  mut.setError("");
  try {
    const found = await listClinicalPipelineRuns({ q, mode });
    mut.setRows(found);
    mut.setSearched(true);
    const only = found.length === 1 ? found[0] : null;
    mut.setPicked(only);
    if (only && setLinkedCases) {
      setLinkedCases((prev) => addInvestigationCase(prev, only));
    }
  } catch (err: unknown) {
    mut.setError(err instanceof Error ? err.message : "Could not find that case");
  } finally {
    mut.setBusy(false);
  }
}

async function pickPatient(
  row: ClinicalPipelineRun,
  mut: LookupMutators,
  setLinkedCases: (
    fn: (prev: ClinicalPipelineRun[]) => ClinicalPipelineRun[],
  ) => void,
) {
  const chosen =
    (row.run_count || 1) <= 1 && row.run_id
      ? row
      : row.nhs_number || row.patient_id
        ? null
        : row;
  if (chosen) {
    setLinkedCases((prev) => addInvestigationCase(prev, chosen));
    mut.setPicked(chosen);
    return;
  }
  const key = row.nhs_number || row.patient_id;
  if (!key) return;
  await findRuns(key, "patient", mut, setLinkedCases);
}

function investigationMatch(
  left: ClinicalPipelineRun,
  right: ClinicalPipelineRun,
): boolean {
  return (
    (left.run_id && left.run_id === right.run_id) ||
    (!!left.patient_id && left.patient_id === right.patient_id)
  );
}

function openPicked(
  picked: ClinicalPipelineRun | null,
  why: string,
  setUsed: (rows: UsedPatient[]) => void,
  onReview: (target: RunReviewTarget) => void,
) {
  if (!picked) return;
  setUsed(recordUsedPatient(picked));
  onReview({
    title: picked.patient_name || picked.patient_id || "Clinical run",
    pipelineRunId: picked.run_id,
    status: picked.status,
    terminal: true,
    readOnly: true,
    whyOpened: why.trim(),
  });
}
