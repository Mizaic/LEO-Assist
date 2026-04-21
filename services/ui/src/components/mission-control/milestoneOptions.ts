/**
 * Shared milestone slot vocabulary used by EditEpisodeEncountersTab
 * and MilestoneCurationDialog.
 *
 * Atlas trace:
 *   DO: DO-7986A957
 *   DI: DI-4B99678C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7986A957")
 */

export interface MilestoneOption {
  value: string;
  label: string;
}

// Order is important -- the picker presents these top-to-bottom.
// Keep first_* / single-name pairs together so the reviewer reads
// the natural pathway sequence (presentation -> referral -> visit
// -> investigation -> diagnosis -> treatment).
export const MILESTONE_OPTIONS: MilestoneOption[] = [
  { value: "first_presentation", label: "First presentation" },
  { value: "presentation", label: "Presentation" },
  { value: "referral", label: "Referral" },
  { value: "referral_sent", label: "Referral sent" },
  { value: "specialist_visit", label: "Specialist visit" },
  { value: "first_clinic_visit", label: "First clinic visit" },
  { value: "clinic_visit", label: "Clinic visit" },
  { value: "first_clinic", label: "First clinic" },
  { value: "investigation", label: "Investigation" },
  { value: "diagnosis", label: "Diagnosis" },
  { value: "diagnosis_confirmed", label: "Diagnosis confirmed" },
  { value: "treatment_decision", label: "Treatment decision" },
  { value: "treatment", label: "Treatment" },
  { value: "treatment_started", label: "Treatment started" },
  { value: "first_treatment", label: "First treatment" },
  { value: "related", label: "Related" },
];

export function milestoneLabel(value: string): string {
  return (
    MILESTONE_OPTIONS.find((opt) => opt.value === value)?.label ??
    value.replaceAll("_", " ")
  );
}
