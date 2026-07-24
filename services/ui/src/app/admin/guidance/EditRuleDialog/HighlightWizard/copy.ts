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

/** Step 1 -- "What must ALWAYS be true?" (see the wizard plan's Step
 *  1 wireframe). Fuzzy-matches existing DEMOGRAPHIC/OBSERVATION/
 *  CONCEPT prerequisite leaves onto the guideline text. */
export const STEP_PREREQUISITES = {
  title: "What must always be true?",
  helper:
    "These are things that apply no matter which symptoms the patient has.",
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
    "This rule has no guideline text to highlight. Skip this step, or use the Advanced view to add anything that should always be true.",
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
  clusterPrompt: "We noticed \"any of the following\" under this row --",
  /** Prompt for a SECOND, marker-less "A or B" cluster found ahead of
   *  the trailing one (e.g. "nausea or vomiting" ahead of "any of the
   *  following: ..."). Asked independently of `clusterPrompt` -- see
   *  `PathwayRows.leadCluster`'s doc comment in wizardMapping.ts. */
  leadClusterPrompt: (terms: string[]) =>
    `We noticed "${terms.join(" or ")}" above -- does only one of these need to match, or all of them?`,
  onlyOneLabel: "Only one needs to match (Recommended)",
  allMustMatchLabel: "All must match",
  groupingConfirmedOnlyOne: "Only one of these needs to match.",
  groupingConfirmedAll: "All of these must match.",
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
} as const;

/** Orchestrator chrome: the "Step X of Y" progress header, Back /
 *  Skip-to-Advanced navigation, and the Review hand-off screen once
 *  every step is confirmed. */
export const WIZARD_CHROME = {
  stepLabel: (index: number, total: number) => `Step ${index} of ${total}`,
  stepNames: {
    prerequisites: "What must always be true",
    "pathway-split": "Does this split into situations",
    "pathway-conditions": "Build each situation",
    review: "Review",
  } as const,
  backLabel: "Back",
  skipToAdvancedLabel: "Skip to Advanced view",
  materializingStatus: "Setting up the situations you confirmed...",
  reviewTitle: "Here's the rule you built",
  reviewHelper:
    "Check it reads the way you'd expect. You can still edit anything below, or go back to change an earlier answer.",
  reviewBackLabel: "Back to the last situation",
} as const;
