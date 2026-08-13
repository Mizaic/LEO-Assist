/**
 * Clinical door lookup and used-patient state.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
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
} from "./labFindingsApi";
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
  const [rows, setRows] = useState<ClinicalPipelineRun[]>([]);
  const [patients, setPatients] = useState<ClinicalPipelineRun[]>([]);
  const [used, setUsed] = useState<UsedPatient[]>([]);
  const [picked, setPicked] = useState<ClinicalPipelineRun | null>(null);
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
    rows,
    patients,
    picked,
    why,
    setWhy,
    error,
    busy,
    searched,
    recent,
    frequent,
    onFind: () => void findRuns(query, mut),
    onPick: (row: ClinicalPipelineRun) => void pickPatient(row, mut),
    onBackPick: () => setPicked(null),
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

async function findRuns(query: string, mut: LookupMutators) {
  const q = query.trim();
  if (!q) return;
  mut.setBusy(true);
  mut.setError("");
  try {
    const found = await listClinicalPipelineRuns({ q });
    mut.setRows(found);
    mut.setSearched(true);
    mut.setPicked(found.length === 1 ? found[0] : null);
  } catch (err: unknown) {
    mut.setError(err instanceof Error ? err.message : "Could not find that case");
  } finally {
    mut.setBusy(false);
  }
}

async function pickPatient(row: ClinicalPipelineRun, mut: LookupMutators) {
  if ((row.run_count || 1) <= 1 && row.run_id) {
    mut.setPicked(row);
    return;
  }
  const key = row.nhs_number || row.patient_id;
  if (!key) {
    mut.setPicked(row);
    return;
  }
  await findRuns(key, mut);
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
