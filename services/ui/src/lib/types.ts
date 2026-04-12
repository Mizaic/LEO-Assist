export interface Patient {
  patient_id: string;
  encounter_count: number;
  reviewed_count?: number;
  progress?: number;
}

export interface EncounterSummary {
  encounter_id: string;
  date: string;
  text?: string;
  coded_count?: number;
  flags?: string;
}

export interface CodedLink {
  concept_id: string;
  term?: string;
  read_code?: string;
  semantic_tag?: string;
  /** DOCUMENTS relationship: evidence text from encounter */
  evidence?: string;
  /** DOCUMENTS relationship: de-identified sentence containing the mention */
  evidence_sentence?: string;
  /** DOCUMENTS relationship: index of the sentence in the encounter payload */
  sentence_index?: number;
  /** DOCUMENTS relationship: mention offsets in evidence_sentence */
  evidence_start?: number;
  evidence_end?: number;
  /** DOCUMENTS relationship: extraction confidence (0-1) */
  confidence?: number;
  /** DOCUMENTS relationship: domain (e.g. clinical_finding) */
  domain?: string;
  /** DOCUMENTS relationship: negated, uncertain, historical, etc. */
  context?: Record<string, unknown>;
  /** Assertion parsed from context.assertion (present/absent/possible/historical/hypothetical/family/declined/cancelled) */
  assertion?: string;
  /** DOCUMENTS relationship: value, unit, reference_range, interpretation */
  modifiers?: Record<string, unknown>;
  /** DOCUMENTS relationship: when the link was coded */
  coded_at?: string;
}

export interface TimelineEvent {
  encounter_date: string;
  encounter_id: string;
  concept_id: string;
  term: string;
  semantic_tag: string;
  read_code?: string;
  assertion: string;
  confidence?: number;
  domain?: string;
  decision_tier?: number;
}

export interface TermSearchResult {
  snomed_concept_id: string;
  term: string;
  read_code?: string;
  semantic_tag?: string;
  module_id?: string;
  score?: number;
  icd10?: string;
  from_surface_form?: boolean;
}

export interface Correction {
  type: string;
  text: string;
  detail: string;
  time: string;
}

export interface LLMUsage {
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  total_tokens: number;
  llm_calls: number;
  cost_usd?: number;
}

export interface PipelineRunResponse {
  run_id: string;
  processed_encounters: number;
  queued_for_review: number;
  auto_approved?: number;
  rejected_hard_fail: number;
  warnings_only: number;
  llm_usage?: LLMUsage;
}

export interface ReviewTaskSummary {
  task_id: string;
  candidate_id: string;
  patient_id: string;
  encounter_id: string;
  priority: number;
  status: string;
  warning_count: number;
  created_at: string;
  updated_at: string;
}

export interface TermContext {
  negated: boolean;
  uncertain: boolean;
  historical: boolean;
  subject: "patient" | "family" | "other";
  temporality: "present" | "past" | "planned" | "hypothetical" | "unknown";
}

export interface TermCodingProposal {
  snomed_concept_id?: string;
  read_code?: string;
  snomed_term?: string;
  score?: number;
  source?: string;
}

export interface EncounterTerm {
  term_id: string;
  text: string;
  span_start: number;
  span_end: number;
  context: TermContext;
  coding: TermCodingProposal;
  evidence_text: string;
  extraction_method: string;
  extraction_confidence?: number;
  /** New training-schema: direct semantic tag (e.g. "procedure", "disorder") */
  semantic_tag?: string;
  /** New training-schema: "present" | "absent" | "family" — overrides individual context flags when present */
  assertion?: string;
}

export interface EncounterSentence {
  sentence_id: string;
  start: number;
  end: number;
  text: string;
  section?: string;
  terms: EncounterTerm[];
}

export interface EncounterCandidate {
  candidate_id: string;
  patient_id: string;
  encounter_id: string;
  date: string;
  source_hash: string;
  deidentified_hash: string;
  deidentified_text: string;
  approval_status: string;
  hard_fail_reasons: string[];
  warning_reasons: string[];
  sentences: EncounterSentence[];
  audit_events?: unknown[];
  llm_usage_json?: string;
}

export interface ReviewTaskDetail {
  task: ReviewTaskSummary;
  candidate: EncounterCandidate;
}

export interface AskLeoSmartResult {
  /** Verified SNOMED concept chosen from real search results. Null when ambiguous or not codeable. */
  matched_candidate: TermSearchResult | null;
  /** LEO's explanation for the choice or the reason for ambiguity. */
  reason: string;
  /** True when LEO could not determine the correct code from available evidence. */
  is_ambiguous: boolean;
  /** Search query LEO generated for the second-pass search, if one was performed. */
  alternative_query_used: string | null;
  /**
   * Set when LEO detected the entity should not be coded -- e.g. procedure awaiting,
   * informational mention, negated existence. Mutually exclusive with matched_candidate.
   */
  assertion_warning: string | null;
  /**
   * Assertion override from LEO. "declined", "cancelled", or "refuted" when the
   * patient declined/cancelled or an initial impression was overridden by investigation.
   * "present" in all other cases.
   */
  assertion: string;
}

export const CTX_FLAGS: Array<{ key: string; short: string; label: string; color: string }> = [
  { key: "negated", short: "Neg", label: "Negated", color: "#dc2626" },
  { key: "declined", short: "Dec", label: "Declined", color: "#b91c1c" },
  { key: "uncertain", short: "Unc", label: "Uncertain", color: "#f59e0b" },
  { key: "historical", short: "Hist", label: "Historical", color: "#8b5cf6" },
  { key: "family", short: "Fam", label: "Family history", color: "#06b6d4" },
  { key: "planned", short: "Plan", label: "Planned / awaiting", color: "#6366f1" },
  { key: "hypothetical", short: "Hypo", label: "Hypothetical / conditional", color: "#8b5cf6" },
  { key: "resolved", short: "Res", label: "Resolved", color: "#059669" },
];

/** Decision tier from the safety layer classifier (1 = auto-code, 2 = review, 3 = safety gate). */
export type DecisionTier = 1 | 2 | 3;

/** Tier metadata attached to a CodingReview item. */
export interface TierInfo {
  decision_tier: DecisionTier | null;
  tier_reason: string | null;
  tier_decision: string | null;
}

/** Human-readable labels and colours for each tier. */
export const TIER_META: Record<
  number,
  { label: string; color: "success" | "warning" | "error"; description: string }
> = {
  1: {
    label: "Tier 1",
    color: "success",
    description: "High confidence. The system would auto-code this in autonomous mode.",
  },
  2: {
    label: "Tier 2",
    color: "warning",
    description: "Medium confidence. Needs human check before coding.",
  },
  3: {
    label: "Tier 3",
    color: "error",
    description: "Safety gate. The system blocked this item -- review the reason below.",
  },
};

/** Maps an assertion string to a display chip colour (MUI color prop). */
export const ASSERTION_CHIP: Record<string, { label: string; color: "error" | "warning" | "info" | "default" | "primary" | "success" }> = {
  present:     { label: "Present",            color: "success" },
  absent:      { label: "Negated",            color: "error"   },
  refuted:     { label: "Refuted",            color: "error"   },
  declined:    { label: "Declined",           color: "error"   },
  cancelled:   { label: "Cancelled",          color: "error"   },
  possible:    { label: "Uncertain",          color: "warning" },
  historical:   { label: "Historical",               color: "info"    },
  family:       { label: "Family history",            color: "default" },
  planned:      { label: "Planned / awaiting",        color: "primary" },
  hypothetical: { label: "Hypothetical / conditional", color: "info"    },
};
