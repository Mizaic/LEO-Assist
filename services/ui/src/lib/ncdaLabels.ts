/**
 * NCDA reviewer UI label dictionary.
 *
 * Centralises every UI string for the NCDA pathway timeline, audit tile,
 * and active-learning queue so reading-age 9-11 enforcement (per
 * .cursor/rules/health-literacy.mdc) happens in one place.
 *
 * Plain-language wording rules for editors:
 *   - Use short words (1-2 syllables) where possible.
 *   - Avoid medical jargon. Prefer "cancer found" over "malignancy confirmed".
 *   - Use active voice. "We rule out cancer" not "Cancer is being ruled out".
 *   - Sentences <= 12 words.
 *   - Use "your" when speaking to a patient; "the patient" when speaking
 *     to a clinician (this dictionary is for the clinician/reviewer).
 */

export const NCDA_ROLE_LABELS = {
  ftr: "Urgent referral",
  seen: "First hospital visit",
  dx_found: "Cancer found",
  dx_excluded: "Cancer ruled out",
  treatment: "Treatment began",
  none: "Not part of the pathway",
} as const;

export const NCDA_COHORT_LABELS = {
  "1a": "Standard 2WW - cancer found",
  "1b": "Standard 2WW - cancer ruled out",
  "2": "Urgent referral - outcome pending",
  "3": "Cancer found without urgent referral",
  "4": "Multiple pathways",
} as const;

export const NCDA_BREACH_TOOLTIPS = {
  fds_28:
    "National rule: cancer should be found or ruled out within 28 days of urgent referral.",
  treatment_31:
    "National rule: treatment should start within 31 days of finding cancer.",
  referral_62:
    "National rule: treatment should start within 62 days of urgent referral.",
} as const;

export const NCDA_BAND_HELPERS = {
  green: "Inside this hospital's typical time.",
  amber: "Slower than usual but inside the national rule.",
  red: "Past the national rule. Needs review.",
  unknown: "Date is missing or has not been entered yet.",
} as const;

export const NCDA_AUDIT_FINDING_LABELS = {
  role_mismatch: "Label does not match the encounter text",
  out_of_sequence: "Dates are out of order",
  multiple_anchors_per_role: "More than one anchor of this kind",
  wrong_site: "Cancer site does not match",
  llm_relabel_suggestion: "Suggested change for review",
} as const;

export const NCDA_AUDIT_SEVERITY_LABELS = {
  high: "Must fix before tidy",
  medium: "Recommended fix",
  low: "Heads up",
  info: "Audit trail",
} as const;

export const NCDA_REVIEWER_ACTIONS = {
  mark_correct: "Looks right",
  relabel: "Pick a different label",
  delete_milestone: "Remove this milestone",
  add_to_read_code_lookup: "Add this code to the lookup",
} as const;

export const NCDA_QUEUE_REASON_LABELS = {
  low_confidence: "Computer is unsure",
  cohort_3: "Cancer found without urgent referral",
  seen_missing: "First hospital visit not found",
  treatment_missing: "Treatment not found yet",
  multi_pair: "Several pathways at once",
} as const;

export type NcdaRoleKey = keyof typeof NCDA_ROLE_LABELS;
export type NcdaCohortKey = keyof typeof NCDA_COHORT_LABELS;
export type NcdaAuditFindingKey = keyof typeof NCDA_AUDIT_FINDING_LABELS;
export type NcdaSeverityKey = keyof typeof NCDA_AUDIT_SEVERITY_LABELS;
