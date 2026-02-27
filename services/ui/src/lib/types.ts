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
  /** DOCUMENTS relationship: extraction confidence (0–1) */
  confidence?: number;
  /** DOCUMENTS relationship: domain (e.g. clinical_finding) */
  domain?: string;
  /** DOCUMENTS relationship: negated, uncertain, historical, etc. */
  context?: Record<string, unknown>;
  /** DOCUMENTS relationship: value, unit, reference_range, interpretation */
  modifiers?: Record<string, unknown>;
  /** DOCUMENTS relationship: when the link was coded */
  coded_at?: string;
}

export interface TermSearchResult {
  snomed_concept_id: string;
  term: string;
  read_code?: string;
  semantic_tag?: string;
  score?: number;
  icd10?: string;
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

export const CTX_FLAGS: Array<{ key: string; short: string; label: string; color: string }> = [
  { key: "negated", short: "Neg", label: "Negated", color: "#dc2626" },
  { key: "uncertain", short: "Unc", label: "Uncertain", color: "#f59e0b" },
  { key: "historical", short: "Hist", label: "Historical", color: "#8b5cf6" },
  { key: "family", short: "Fam", label: "Family history", color: "#06b6d4" },
  { key: "hypothetical", short: "Hyp", label: "Hypothetical", color: "#6366f1" },
  { key: "resolved", short: "Res", label: "Resolved", color: "#059669" },
];
