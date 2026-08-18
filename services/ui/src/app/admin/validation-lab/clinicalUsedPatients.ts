/**
 * Recently and frequently used clinical patients for this browser.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
import type { ClinicalPipelineRun } from "./labFindingsApi";

export const USED_PATIENTS_KEY = "leo-validation-lab-used-patients";
const MAX_STORED = 50;
const LIST_SIZE = 8;

export interface UsedPatient {
  patient_id: string;
  patient_name: string;
  nhs_number: string;
  ubrn: string;
  run_id: string;
  last_opened_at: string;
  open_count: number;
}

export function patientKey(row: {
  patient_id?: string;
  nhs_number?: string;
  ubrn?: string;
  run_id?: string;
}): string {
  return row.patient_id || row.nhs_number || row.ubrn || row.run_id || "";
}

export function parseUsedPatients(raw: string | null): UsedPatient[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isUsedPatient).slice(0, MAX_STORED);
  } catch {
    return [];
  }
}

export function mergeUsedPatient(
  existing: UsedPatient[],
  next: ClinicalPipelineRun,
  now: string,
): UsedPatient[] {
  const id = patientKey(next);
  if (!id) return existing;
  const prev = existing.find((row) => patientKey(row) === id);
  const updated: UsedPatient = {
    patient_id: next.patient_id || "",
    patient_name: next.patient_name || "",
    nhs_number: next.nhs_number || "",
    ubrn: next.ubrn || "",
    run_id: next.run_id || "",
    last_opened_at: now,
    open_count: (prev?.open_count || 0) + 1,
  };
  return [updated, ...existing.filter((row) => patientKey(row) !== id)].slice(
    0,
    MAX_STORED,
  );
}

export function recentlyUsed(
  rows: UsedPatient[],
  limit = LIST_SIZE,
): UsedPatient[] {
  return [...rows]
    .sort((a, b) => b.last_opened_at.localeCompare(a.last_opened_at))
    .slice(0, limit);
}

export function frequentlyUsed(
  rows: UsedPatient[],
  limit = LIST_SIZE,
): UsedPatient[] {
  return [...rows]
    .filter((row) => row.open_count >= 2)
    .sort((a, b) => b.open_count - a.open_count)
    .slice(0, limit);
}

export function usedToRun(row: UsedPatient): ClinicalPipelineRun {
  return {
    run_id: row.run_id,
    status: "",
    created_at: row.last_opened_at,
    plan_id: "",
    patient_id: row.patient_id,
    patient_name: row.patient_name,
    nhs_number: row.nhs_number,
    ubrn: row.ubrn,
    run_count: row.open_count,
  };
}

export function recentPickerRows(
  used: UsedPatient[],
  patients: ClinicalPipelineRun[],
): ClinicalPipelineRun[] {
  const personal = recentlyUsed(used).map(usedToRun);
  if (personal.length) return personal;
  return patients.slice(0, LIST_SIZE);
}

export function frequentPickerRows(
  used: UsedPatient[],
  patients: ClinicalPipelineRun[],
): ClinicalPipelineRun[] {
  const personal = frequentlyUsed(used).map(usedToRun);
  if (personal.length) return personal;
  return [...patients]
    .filter((row) => (row.run_count || 0) >= 2)
    .sort((a, b) => (b.run_count || 0) - (a.run_count || 0))
    .slice(0, LIST_SIZE);
}

export function readUsedPatients(): UsedPatient[] {
  if (typeof window === "undefined") return [];
  try {
    return parseUsedPatients(window.localStorage.getItem(USED_PATIENTS_KEY));
  } catch {
    return [];
  }
}

export function recordUsedPatient(row: ClinicalPipelineRun): UsedPatient[] {
  const next = mergeUsedPatient(readUsedPatients(), row, new Date().toISOString());
  try {
    window.localStorage.setItem(USED_PATIENTS_KEY, JSON.stringify(next));
  } catch {
    /* fail-soft */
  }
  return next;
}

function isUsedPatient(value: unknown): value is UsedPatient {
  if (!value || typeof value !== "object") return false;
  const row = value as UsedPatient;
  return typeof row.run_id === "string" && typeof row.open_count === "number";
}
