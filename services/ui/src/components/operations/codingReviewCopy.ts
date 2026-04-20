/**
 * Plain-language copy for the coding-review cases modal.
 *
 * Every string here must pass Flesch-Kincaid Grade <=9.
 * See VT-LEO-AI-118 TC-002.
 *
 * Atlas trace:
 *   DO: DO-1B7E7255
 *   DI: DI-EA432FDA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-1B7E7255")
 */
export const CODING_REVIEW_INTRO = {
  why: "This is the coding review queue. It shows cases the AI was not sure about.",
  how: "Open each card. Read the note. Accept LEO if the match is right. Or search for a better code. Or suppress the case if the record is not about this finding.",
  what: "When you accept a code, it saves to the patient record. If you suppress, LEO will skip this text next time.",
} as const;

/**
 * Glossary term IDs shown inside the modal. Each has a plain-language entry
 * in services/ui/src/lib/glossary.ts and passes FK grade <=9.
 */
export const CODING_REVIEW_GLOSSARY_TERMS = [
  "assertion",
  "semantic-tag",
  "suppress",
  "declined",
  "absent",
  "planned",
  "hypothetical",
] as const;

export const SUPPRESS_HELP = {
  title: "What 'suppress' does",
  body:
    "Suppressing stops LEO from picking this text up next time. Only use this when the finding is not really there. If the patient does have this finding, do not suppress.",
} as const;

export const ASSERTION_HELP = {
  title: "What 'assertion' means",
  body:
    "A short label that tells you how the record treats a thing. 'Present' means it is there. 'Absent' means the record says no. 'Declined' means the patient said no to it. 'Planned' means it is booked for later.",
} as const;

export const SEMANTIC_TAG_HELP = {
  title: "What 'semantic tag' means",
  body:
    "A short label that says what kind of thing a code is. Such as a finding, a test, or a body part. If the tag does not match the text, the code may not be right.",
} as const;
