"use client";

/**
 * State + submit logic for the 5-step Validation Lab patient wizard:
 * patient -> profile (PMH) -> encounters -> referral -> submit + poll.
 *
 * Atlas: DI-724CD8A5 / DI-2289D095
 */

import { useCallback, useState } from "react";
import {
  createCase,
  pollRunUntilTerminal,
  startRun,
  type LabRun,
  type PmhCategory,
} from "./labApi";

export interface PmhRow {
  id: string;
  category: PmhCategory;
  conceptId: string;
  term: string;
}

export interface EncounterRow {
  id: string;
  label: string;
  text: string;
  date: string;
}

let rowSeq = 0;
function newRowId(prefix: string): string {
  rowSeq += 1;
  return `${prefix}-${rowSeq}`;
}

const DEFAULT_PHASES = ["extraction", "verification", "persist", "guidance", "sbar"];
const DEFAULT_PLAN_ID = "pd-referral-assessment";

export function useCreatePatientWizard(onCreated?: (caseId: string) => void) {
  const [step, setStep] = useState(0);

  const [title, setTitle] = useState("");
  const [patientName, setPatientName] = useState("");
  const [patientAge, setPatientAge] = useState("");
  const [patientSex, setPatientSex] = useState("");

  const [pmhRows, setPmhRows] = useState<PmhRow[]>([]);
  const [encounterRows, setEncounterRows] = useState<EncounterRow[]>([]);
  const [referralText, setReferralText] = useState("");
  const [planId, setPlanId] = useState(DEFAULT_PLAN_ID);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [run, setRun] = useState<LabRun | null>(null);
  const [polling, setPolling] = useState(false);

  const addPmhRow = useCallback((category: PmhCategory) => {
    setPmhRows((prev) => [
      ...prev,
      { id: newRowId("pmh"), category, conceptId: "", term: "" },
    ]);
  }, []);

  const updatePmhRow = useCallback((id: string, patch: Partial<PmhRow>) => {
    setPmhRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }, []);

  const removePmhRow = useCallback((id: string) => {
    setPmhRows((prev) => prev.filter((row) => row.id !== id));
  }, []);

  const addEncounterRow = useCallback(() => {
    setEncounterRows((prev) => [
      ...prev,
      { id: newRowId("enc"), label: "", text: "", date: "" },
    ]);
  }, []);

  const updateEncounterRow = useCallback(
    (id: string, patch: Partial<EncounterRow>) => {
      setEncounterRows((prev) =>
        prev.map((row) => (row.id === id ? { ...row, ...patch } : row)),
      );
    },
    [],
  );

  const removeEncounterRow = useCallback((id: string) => {
    setEncounterRows((prev) => prev.filter((row) => row.id !== id));
  }, []);

  const goNext = useCallback(() => setStep((s) => Math.min(4, s + 1)), []);
  const goBack = useCallback(() => setStep((s) => Math.max(0, s - 1)), []);

  const reset = useCallback(() => {
    setStep(0);
    setTitle("");
    setPatientName("");
    setPatientAge("");
    setPatientSex("");
    setPmhRows([]);
    setEncounterRows([]);
    setReferralText("");
    setPlanId(DEFAULT_PLAN_ID);
    setError(null);
    setCaseId(null);
    setRun(null);
  }, []);

  const submit = useCallback(async () => {
    setBusy(true);
    setError(null);
    setRun(null);
    try {
      const created = await createCase({
        title: title.trim() || "Untitled test patient",
        referral_text: referralText,
        plan_id: planId,
        patient_age: patientAge.trim() ? Number(patientAge) : null,
        patient_sex: patientSex || null,
        patient_name: patientName.trim(),
        pmh: pmhRows
          .filter((row) => row.conceptId)
          .map((row) => ({
            category: row.category,
            concept_id: row.conceptId,
            term: row.term,
          })),
        encounters: encounterRows
          .filter((row) => row.text.trim())
          .map((row) => ({ label: row.label, text: row.text, date: row.date })),
      });
      setCaseId(created.id);
      onCreated?.(created.id);
      const started = await startRun(created.id, {
        plan_id: planId,
        phase_ids: DEFAULT_PHASES,
        persist_mode: "production",
      });
      setRun(started.run);
      setPolling(true);
      const finalRun = await pollRunUntilTerminal(created.id, started.run.id);
      setRun(finalRun);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit referral failed");
    } finally {
      setPolling(false);
      setBusy(false);
    }
  }, [
    title,
    referralText,
    planId,
    patientAge,
    patientSex,
    patientName,
    pmhRows,
    encounterRows,
    onCreated,
  ]);

  return {
    step,
    setStep,
    goNext,
    goBack,
    title,
    setTitle,
    patientName,
    setPatientName,
    patientAge,
    setPatientAge,
    patientSex,
    setPatientSex,
    pmhRows,
    addPmhRow,
    updatePmhRow,
    removePmhRow,
    encounterRows,
    addEncounterRow,
    updateEncounterRow,
    removeEncounterRow,
    referralText,
    setReferralText,
    planId,
    setPlanId,
    busy,
    polling,
    error,
    caseId,
    run,
    submit,
    reset,
  };
}
