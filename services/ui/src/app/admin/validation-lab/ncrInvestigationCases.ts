/**
 * Local investigation cases for an Atlas NCR.
 * NHS number and referral number stay in LEO.
 *
 * Atlas: DI-287FFFD0 / DI-ED5A9AC3
 */

import type { ClinicalPipelineRun } from "./labFindingsApi";

export function investigationKey(row: ClinicalPipelineRun): string {
  return (
    row.run_id ||
    `${row.patient_id}|${row.nhs_number || ""}|${row.ubrn || ""}`
  );
}

export function addInvestigationCase(
  list: ClinicalPipelineRun[],
  row: ClinicalPipelineRun,
): ClinicalPipelineRun[] {
  const key = investigationKey(row);
  if (list.some((item) => investigationKey(item) === key)) return list;
  return [...list, row];
}

export function removeInvestigationCase(
  list: ClinicalPipelineRun[],
  row: ClinicalPipelineRun,
): ClinicalPipelineRun[] {
  const key = investigationKey(row);
  return list.filter((item) => investigationKey(item) !== key);
}

export function caseLabel(row: ClinicalPipelineRun): string {
  const name = row.patient_name || row.patient_id || "Case";
  const bits = [name];
  if (row.nhs_number) bits.push(`NHS ${row.nhs_number}`);
  if (row.ubrn) bits.push(`Referral ${row.ubrn}`);
  return bits.join(" -- ");
}
