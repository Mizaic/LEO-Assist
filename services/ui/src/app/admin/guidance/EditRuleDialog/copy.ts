/**
 * Plain-English copy and tiny formatting helpers for the EditRuleDialog.
 *
 * Centralised so a clinician with average reading age (UK 9-11) can use the
 * editor without parsing technical SNOMED / boolean-logic vocabulary, and so
 * QA can update wording in one place rather than chasing 4-5 components.
 *
 * Per `.cursor/rules/health-literacy.mdc`:
 *   - short sentences, one idea per sentence
 *   - everyday words instead of clinical jargon
 *   - active voice
 *   - explain before you name
 */

import type { LogicNodeKind } from "./types";

/** Group-kind dropdown labels. */
export const GROUP_KIND_LABELS: Record<LogicNodeKind, string> = {
  AND: "Patient must have ALL of these",
  OR: "Patient must have ANY of these",
  NOT: "Patient must NOT have any of these",
  AT_LEAST: "Patient must have at least N of these",
  CONCEPT: "Symptom or sign",
  DEMOGRAPHIC: "Patient detail",
};

/** Short label used inside small chips / badges. */
export const GROUP_KIND_SHORT: Record<LogicNodeKind, string> = {
  AND: "ALL of these",
  OR: "ANY of these",
  NOT: "NONE of these",
  AT_LEAST: "AT LEAST n of",
  CONCEPT: "Symptom",
  DEMOGRAPHIC: "Patient detail",
};

/** Plain-English label for each demographic field. */
export const DEMOGRAPHIC_FIELD_LABELS: Record<string, string> = {
  age: "Patient's age",
  sex: "Patient's sex",
};

/** Plain-English label for each comparison operator. */
export const OPERATOR_LABELS: Record<string, string> = {
  ">=": "is at least",
  "<=": "is at most",
  ">": "is more than",
  "<": "is less than",
  "=": "is exactly",
  between: "is between",
};

/** Plain-English label for the recommendation strength. */
export const STRENGTH_LABELS: Array<{ value: string; label: string }> = [
  { value: "offer", label: "Offer this test or referral" },
  { value: "consider", label: "Think about this test or referral" },
  { value: "refer", label: "Refer urgently" },
  { value: "safety_net", label: "Watch and check back" },
  { value: "do_not_offer", label: "Do not offer this" },
  { value: "unspecified", label: "Not specified yet" },
];

/**
 * Strip the SNOMED semantic tag (e.g. "(finding)", "(disorder)", "(situation)")
 * from a preferred term so the chip reads in everyday English.
 *
 *   "Cough (finding)"               -> "Cough"
 *   "Acute appendicitis (disorder)" -> "Acute appendicitis"
 *   "History of asbestos exposure"  -> "History of asbestos exposure"
 */
export function friendlyTerm(raw: string | undefined | null): string {
  if (!raw) return "";
  const trimmed = raw.trim();
  return trimmed.replace(/\s*\(([a-z][a-z /-]*?)\)\s*$/i, "").trim() || trimmed;
}

/** Friendly action labels for the "+ add child" bar. */
export const ADD_BAR_LABELS = {
  symptom: "Add a symptom or sign",
  group: "Add a sub-group",
  detail: "Add a patient detail",
};
