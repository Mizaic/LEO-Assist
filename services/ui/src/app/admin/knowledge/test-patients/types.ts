/**
 * Shared types for the Knowledge > Test Patients tab.
 *
 * This is the centralised library that backs every part of the AI:
 * NLP (note reading), Episodes (patient story), Guidelines (rule
 * firing) and Summarisation (SBAR handover). Per DI-7625C251 (Atlas)
 * the page is aspect-aware -- the QA lead picks an aspect and the
 * library only shows fixtures for that aspect.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
export const ASPECT_VALUES = [
  "all",
  "nlp",
  "episodes",
  "guidelines",
  "summarisation",
] as const;

export type AspectFilter = (typeof ASPECT_VALUES)[number];

/**
 * Display copy for each aspect. Plain English so a nurse-grade reader
 * (UK reading age 11) can scan the four count tiles without IT
 * background. Mirrors the audience standard set in
 * .cursor/rules/health-literacy.mdc.
 */
export const ASPECT_LABEL: Record<AspectFilter, string> = {
  all: "All",
  nlp: "Reading notes",
  episodes: "Patient story",
  guidelines: "Rule checks",
  summarisation: "SBAR / referral triage",
};

export const ASPECT_HINT: Record<AspectFilter, string> = {
  all: "Every saved test patient.",
  nlp: "Patients used to check the AI reads notes the right way.",
  episodes: "Patients used to check the AI builds the patient story right.",
  guidelines: "Patients used to check the right rules fire (or do not).",
  summarisation:
    "Patients used to check the AI gives the right triage decision " +
    "(2 week wait, urgent, routine, safety-net, no rule fired) and writes " +
    "a clean SBAR handover. Includes NICE NG12 suspected-cancer pathways.",
};

/**
 * Count tile data shown across the top of the page. Always returns
 * one entry per known aspect plus an "all" total -- the API
 * guarantees zeros are present so the UI does not have to default.
 */
export interface AspectCounts {
  all: number;
  nlp: number;
  episodes: number;
  guidelines: number;
  summarisation: number;
}

/**
 * Triage outcome derived from the ExpectedSBAR node attached to a
 * SBAR / referral-triage test patient. Mirrors the CASE expression
 * in libs/cypher/test_patient_queries.LIST_TEST_PATIENTS exactly.
 *
 * The chip-group filter on the Knowledge tab uses these values so the
 * reviewer can see, at a glance, how many 2 week wait fixtures vs
 * routine vs no-rule-fired vs evaluator-outage cases the library has
 * coverage for. NICE NG12 referrals land under "2ww" or "urgent".
 *
 * "unset" is the catch-all for non-summarisation patients (no
 * ExpectedSBAR node attached) so the chip group never hides rows.
 * "all" is a UI-only sentinel meaning "no triage filter".
 */
export const TRIAGE_OUTCOME_VALUES = [
  "all",
  "2ww",
  "urgent",
  "routine",
  "no_rule_fired",
  "evaluator_outage",
  "unset",
] as const;

export type TriageOutcome = (typeof TRIAGE_OUTCOME_VALUES)[number];

export const TRIAGE_OUTCOME_LABEL: Record<TriageOutcome, string> = {
  all: "All triage outcomes",
  "2ww": "2 week wait (suspected cancer)",
  urgent: "Urgent",
  routine: "Routine",
  no_rule_fired: "No rule fired",
  evaluator_outage: "Evaluator outage",
  unset: "(no SBAR)",
};

export const TRIAGE_OUTCOME_HINT: Record<TriageOutcome, string> = {
  all: "Show every SBAR test patient.",
  "2ww": "NICE NG12 suspected-cancer referrals (refer within 2 weeks).",
  urgent: "Urgent referrals that are not 2 week wait.",
  routine: "Routine referrals or routine review.",
  no_rule_fired:
    "The rule engine fired no rules for this patient -- the SBAR " +
    "should reflect that (no referral, safety-net, watch and wait).",
  evaluator_outage:
    "The terminology / evaluator was unreachable -- the SBAR should " +
    "still be written but flagged as a partial result.",
  unset: "Patients without an ExpectedSBAR (non-summarisation aspects).",
};

export type TriageOutcomeCounts = Record<Exclude<TriageOutcome, "all">, number>;

export interface TestPatientRow {
  id: string;
  name: string;
  description: string;
  aspect: Exclude<AspectFilter, "all">;
  is_test: boolean;
  source_patient_id: string | null;
  codes: string[] | null;
  age: number | null;
  sex: string | null;
  pathway_id: string | null;
  generation_source: string;
  guideline_id: string | null;
  guideline_title: string | null;
  triage_outcome: Exclude<TriageOutcome, "all"> | null;
  created_at: string;
  created_by: string;
  expectations: Array<Record<string, unknown>>;
}

export interface SourcePatientPickerEntry {
  id: string;
  display_name: string;
  encounter_count: number;
}

export interface CloneResult {
  id: string;
  source_patient_id: string;
  aspect: Exclude<AspectFilter, "all">;
  name: string;
  encounters_cloned: number;
  documents_cloned: number;
  concept_rels_cloned: number;
}

