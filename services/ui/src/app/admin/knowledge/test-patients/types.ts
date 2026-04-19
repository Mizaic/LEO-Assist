/**
 * Shared types for the Knowledge > Test Patients tab.
 *
 * This is the centralised library that backs every part of the AI:
 * NLP (note reading), Episodes (patient story), Guidelines (rule
 * firing) and Summarisation (SBAR handover). Per DI-7625C251 (Atlas)
 * the page is aspect-aware -- the QA lead picks an aspect and the
 * library only shows fixtures for that aspect.
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
  summarisation: "SBAR handover",
};

export const ASPECT_HINT: Record<AspectFilter, string> = {
  all: "Every saved test patient.",
  nlp: "Patients used to check the AI reads notes the right way.",
  episodes: "Patients used to check the AI builds the patient story right.",
  guidelines: "Patients used to check the right rules fire (or do not).",
  summarisation: "Patients used to check the SBAR handover comes out right.",
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
