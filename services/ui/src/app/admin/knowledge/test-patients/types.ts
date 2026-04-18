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
