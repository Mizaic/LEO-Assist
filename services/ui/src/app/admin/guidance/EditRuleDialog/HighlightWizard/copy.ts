/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Plain-English copy for the highlight-to-build rule wizard.
 *
 * Kept in its own file rather than added to the parent
 * `EditRuleDialog/copy.ts` -- that file is already close to this
 * repo's 500 LOC file-length hard limit, and this wizard is its own
 * domain concept (a guided, one-question-at-a-time flow anchored to
 * the live guideline sentence), matching the same "one file per
 * responsibility" convention `copy.ts` itself follows.
 *
 * Per `.cursor/rules/health-literacy.mdc`: short sentences, everyday
 * words, active voice, explain before you name.
 */

/** "nausea, vomiting, and weight loss" -- short list for prompts. */
function formatTermList(terms: string[]): string {
  if (terms.length === 0) return "";
  if (terms.length === 1) return terms[0];
  if (terms.length === 2) return `${terms[0]} and ${terms[1]}`;
  return `${terms.slice(0, -1).join(", ")}, and ${terms[terms.length - 1]}`;
}

/** Step 1 -- "What must ALWAYS be true?" (see the wizard plan's Step
 *  1 wireframe). Fuzzy-matches existing DEMOGRAPHIC/OBSERVATION/
 *  CONCEPT prerequisite leaves onto the guideline text. */
export const STEP_PREREQUISITES = {
  title: "What must always be true?",
  helper:
    "These are things that apply no matter which situation matches -- for example an age that covers every situation. If one situation has its own age or sex, add that when you build that situation.",
  capturedHeading: "Captured so far",
  question:
    "Does anything else always have to be true, no matter which symptoms the patient has? Most rules don't -- it's fine to say no.",
  questionAriaLabel: "Does anything else always have to be true?",
  noMoreLabel: "No, nothing else",
  highlightMoreLabel: "Highlight more text",
  editLabel: "Edit",
  removeLabel: "Remove",
  placeManuallyLabel: "Tap to place it manually",
  noAnchorHint: "Could not find matching words for this in the sentence.",
  noTextFallback:
    "This rule has no guideline text to highlight. Skip this step for now, or go back and add what must always be true once the wording is available.",
} as const;

/** Step 2 -- "Does this split into different situations?" (see the
 *  wizard plan's Step 2 wireframe). Prefers the guideline's own list
 *  structure (`recommendation_structure`) over the `", or "`-splitting
 *  text heuristic -- the two are never shown with equal confidence. */
export const STEP_PATHWAY_SPLIT = {
  structureTitle: (count: number) =>
    `The guideline lists ${count} situations. Here they are.`,
  structureTag: "Found from the guideline's own list formatting.",
  heuristicTitle:
    "Does this apply the same way to everyone, or does it depend which symptoms the patient has?",
  heuristicTag: (count: number) =>
    `We think we found ${count} possible situations. Please check them.`,
  looksRightLabel: "Looks right, continue",
  mergeLabel: "Merge two rows",
  splitLabel: "Split a row",
  confirmMergeLabel: "Confirm merge",
  cancelLabel: "Cancel",
  splitInstruction:
    "Select the words that belong to the first new situation, then confirm.",
  noSplitBody: "We couldn't find more than one situation in this text.",
  noSplitConfirmLabel: "Doesn't split -- one set of rules for everyone",
} as const;

/** Step 3 -- one pathway at a time, repeated with a "Situation B (2 of
 *  6)" progress indicator (see the wizard plan's Step 3 wireframe).
 *  Every row -- the lead condition and each "any of the following"
 *  item -- resolves through the existing concept-search / observation
 *  / demographic flows, pre-filled instead of typed from scratch. */
export const STEP_PATHWAY_CONDITIONS = {
  situationProgress: (letter: string, index: number, count: number) =>
    `Situation ${letter} (${index} of ${count})`,
  helper: "Within this situation, what must ALL be true?",
  confirmedHeading: "Already confirmed:",
  /** Trailing "any of the following" cluster prompt -- names the
   *  findings so the reviewer knows which chips the choice covers. */
  clusterPrompt: (terms: string[]) =>
    terms.length > 0
      ? `We noticed "any of the following" for ${formatTermList(terms)} --`
      : 'We noticed "any of the following" under this row --',
  /** Prompt for a SECOND, marker-less "A or B" cluster found ahead of
   *  the trailing one (e.g. "nausea or vomiting" ahead of "any of the
   *  following: ..."). Asked independently of `clusterPrompt` -- see
   *  `PathwayRows.leadCluster`'s doc comment in wizardMapping.ts. */
  leadClusterPrompt: (terms: string[]) =>
    `We noticed "${terms.join(" or ")}" -- does only one of these need to match, or all of them?`,
  onlyOneLabel: "Only one needs to match (Recommended)",
  allMustMatchLabel: "All must match",
  groupingConfirmedOnlyOne: "Only one of these needs to match.",
  groupingConfirmedAll: "All of these must match.",
  /** Shown under Confirm when a grouping card is still unanswered --
   *  deliberately NOT a repeat of the prompt text above the buttons. */
  groupingChoiceRequired:
    "Choose only-one or all-must-match above before you continue.",
  changeLabel: "Change",
  confirmLabel: (letter: string, nextLetter: string | null) =>
    nextLetter
      ? `Confirm situation ${letter}, next -> ${nextLetter}`
      : `Confirm situation ${letter}`,
  unresolvedBlockedReason: (count: number) =>
    count === 1
      ? "One row still needs a match before you can continue."
      : `${count} rows still need a match before you can continue.`,
  /**
   * One-time offer to copy an earlier, already-confirmed pathway's
   * SNOMED codes onto this pathway's matching rows, shown only when
   * both pathways ask about the exact same findings (see
   * `pathwayCopyAcross.ts`). This is a copy, not a live link -- the
   * two pathways can be edited independently afterwards.
   */
  copyAcrossOffer: (sourceLetter: string, count: number) =>
    `Situation ${sourceLetter} asked about the same ${count} finding${
      count === 1 ? "" : "s"
    }. Copy your codes across so you don't have to look them up again?`,
  copyAcrossAcceptLabel: "Copy them across",
  copyAcrossDismissLabel: "No, I'll do this one myself",
  copyAcrossAriaLabel: "Copy codes from an earlier matching situation",
  /** Age/sex that apply to THIS situation only (not Step 1 globals). */
  demographicsHeading: "Does this situation only apply to some ages or sexes?",
  demographicsHelper:
    "Only add these if this situation is different from the others. Things that apply to every situation belong in step 1.",
  addAgeLabel: "Add age",
  addSexLabel: "Add sex",
  addAgeAriaLabel: "Add an age check for this situation only",
  addSexAriaLabel: "Add a sex check for this situation only",
} as const;

/** Orchestrator chrome: the "Step X of Y" progress header, Back, and
 *  the Review hand-off once every step is confirmed. Review itself is
 *  confirmation-only -- the right-column live preview is the summary. */
export const WIZARD_CHROME = {
  stepLabel: (index: number, total: number) => `Step ${index} of ${total}`,
  stepNames: {
    prerequisites: "What must always be true",
    "pathway-split": "Does this split into situations",
    "pathway-conditions": "Build each situation",
    review: "Review",
  } as const,
  backLabel: "Back",
  materializingStatus: "Setting up the situations you confirmed...",
  reviewTitle: "Check the live preview",
  reviewHelper:
    "The right-hand preview shows what this rule means. If something looks wrong, go back to change an earlier answer.",
  reviewBackLabel: "Back to the last situation",
} as const;
