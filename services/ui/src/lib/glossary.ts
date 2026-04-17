/**
 * Plain-language glossary source of truth.
 *
 * Every clinical term rendered through GlossaryTerm must have an entry
 * here, and every plainLanguage string must pass Flesch-Kincaid Grade
 * <=9 (enforced by VT-LEO-AI-116 TC-006).
 *
 * Seeded with the most common terms on patient-reachable and
 * trainee-reachable surfaces. Further terms are added per screen in
 * later waves (B..F).
 */

export interface GlossaryEntry {
  termId: string;
  label: string;
  clinicalTerm: string;
  plainLanguage: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  haematuria: {
    termId: "haematuria",
    label: "blood in urine",
    clinicalTerm: "haematuria",
    plainLanguage:
      "Blood in the urine. This can look pink, red, or brown. It is always worth telling a doctor.",
  },
  microalbuminuria: {
    termId: "microalbuminuria",
    label: "small amounts of protein in urine",
    clinicalTerm: "microalbuminuria",
    plainLanguage:
      "A small amount of protein is in the urine. This can be an early sign of kidney strain.",
  },
  hba1c: {
    termId: "hba1c",
    label: "long-term blood sugar test",
    clinicalTerm: "HbA1c",
    plainLanguage:
      "A blood test that shows average blood sugar over the last three months.",
  },
  refuted: {
    termId: "refuted",
    label: "diagnosis was overturned",
    clinicalTerm: "refuted assertion",
    plainLanguage:
      "An earlier note said the patient had this, but later tests showed they did not.",
  },
  "safety-netting": {
    termId: "safety-netting",
    label: "what to watch for",
    clinicalTerm: "safety netting",
    plainLanguage:
      "A short list of signs to watch for. If you notice any of them, please contact your GP or NHS 111.",
  },
  assertion: {
    termId: "assertion",
    label: "how the record treats this",
    clinicalTerm: "assertion",
    plainLanguage:
      "A short label that tells you how the record treats a thing. For example, 'planned', 'not present', or 'in the past'.",
  },
  cohort: {
    termId: "cohort",
    label: "a group of patients",
    clinicalTerm: "cohort",
    plainLanguage:
      "A group of patients picked out by shared traits, such as age or a shared test result.",
  },
  audit: {
    termId: "audit",
    label: "a careful check of records",
    clinicalTerm: "clinical audit",
    plainLanguage:
      "A careful check of a set of patient records to see if care matches the plan.",
  },
  "semantic-tag": {
    termId: "semantic-tag",
    label: "kind of thing this code is",
    clinicalTerm: "SNOMED semantic tag",
    plainLanguage:
      "A short label that says what kind of thing a code is. Such as a finding, a test, or a body part.",
  },
  suppress: {
    termId: "suppress",
    label: "stop this being picked up next time",
    clinicalTerm: "suppress rule",
    plainLanguage:
      "Tell LEO to skip this text next time. Only use this when the finding is not really there.",
  },
  declined: {
    termId: "declined",
    label: "offered but the patient said no",
    clinicalTerm: "declined assertion",
    plainLanguage:
      "The care was offered. The patient chose not to have it. We still record that it was offered.",
  },
  absent: {
    termId: "absent",
    label: "the record says no",
    clinicalTerm: "absent assertion",
    plainLanguage:
      "The record says the patient does not have this. For example, 'no chest pain'.",
  },
  planned: {
    termId: "planned",
    label: "booked or set up for later",
    clinicalTerm: "planned assertion",
    plainLanguage:
      "Care that is booked or set up. It has not happened yet.",
  },
  hypothetical: {
    termId: "hypothetical",
    label: "a 'what if'",
    clinicalTerm: "hypothetical assertion",
    plainLanguage:
      "A 'what if' or talk about what might happen. It has not been arranged.",
  },
};

export function lookupTerm(termId: string): GlossaryEntry | undefined {
  return GLOSSARY[termId];
}
