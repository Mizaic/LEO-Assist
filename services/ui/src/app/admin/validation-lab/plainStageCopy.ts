/**
 * Plain-English names for pipeline stages.
 * Written for a reading age of 9-11 years.
 */

export interface PlainStageCopy {
  name: string;
  plain: string;
  question: string;
}

const COPY: Record<string, PlainStageCopy> = {
  extract: {
    name: "Reading the letter",
    plain: "LEO reads each part of the letter and picks out the facts.",
    question: "Did LEO find every important fact?",
  },
  "extraction-check": {
    name: "Checking the reading",
    plain: "LEO checks the facts it just picked out.",
    question: "Are all the facts still here after checking?",
  },
  extraction: {
    name: "Reading the letter",
    plain: "LEO reads each part of the letter and picks out the facts.",
    question: "Did LEO find every important fact?",
  },
  post: {
    name: "Cleaning the facts",
    plain: "LEO labels each fact as current, past, family history, or not present. It may also drop facts that are noise. Amber chips below mean the label changed.",
    question: "Are all the facts still here after cleaning?",
  },
  post_process: {
    name: "Cleaning the facts",
    plain: "LEO labels each fact as current, past, family history, or not present. It may also drop facts that are noise. Amber chips below mean the label changed.",
    question: "Are all the facts still here after cleaning?",
  },
  "coding-verify": {
    name: "Checking the codes",
    plain: "LEO checks that each matched code is safe to use.",
    question: "Did all the right codes make it through?",
  },
  coding: {
    name: "Checking the codes",
    plain: "LEO checks that each matched code is safe to use.",
    question: "Did all the right codes make it through?",
  },
  terminology: {
    name: "Adding medical codes",
    plain: "LEO matches each fact to a standard code so rules can use it.",
    question: "Is each fact matched to the right code?",
  },
  snomed_enrichment: {
    name: "Adding body sites from codes",
    plain: "LEO uses the medical code book to add body sites and other links that the code already knows. Dashed chips were added from the code book, not from the letter.",
    question: "Are the added body sites right for this letter?",
  },
  "snomed-enrich": {
    name: "Adding body sites from codes",
    plain: "LEO uses the medical code book to add body sites and other links that the code already knows. Dashed chips were added from the code book, not from the letter.",
    question: "Are the added body sites right for this letter?",
  },
  persist: {
    name: "Saving the facts",
    plain: "LEO writes the facts and codes into the patient record.",
    question: "Did the facts save as you expect?",
  },
  "snomed-relation-judge": {
    name: "Checking links after coding",
    plain: "LEO checks the links again now that each fact has a medical code.",
    question: "Are the links still right after coding?",
  },
  "relation-link": {
    name: "Linking the facts",
    plain: "LEO joins related facts. For example: pain linked to a body site, a finding linked to a condition, or a measurement linked to what it measures.",
    question: "Are the links between facts right?",
  },
  "referral-reason": {
    name: "Reading why they were referred",
    plain: "LEO reads the reason for the referral.",
    question: "Does this match why the letter was sent?",
  },
  compliance: {
    name: "Checking the guideline",
    plain: "LEO checks if the codes trigger a care rule.",
    question: "Did the right rule fire? If not, a code may be missing.",
  },
  completeness: {
    name: "Checking for gaps",
    plain: "LEO checks if the letter is missing something the rule needs.",
    question: "Are the missing items really not in the letter?",
  },
  sbar: {
    name: "Draft assessment",
    plain: "LEO writes a short summary from everything above.",
    question: "Does the summary match what you would say?",
  },
};

function keyFromStepId(stepId: string): string {
  const lower = stepId.toLowerCase();
  const keys = Object.keys(COPY).sort((a, b) => b.length - a.length);
  for (const key of keys) {
    const dash = key.replace(/_/g, "-");
    if (lower.includes(dash) || lower.includes(key)) return key;
  }
  return "";
}

export function plainStageCopy(stepId: string, fallbackName?: string): PlainStageCopy {
  const match = COPY[keyFromStepId(stepId)];
  if (match) return match;
  const name =
    fallbackName ||
    stepId.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    name,
    plain: "This step is part of the run.",
    question: "Does this step look right?",
  };
}
