/**
 * Shared constants for the NCDA Section 7 "prior consultations" surfaces:
 *   - ConsultationsSection  (how many)
 *   - MultipleConsultationsSection  (why)
 *
 * Mirrors libs/oncology/prior_consultations.py NCDA_FACTOR_LABELS and
 * the NCDA pro forma groupings so the UI matches the GP's wording.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
// ---------------------------------------------------------------------------
// Factor labels
// ---------------------------------------------------------------------------

export const FACTOR_LABELS: Record<string, string> = {
  co_morbidity_blurring: "Co-morbidity blurring picture",
  different_initial_diagnosis: "Symptoms suggested different initial diagnosis",
  different_malignancy: "Symptoms suggested different malignancy",
  incomplete_symptom_account: "Didn't have a full account of symptoms",
  low_perceived_malignancy_probability: "Perceived low probability of malignancy",
  frequent_attender_vague_symptoms: "Frequent attender with vague symptoms",
  declined_investigation: "Declined investigation or examination",
  declined_referral: "Declined referral or admission",
  did_not_attend_followup: "Did not attend for follow-up",
  abnormal_result_not_followed_up: "Abnormal result not followed up",
  poor_communication_with_patient: "Poor communication with the patient",
  inadequate_history_taken: "Inadequate history taken",
  examination_not_performed: "Appropriate examination not performed",
  investigation_not_ordered: "Appropriate investigation not ordered",
  wrong_specialty_referral: "Referred to the 'wrong' specialty",
  poor_communication_within_practice: "Poor communication within the practice",
  seen_by_multiple_health_professionals: "Seen by multiple health professionals",
  reassurance_from_negative_investigation: "Reassurance from negative investigation",
  investigation_suggested_benign_cause: "Investigation suggested benign cause",
  consultations_to_discuss_test_results: "Consultation(s) to discuss test results",
  no_reason: "No reason",
  other_reason: "Other",
  no_multiple_consultations: "No multiple consultations",
  not_known: "Not known",
};

// ---------------------------------------------------------------------------
// NCDA pro-forma category groupings
// ---------------------------------------------------------------------------

/**
 * Maps each factor code to one of the four top-level NCDA categories.
 * Used by MultipleConsultationsSection to group bars and match the pro-forma.
 */
export const FACTOR_TO_CATEGORY: Record<string, string> = {
  co_morbidity_blurring:                  "Complexity of presentation",
  different_initial_diagnosis:            "Complexity of presentation",
  different_malignancy:                   "Complexity of presentation",
  incomplete_symptom_account:             "Complexity of presentation",
  low_perceived_malignancy_probability:   "Complexity of presentation",
  frequent_attender_vague_symptoms:       "Complexity of presentation",
  declined_investigation:                 "Patient factors",
  declined_referral:                      "Patient factors",
  did_not_attend_followup:                "Patient factors",
  poor_communication_with_patient:        "GP factors",
  inadequate_history_taken:               "GP factors",
  examination_not_performed:              "GP factors",
  investigation_not_ordered:              "GP factors",
  wrong_specialty_referral:               "GP factors",
  poor_communication_within_practice:     "GP factors",
  seen_by_multiple_health_professionals:  "GP factors",
  abnormal_result_not_followed_up:        "Diagnostic process",
  reassurance_from_negative_investigation: "Diagnostic process",
  investigation_suggested_benign_cause:   "Diagnostic process",
  consultations_to_discuss_test_results:  "Diagnostic process",
  no_reason:                              "Other",
  other_reason:                           "Other",
  not_known:                              "Other",
};

export const NCDA_CATEGORIES = [
  "Complexity of presentation",
  "Patient factors",
  "GP factors",
  "Diagnostic process",
  "Other",
] as const;

// ---------------------------------------------------------------------------
// Bucket definitions
// ---------------------------------------------------------------------------

/**
 * NCDA threshold: >= 3 consultations = "multiple consultations".
 * Buckets are split to cleanly show the 0-2 (not multiple) vs 3+ (multiple) divide.
 */
export type BucketKey = "0" | "1" | "2" | "3-4" | "5-7" | "8+";

export const BUCKET_ORDER: BucketKey[] = ["0", "1", "2", "3-4", "5-7", "8+"];

export const BUCKET_LABELS: Record<BucketKey, string> = {
  "0":   "0 consultations",
  "1":   "1 consultation",
  "2":   "2 consultations",
  "3-4": "3-4 consultations \u2014 NCDA \u201cmultiple\u201d",
  "5-7": "5-7 consultations",
  "8+":  "8+ consultations",
};

/** Buckets 3-4, 5-7, 8+ are "multiple" territory (NCDA threshold >= 3). */
export const BUCKET_IS_MULTIPLE: Record<BucketKey, boolean> = {
  "0":   false,
  "1":   false,
  "2":   false,
  "3-4": true,
  "5-7": true,
  "8+":  true,
};

export const BUCKET_COLOURS: Record<BucketKey, string> = {
  "0":   "#94a3b8",
  "1":   "#64748b",
  "2":   "#94a3b8",
  "3-4": "#3b82f6",
  "5-7": "#f59e0b",
  "8+":  "#ef4444",
};

// ---------------------------------------------------------------------------
// Contact-type meta
// ---------------------------------------------------------------------------

export type ContactTypeKey =
  | "f2f"
  | "phone"
  | "nurse"
  | "email"
  | "specialist_clinic"
  | "home_visit"
  | "phlebotomy"
  | "result_review";

export const CONTACT_META: Array<{ key: ContactTypeKey; label: string }> = [
  { key: "f2f",              label: "Face-to-face (clinic)" },
  { key: "phone",            label: "Telephone" },
  { key: "nurse",            label: "Nurse / Nurse Practitioner" },
  { key: "email",            label: "Email / secure message" },
  { key: "specialist_clinic", label: "Specialist clinic attendance" },
  { key: "home_visit",       label: "Home visit" },
  { key: "phlebotomy",       label: "Phlebotomy / blood draw" },
  { key: "result_review",    label: "Result review (auto-filed)" },
];
