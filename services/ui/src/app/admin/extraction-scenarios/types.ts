/**
 * Types for the Extraction Scenarios admin surface.
 *
 * Atlas trace:
 *   DI: DI-1B3B5375, DI-B492CAFD
 *   DO: DO-416BA91D
 *   Risk: R-80E8BD96
 *   VAL-87173594  phrase-level F1 validation
 */

export type ReviewStatus = "draft_for_clinician_approval" | "approved";

export interface ExpectedPhrase {
  text: string;
  semantic_tag: string;
  value?: string;
  unit?: string;
  concept_id?: string;
  preferred_term?: string;
}

export interface ObservableValue {
  value?: string;
  unit?: string;
}

/** Placeholder for roaring-bitmap / guideline analysis expectations. */
export interface ExpectedAnalysis {
  matched_rule_ids: string[];
  expect_no_rules_fired: boolean;
  expected_action_priority: string | null;
  reviewer_notes: string;
}

/** Placeholder for expected SBAR transcript expectations. */
export interface ExpectedSbar {
  situation_md: string;
  background_md: string;
  recommendation_md: string;
  matched_rule_ids: string[];
  required_phrases: string[];
  banned_phrases: string[];
  expected_action_priority: string | null;
  reviewer_focus: string;
}

export interface ExtractionScenarioRow {
  case_id: string;
  site: string;
  format: string;
  phrase_classes: string[];
  difficulty: string[];
  review_status: ReviewStatus;
  expected_strings: Array<string | ExpectedPhrase>;
  must_not_extract: string[];
  notes_for_clinician_review: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  schema_version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExtractionScenarioDetail extends ExtractionScenarioRow {
  markdown_body: string;
  source_template_markdown: string | null;
  synthetic_patient: Record<string, unknown> | null;
  expected_observables?: Array<{
    text: string;
    value?: string;
    unit?: string;
    flag?: string;
  }> | null;
  blood_results:
    | {
        results?: Array<{
          test_name: string;
          display_name?: string;
          value?: number | string;
          unit?: string;
          flag?: string;
        }>;
      }
    | unknown[]
    | null;
  expected_analysis?: ExpectedAnalysis | null;
  expected_sbar?: ExpectedSbar | null;
}

export interface ScenarioListResponse {
  total: number;
  approved: number;
  draft: number;
  pass_threshold: number;
  cases: ExtractionScenarioRow[];
}

export interface CaseScore {
  case_id: string;
  f1: number;
  precision: number;
  recall: number;
  true_positive: number;
  false_positive: number;
  false_negative: number;
  missed_strings: string[];
  extra_strings: string[];
  observable_recall?: number;
  stage_snapshots?: Record<string, { entity_count: number; terms: string[] }>;
}

export interface ValidationRunStatus {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  triggered_by: string;
  triggered_at: string;
  pass_threshold: number;
  overall_f1?: number;
  overall_precision?: number;
  overall_recall?: number;
  passed?: boolean;
  per_case_results?: CaseScore[];
  completed_at?: string;
  error?: string;
  atlas_vt_recorded?: boolean;
  atlas_val_recorded?: boolean;
}

export type StatusFilter = "all" | "approved" | "draft";

export interface ScenarioWritePayload {
  case_id?: string;
  site: string;
  format: string;
  markdown_body: string;
  expected_strings: ExpectedPhrase[];
  must_not_extract: string[];
  phrase_classes: string[];
  difficulty: string[];
  notes_for_clinician_review?: string | null;
  expected_observables?: ExtractionScenarioDetail["expected_observables"];
  expected_analysis?: ExtractionScenarioDetail["expected_analysis"];
  expected_sbar?: ExtractionScenarioDetail["expected_sbar"];
  synthetic_patient?: ExtractionScenarioDetail["synthetic_patient"];
  blood_results?: ExtractionScenarioDetail["blood_results"];
  source_template_markdown?: string | null;
  schema_version?: number;
}