/**
 * Editor data model -- mirrors EditorEncounterBody and
 * EditorExpectedSbarBody on the FastAPI router. The Edit drawer
 * reads this shape via GET /full and PATCH'es it back atomically.
 */
export type AssertionValue =
  | "present"
  | "absent"
  | "history_of"
  | "suspected"
  | "uncertain";

export const ASSERTION_VALUES: AssertionValue[] = [
  "present",
  "absent",
  "history_of",
  "suspected",
  "uncertain",
];

export interface EditorCode {
  concept_id: string;
  term: string | null;
  assertion: AssertionValue;
}

export interface EditorEncounter {
  id: string | null;
  source_label: string | null;
  source_id: string | null;
  date: string | null;
  text: string;
  codes: EditorCode[];
}

export interface EditorExpectedSbar {
  id?: string | null;
  fixture_id?: string | null;
  situation_md: string;
  background_md: string;
  recommendation_md: string;
  matched_rule_ids: string[];
  required_phrases: string[];
  banned_phrases: string[];
  expected_action_priority: string | null;
  reviewer_focus: string;
  evaluator_outage?: boolean;
}

export interface FullTestPatient {
  id: string;
  name: string;
  description: string;
  aspect: Exclude<AspectFilter, "all">;
  is_test: boolean;
  source_patient_id: string | null;
  age: number | null;
  sex: string | null;
  pathway_id: string | null;
  generation_source: string | null;
  guideline_id: string | null;
  guideline_title: string | null;
  created_at: string | null;
  updated_at: string | null;
  created_by: string | null;
  updated_by: string | null;
  encounters: EditorEncounter[];
  expected_sbar: EditorExpectedSbar | null;
}

export interface UpdateFullBody {
  aspect: "nlp" | "episodes" | "summarisation";
  name: string;
  description: string;
  age: number | null;
  sex: "male" | "female" | "other" | null;
  encounters: EditorEncounter[];
  expected_sbar: EditorExpectedSbar | null;
}

export interface UpdateFullResult {
  id: string;
  updated: boolean;
  aspect: string;
  encounters_written: number;
  expected_sbar_written: boolean;
}

/**
 * One row in the rule picker. Powers the SBAR editor's Matched rule IDs
 * lookup so the reviewer picks from the rules the live ruleset actually
 * fires, instead of typing rule IDs by hand. Mirrors the shape returned
 * by GET /guidance/test-patients/rules.
 *
 * The reviewer never has to look at `rule_id`: `display_label` is a
 * plain-English string (the verbatim NICE recommendation, the chapter
 * title plus a SNOMED cue, etc.) and is always populated.
 */
export interface GuidanceRulePickerEntry {
  rule_id: string;
  status: string | null;
  name: string | null;
  display_label: string;
  recommendation_text: string | null;
  chapter_title: string | null;
  action_priority: string | null;
  trigger_terms: string[];
  guideline_id: string | null;
  guideline_title: string | null;
}

// ---------------------------------------------------------------------------
// Replay + diagnose + sandbox + bitmap shapes
//
// Used by the rule editor's "Try it on real patients" panel and by the
// shared ReplayResultsDialog / RulesetNotCompiledBanner. Mirrors the
// API shapes in services/api/app/services/test_patient_service.py.
// ---------------------------------------------------------------------------

export interface MatchedRule {
  rule_id: string;
  name?: string;
  recommendation_text?: string;
  guideline_id?: string;
}

export interface ReplayPatientResult {
  patient_id: string;
  patient_name: string;
  passes: Array<{
    rule_id: string;
    fires: boolean;
    expected: boolean;
    /**
     * Set when the saved expectation pinned a pre-edit rule_id that no
     * longer exists in the active ruleset, but a later edit of the same
     * logical rule (same stem) does fire. Lets the UI label "matched as
     * <new id>" instead of misreporting a regression.
     */
    matched_as?: string;
  }>;
  regressions: Array<{
    rule_id: string;
    fires: boolean;
    expected: boolean;
    matched_as?: string;
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
  not_compiled?: boolean;
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
  /**
   * The original rule_id the caller asked about, populated only when
   * the evaluator rebound to a stem-matching descendant (because the
   * literal id has been edited away). Lets the UI explain "this rule
   * was edited; diagnosed against <rule_id>" instead of looking like a
   * silent id swap.
   */
  requested_rule_id?: string;
  rebound_from?: string;
  rebind_reason?: string;
}

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

/**
 * Minimal patient summary the ReplayResultsDialog uses to render the
 * patient header. Source rows from /test-patients are TestPatientRow
 * shape, but the dialog only needs id + name + age + sex + codes +
 * description + pathway. We accept any subset that satisfies these
 * fields so callers can pass either a TestPatientRow or a richer
 * snapshot.
 */
export interface ReplayPatientSummary {
  id: string;
  name: string;
  description?: string;
  codes?: string[] | null;
  age: number | null;
  sex: string | null;
  pathway_id: string | null;
}
