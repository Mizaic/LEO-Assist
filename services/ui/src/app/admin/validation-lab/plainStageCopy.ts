/**
 * Plain-English names for pipeline stages.
 * Written for a reading age of 9-11 years.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
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
    name: "Checking the facts are complete",
    plain:
      "LEO checks that no facts were lost or changed during the linking step.",
    question: "Are all the facts still here after linking?",
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

/**
 * Explicit step-id-suffix -> copy key map.
 * Ordered most-specific first. Any step_id whose last segment matches a key
 * here is resolved without substring scanning.
 */
const SUFFIX_MAP: Record<string, string> = {
  "extraction-check": "extraction-check",
  "snomed-relation-judge": "snomed-relation-judge",
  "snomed-enrich": "snomed-enrich",
  "snomed-enrichment": "snomed_enrichment",
  snomed_enrichment: "snomed_enrichment",
  "coding-verify": "coding-verify",
  "coding-verifier": "coding-verify",
  coding_verifier: "coding-verify",
  "referral-reason": "referral-reason",
  referral_reason: "referral-reason",
  "relation-link": "relation-link",
  relation_linking: "relation-link",
  "post-process": "post",
  post_processing: "post_process",
  post_process: "post_process",
  extraction: "extraction",
  extract: "extract",
  terminology: "terminology",
  persist: "persist",
  compliance: "compliance",
  completeness: "completeness",
  sbar: "sbar",
};

function keyFromStepId(stepId: string): string {
  const lower = stepId.toLowerCase().replace(/_/g, "-");
  // Try the last hyphen-delimited segment(s) progressively longer
  const parts = lower.split("-");
  for (let start = parts.length - 1; start >= 0; start--) {
    const suffix = parts.slice(start).join("-");
    if (SUFFIX_MAP[suffix]) return SUFFIX_MAP[suffix];
    // Also try underscored variant
    const underscored = parts.slice(start).join("_");
    if (SUFFIX_MAP[underscored]) return SUFFIX_MAP[underscored];
  }
  // Legacy fallback: substring scan (longest key wins)
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
