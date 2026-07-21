/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

/**
 * State + submit logic for the Validation Lab patient wizard.
 *
 * Atlas: DI-724CD8A5 / DI-2289D095 / DI-D6E5F94E
 */

import { useCallback, useState } from "react";
import {
  createCase,
  pollRunUntilTerminal,
  previewPmhNarrative,
  startRun,
  type AgTurnInput,
  type LabRun,
  type LabScenarioType,
  type PmhCategory,
} from "./labApi";
import { DEFAULT_LAB_PHASES, DEFAULT_LAB_PLAN_ID } from "./labRun";
import type { AgTurnCategory, AgTurnRow } from "./WizardAgThreadSteps";

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

export type WizardScenario =
  | "generic_referral"
  | "generic_ag"
  | "spo_ag"
  | "ras_referral";

let rowSeq = 0;
function newRowId(prefix: string): string {
  rowSeq += 1;
  return `${prefix}-${rowSeq}`;
}

function scenarioToCaseType(scenario: WizardScenario): "referral" | "ag" {
  return scenario === "generic_ag" || scenario === "spo_ag" ? "ag" : "referral";
}

function scenarioToApiType(scenario: WizardScenario): LabScenarioType {
  if (scenario === "spo_ag") return "spo_ag";
  if (scenario === "ras_referral") return "ras_referral";
  return "generic";
}

function isSpoa(scenario: WizardScenario): boolean {
  return scenario === "spo_ag" || scenario === "ras_referral";
}

