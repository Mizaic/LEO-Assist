/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-21936FDD")
 */
export const MILESTONE_OPTIONS = [
  "benign_closure",
  "diagnosis",
  "first_presentation",
  "referral",
  "specialist_outcome_letter",
  "specialist_visit",
  "treatment_start",
] as const;

export const ASSERTION_OPTIONS = [
  "absent",
  "cancelled",
  "declined",
  "family",
  "historical",
  "hypothetical",
  "planned",
  "possible",
  "present",
  "refuted",
] as const;
