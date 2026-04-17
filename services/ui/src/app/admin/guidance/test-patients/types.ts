/**
 * Shared types for the test-patient library UI.  Mirrors the API
 * shapes in services/api/app/services/test_patient_service.py and
 * services/api/app/routers/test_patients.py.
 */

export type Sex = "male" | "female" | "other";

export interface PatientPayload {
  codes: string[];
  age: number | null;
  sex: Sex | null;
  pathway_id: string | null;
  name: string;
  description: string;
  generation_source?: string;
}

export interface ExpectationInput {
  rule_id: string;
  fires: boolean;
  matched_branch_node_ids: string[];
}

export interface SavedExpectation {
  rule_id: string;
  fires: boolean;
  matched_branch_node_ids: string[] | null;
  snapshot_at: string;
  ruleset_version: string | null;
}

export interface TestPatient {
  id: string;
  name: string;
  description: string;
  codes: string[];
  age: number | null;
  sex: Sex | null;
  pathway_id: string | null;
  scope_type: string;
  scope_id: string;
  generation_source: string;
  content_hash: string;
  guideline_id: string;
  guideline_title: string;
  created_at: string;
  created_by: string;
  expectations: SavedExpectation[];
}

export interface MatchedRule {
  rule_id: string;
  name?: string;
  recommendation_text?: string;
  guideline_id?: string;
}

export interface DryRunResponse {
  matched_rules: MatchedRule[];
  branch_paths: Record<string, string[]>;
  ruleset_version: string | null;
}

export interface ProposalRow {
  patient: PatientPayload;
  rule_id: string;
  rule_name: string;
  guideline_id: string;
  kind: "happy" | "fail" | "branch" | "boundary";
  rationale: string;
  content_hash: string;
}

export interface GenerateResponse {
  proposals: ProposalRow[];
  scope_type: string;
  depth: string;
  rules_considered: number;
}

export interface ReplayPatientResult {
  patient_id: string;
  patient_name: string;
  passes: Array<{ rule_id: string; fires: boolean; expected: boolean }>;
  regressions: Array<{
    rule_id: string;
    fires: boolean;
    expected: boolean;
    /**
     * Pre-baked diagnostic from the backend, populated by
     * sandbox_replay so the dialog does not need to call /diagnose
     * after the sandbox bitmap has been torn down.  Optional because
     * live (non-sandbox) replays still defer to a per-row /diagnose
     * call against the production scope.
     */
    diagnostic?: DiagnoseResponse | null;
  }>;
  unexpected_matches: MatchedRule[];
  total_assertions: number;
  error?: string;
}

export interface ReplayReport {
  id?: string;
  ruleset_version: string | null;
  scope_type: string;
  scope_id: string;
  guideline_id: string | null;
  patient_count: number;
  regressions_count: number;
  passes_count: number;
  drift_count: number;
  results: ReplayPatientResult[];
}

/**
 * Diagnose response -- per-node match annotations from the bitmap
 * evaluator.  The annotated tree mirrors the rule's compiled
 * ``logic_tree`` so the UI can render it hierarchically (preserving
 * AND / OR / NOT / AT_LEAST grouping).
 */

export type DiagnoseNodeKind =
  | "CONCEPT"
  | "DEMOGRAPHIC"
  | "AND"
  | "OR"
  | "NOT"
  | "AT_LEAST"
  | "CONCEPT_GROUP";

export interface DiagnoseConceptCriterion {
  term?: string;
  snomed_concept_id?: string;
  preferred_term?: string;
  semantic_tag?: string;
}

export interface DiagnoseNode {
  kind: DiagnoseNodeKind;
  node_id: string | null;
  matched: boolean;
  match_count?: number;
  matched_count?: number;
  total_count?: number;
  min?: number;
  missing_bitmap?: boolean;
  criterion?: DiagnoseConceptCriterion;
  field?: string;
  operator?: string;
  value?: number | string | null;
  unit?: string | null;
  mode?: string;
  children?: DiagnoseNode[];
}

export interface DiagnoseResponse {
  rule_id: string;
  rule_name?: string | null;
  guideline_id?: string | null;
  schema_version?: number;
  fires: boolean;
  annotated_tree: DiagnoseNode | null;
  /**
   * True when the terminology API has no active ruleset compiled for the
   * requested scope.  When set, the UI should render a "Compile production
   * ruleset" banner instead of treating the rule as silently passing.
   */
  not_compiled?: boolean;
  /**
   * False when the rule_id is missing from the active ruleset (it was
   * never compiled, or has been removed).  Distinct from ``not_compiled``
   * which says nothing was compiled at all.
   */
  rule_found?: boolean;
  message?: string;
  recompile_hint?: string | null;
  scope_type?: string;
  scope_id?: string;
  patient?: {
    codes_provided: number;
    codes_resolved: number;
    age: number | null;
    sex: string | null;
  };
  active_version: string | null;
}

/**
 * Sandbox replay -- compile draft rules + replay saved patients in one
 * shot.  Used by the rule editor's "Test against library" flow.
 */

export interface SandboxCompileSummary {
  version: string;
  rule_count: number;
  draft_input_count: number;
  compile_timestamp: string;
  scope_type: string;
  scope_id: string;
  policy_mode: string;
  draft: boolean;
  compile_stats?: Record<string, number>;
}

export interface SandboxReplayResponse {
  sandbox_id: string;
  compile: SandboxCompileSummary;
  report: ReplayReport;
}

/**
 * Live status of the production bitmap, surfaced via
 * ``GET /api/terminology/guidelines/bitmap/status``.  Used by the
 * "no ruleset compiled" banner so the user can compile in one click
 * instead of digging into the bitmap lifecycle panel.
 */
export interface BitmapStatus {
  active_version: string | null;
  rule_count: number;
  compile_timestamp: string | null;
  scope_type: string;
  scope_id: string;
  policy_mode?: string | null;
  message?: string;
  compile_stats?: Record<string, number>;
}

export interface GuidelinePickerEntry {
  id: string;
  title: string;
  active_rule_count: number;
}