export function useCreatePatientWizard(onCreated?: (caseId: string) => void) {
  const [step, setStep] = useState(0);
  const [scenario, setScenario] = useState<WizardScenario>("generic_referral");

  const [title, setTitle] = useState("");
  const [patientName, setPatientName] = useState("");
  const [patientAge, setPatientAge] = useState("");
  const [patientSex, setPatientSex] = useState("");
  const [nhsNumber, setNhsNumber] = useState("");
  const [gpPracticeName, setGpPracticeName] = useState("");

  const [pmhRows, setPmhRows] = useState<PmhRow[]>([]);
  const [encounterRows, setEncounterRows] = useState<EncounterRow[]>([]);
  const [gpConsultLabel, setGpConsultLabel] = useState("GP consultation");
  const [gpConsultText, setGpConsultText] = useState("");
  const [gpConsultDate, setGpConsultDate] = useState("");
  const [reasonForSubmission, setReasonForSubmission] = useState("");
  const [pmhPreview, setPmhPreview] = useState<string>("");

  const [referralText, setReferralText] = useState("");
  const [planId, setPlanId] = useState(DEFAULT_LAB_PLAN_ID);
  const [agTurnRows, setAgTurnRows] = useState<AgTurnRow[]>([]);
  const [agResponseText, setAgResponseText] = useState("");
  const [agRequestAttachments, setAgRequestAttachments] = useState<string[]>([]);
  const [agUbrn, setAgUbrn] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [run, setRun] = useState<LabRun | null>(null);
  const [polling, setPolling] = useState(false);

  const caseType = scenarioToCaseType(scenario);
  const spoa = isSpoa(scenario);

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

  const addAgTurn = useCallback((category: AgTurnCategory) => {
    setAgTurnRows((prev) => [
      ...prev,
      {
        id: newRowId("ag"),
        category,
        note: "",
        sentDatetime: "",
        attachmentText: "",
      },
    ]);
  }, []);

  const updateAgTurn = useCallback((id: string, patch: Partial<AgTurnRow>) => {
    setAgTurnRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }, []);

  const removeAgTurn = useCallback((id: string) => {
    setAgTurnRows((prev) => prev.filter((row) => row.id !== id));
  }, []);

  const addAgRequestAttachment = useCallback(() => {
    setAgRequestAttachments((prev) => [...prev, ""]);
  }, []);

  const updateAgRequestAttachment = useCallback((index: number, value: string) => {
    setAgRequestAttachments((prev) =>
      prev.map((item, idx) => (idx === index ? value : item)),
    );
  }, []);

  const removeAgRequestAttachment = useCallback((index: number) => {
    setAgRequestAttachments((prev) => prev.filter((_, idx) => idx !== index));
  }, []);

  const refreshPmhPreview = useCallback(async () => {
    const pmh = pmhRows
      .filter((row) => row.conceptId)
      .map((row) => ({
        category: row.category,
        concept_id: row.conceptId,
        term: row.term,
      }));
    if (!pmh.length) {
      setPmhPreview("");
      return;
    }
    try {
      const result = await previewPmhNarrative({ pmh, seed: title || "preview" });
      setPmhPreview(result.narrative || "");
    } catch {
      setPmhPreview("");
    }
  }, [pmhRows, title]);

  const goNext = useCallback(() => setStep((s) => Math.min(4, s + 1)), []);
  const goBack = useCallback(() => setStep((s) => Math.max(0, s - 1)), []);

  const reset = useCallback(() => {
    setStep(0);
    setScenario("generic_referral");
    setTitle("");
    setPatientName("");
    setPatientAge("");
    setPatientSex("");
    setNhsNumber("");
    setGpPracticeName("");
    setPmhRows([]);
    setEncounterRows([]);
    setGpConsultLabel("GP consultation");
    setGpConsultText("");
    setGpConsultDate("");
    setReasonForSubmission("");
    setPmhPreview("");
    setReferralText("");
    setPlanId(DEFAULT_LAB_PLAN_ID);
    setAgTurnRows([]);
    setAgResponseText("");
    setAgRequestAttachments([]);
    setAgUbrn("");
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
        case_type: caseType,
        scenario_type: scenarioToApiType(scenario),
        referral_text: referralText,
        plan_id: planId,
        patient_age: patientAge.trim() ? Number(patientAge) : null,
        patient_sex: patientSex || null,
        patient_name: patientName.trim(),
        nhs_number: nhsNumber.trim(),
        gp_practice_name: gpPracticeName.trim(),
        reason_for_submission: reasonForSubmission.trim(),
        gp_encounter: spoa
          ? {
              label: gpConsultLabel,
              text: gpConsultText,
              date: gpConsultDate,
            }
          : undefined,
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
        ag_thread: agTurnRows
          .filter((row) => row.note.trim())
          .map(
            (row): AgTurnInput => ({
              category: row.category,
              note: row.note,
              sent_datetime: row.sentDatetime,
              attachment_text: row.attachmentText,
            }),
          ),
        ag_response_text: agResponseText,
        ag_request_attachments: agRequestAttachments.filter((item) => item.trim()),
        ag_ubrn: agUbrn.trim(),
      });
      setCaseId(created.id);
      onCreated?.(created.id);
      const started = await startRun(created.id, {
        plan_id: planId,
        phase_ids: DEFAULT_LAB_PHASES,
        persist_mode: "production",
      });
      setRun(started.run);
      setPolling(true);
      const finalRun = await pollRunUntilTerminal(created.id, started.run.id);
      setRun(finalRun);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed");
    } finally {
      setPolling(false);
      setBusy(false);
    }
  }, [
    title,
    caseType,
    scenario,
    referralText,
    planId,
    patientAge,
    patientSex,
    patientName,
    nhsNumber,
    gpPracticeName,
    reasonForSubmission,
    spoa,
    gpConsultLabel,
    gpConsultText,
    gpConsultDate,
    pmhRows,
    encounterRows,
    agTurnRows,
    agResponseText,
    agRequestAttachments,
    agUbrn,
    onCreated,
  ]);

  return {
    step,
    setStep,
    goNext,
    goBack,
    scenario,
    setScenario,
    caseType,
    spoa,
    title,
    setTitle,
    patientName,
    setPatientName,
    patientAge,
    setPatientAge,
    patientSex,
    setPatientSex,
    nhsNumber,
    setNhsNumber,
    gpPracticeName,
    setGpPracticeName,
    pmhRows,
    addPmhRow,
    updatePmhRow,
    removePmhRow,
    encounterRows,
    addEncounterRow,
    updateEncounterRow,
    removeEncounterRow,
    gpConsultLabel,
    setGpConsultLabel,
    gpConsultText,
    setGpConsultText,
    gpConsultDate,
    setGpConsultDate,
    reasonForSubmission,
    setReasonForSubmission,
    pmhPreview,
    refreshPmhPreview,
    referralText,
    setReferralText,
    planId,
    setPlanId,
    agTurnRows,
    addAgTurn,
    updateAgTurn,
    removeAgTurn,
    agResponseText,
    setAgResponseText,
    agRequestAttachments,
    addAgRequestAttachment,
    updateAgRequestAttachment,
    removeAgRequestAttachment,
    agUbrn,
    setAgUbrn,
    busy,
    polling,
    error,
    caseId,
    run,
    submit,
    reset,
  };
}
