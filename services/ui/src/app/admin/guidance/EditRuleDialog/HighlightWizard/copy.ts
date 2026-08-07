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

/** Shared by every step's `ProblemNodeRow` -- surfaces a tree problem
 *  that has no guideline text of its own to highlight (almost always
 *  an empty group), so "jump to issue" always has a real row to land
 *  on. See treeOps.ts's `findAllValidationErrors`. */
export const PROBLEM_ROW = {
  removeLabel: "Remove it",
  removeAriaLabel: (message: string) => `Remove this problem: ${message}`,
} as const;

/** Step 1 -- "What must ALWAYS be true?" (see the wizard plan's Step
 *  1 wireframe). Fuzzy-matches existing DEMOGRAPHIC/OBSERVATION/
 *  CONCEPT prerequisite leaves onto the guideline text. */
export const STEP_PREREQUISITES = {
  title: "What must always be true?",
  helper:
    "These are things that apply no matter which situation matches -- for example an age that covers every situation. If one situation has its own age or sex, add that when you build that situation.",
  capturedHeading: "Captured so far",
  selectionHint:
    "To select a phrase like 'light chains', click the first word, then hold Shift and click the last word. Or click and drag across the words.",
  question:
    "Does anything else always have to be true, no matter which symptoms the patient has? Most rules don't -- it's fine to say no.",
  questionAriaLabel: "Does anything else always have to be true?",
  noMoreLabel: "No, nothing else",
  highlightMoreLabel: "Highlight more text",
  editLabel: "Edit",
  doneEditingLabel: "Done",
  removeLabel: "Remove",
  /**
   * Optional: link this leaf to words in the quote. Not required --
   * many always-true facts come from a glossary definition or a
   * coded meaning that is not spelled out in the sentence (e.g. NICE
   * "children and young people" -> age 24 or under).
   */
  placeManuallyLabel: "Link to wording",
  /**
   * Neutral note when the leaf has no quote highlight. Deliberately
   * not an error -- missing words in the narrative is common and OK.
   */
  noAnchorHint:
    "Not highlighted in the guideline text. That is fine when this " +
    "comes from a definition or a coded meaning, not from the wording itself.",
  /** Adds a global age/sex check that applies no matter which
   *  situation matches -- distinct from Step 3's per-situation
   *  buttons of the same name, which only ever apply within one
   *  pathway. */
  addAgeLabel: "Add age",
  addSexLabel: "Add sex",
  addAgeAriaLabel: "Add an age check that always applies",
  addSexAriaLabel: "Add a sex check that always applies",
  /** Adds a global lab-value check (e.g. a blood test result) that
   *  applies no matter which situation matches, matching the same
   *  add-age/add-sex pattern above. Unlike age/sex, more than one
   *  can be added, so this button stays visible after the first. */
  addLabValueLabel: "Add lab value",
  addLabValueAriaLabel: "Add a lab value or reading that always applies",
  noTextFallback:
    "This rule has no guideline text to highlight. Skip this step for now, or go back and add what must always be true once the wording is available.",
  /** "Captured so far" row for a CONCEPT leaf built from several
   *  synonym seeds -- shows each finding as its own chip instead of
   *  one packed "one of: a, b, c, ..." sentence, per the wireframe
   *  update after the multi-code review feedback. */
  oneOfPrefix: "Patient has one of:",
  showMoreLabel: (hiddenCount: number) => `+${hiddenCount} more`,
  showLessLabel: "Show fewer",
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
  /** Reopened table-driven / tree-only multi-pathway rules -- the
   *  guideline sentence does not list situations as separate phrases. */
  treeTitle: (count: number) =>
    `This saved rule already has ${count} situations.`,
  treeTag:
    "They come from the rule's saved logic (for example age bands and lab thresholds in a table), not from separate phrases in the guideline sentence. Check each row still looks right, then continue.",
  looksRightLabel: "Looks right, continue",
  mergeLabel: "Merge two rows",
  splitLabel: "Split a row",
  confirmMergeLabel: "Confirm merge",
  cancelLabel: "Cancel",
  splitInstruction:
    "Select the words that belong to the first new situation, then confirm.",
  /** Shown once merge mode is on, above the row list -- merge has no
   *  per-row instruction the way split does (split's prompt lives
   *  inside the one row being split), so it needs its own banner or
   *  the reviewer just sees rows go clickable with no explanation. */
  mergeInstruction: "Tap two rows below to combine them, then confirm.",
  noSplitBody:
    "We couldn't find more than one situation in this text. Shared symptoms belong in Always true. If ages have different lab cut-offs (for example PSA or CA125), build those bands here.",
  noSplitConfirmLabel: "Doesn't split -- one set of rules for everyone",
  ageLabBandsLabel: "Build from age and lab bands",
  ageLabBandsHint:
    "Creates one situation per age range with its own lab threshold. Shared symptoms stay in Always true -- each situation is only age plus the lab value.",
  /** Distinct from `noSplitBody` -- that copy describes what the tool
   *  found on its own and would be a flat contradiction if shown
   *  after the reviewer's OWN merge action collapsed everything down
   *  to one row (see the wizard-in-a-wizard confusion audit). This
   *  pair explains what just happened and offers a way back. */
  mergedToOneTitle: "You've combined every situation into one.",
  mergedToOneBody:
    "It will now apply the same way to everyone. You can undo this if that's not what you meant.",
  undoMergeLabel: "Undo -- keep them as separate situations",
  /** Shown only when the two rows selected for merging are not next
   *  to each other -- merging them would silently swallow whichever
   *  row sits in between. */
  nonAdjacentMergeTitle: "These rows aren't next to each other",
  nonAdjacentMergeBody:
    "Merging them will also pull in the row between them, and its own wording will be lost. Merge anyway?",
  nonAdjacentMergeConfirmLabel: "Merge anyway",
} as const;

/** Warning shown when re-confirming Step 2 with a DIFFERENT number of
 *  situations than before, after the reviewer has already added
 *  conditions to those situations in Step 3 -- changing the count
 *  rebuilds every situation from empty, so anything already added
 *  would otherwise vanish with no explanation. */
export const SPLIT_COUNT_CHANGE_WARNING = {
  title: "This will remove what you've already added",
  body:
    "You already added conditions to the old situations. Changing the number of situations replaces all of them with empty ones -- what you added will be lost.",
  confirmLabel: "Yes, replace them",
  cancelLabel: "Cancel",
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
  /** Heading above the inline editor that opens when the reviewer
   *  re-clicks an already-resolved age/sex row in this list (as
   *  opposed to `PathwayDemographicsPanel`'s own always-visible
   *  "Add age"/"Add sex" affordance for this situation). */
  editingDemographicHeading: "Editing this condition",
  /** Heading above the inline lab-value editor that opens when the
   *  reviewer re-clicks an already-resolved OBSERVATION row. */
  editingObservationHeading: "Editing this lab value",
  /** Trailing "any of the following" cluster prompt -- names the
   *  findings so the reviewer knows which chips the choice covers. */
  clusterPrompt: (terms: string[], suggestedMin = 1) => {
    const quantifier =
      suggestedMin > 1 ? `${suggestedMin} or more of the following` : "any of the following";
    return terms.length > 0
      ? `We noticed "${quantifier}" for ${formatTermList(terms)} --`
      : `We noticed "${quantifier}" under this row --`;
  },
  /** Prompt for a SECOND, marker-less "A or B" cluster found ahead of
   *  the trailing one (e.g. "nausea or vomiting" ahead of "any of the
   *  following: ..."). Asked independently of `clusterPrompt` -- see
   *  `PathwayRows.leadCluster`'s doc comment in wizardMapping.ts. */
  leadClusterPrompt: (terms: string[]) =>
    `We noticed "${terms.join(" or ")}" -- does only one of these need to match, or all of them?`,
  onlyOneLabel: (recommended: boolean) =>
    recommended
      ? "Only one needs to match (Recommended)"
      : "Only one needs to match",
  atLeastNLabel: (n: number, recommended: boolean) =>
    recommended
      ? `At least ${n} need to match (Recommended)`
      : `At least ${n} need to match`,
  allMustMatchLabel: "All must match",
  /** Shown above a required lead finding that sits outside an either/or
   *  group (NG12 1.3.1 E: rectal bleeding before the either-of symptoms). */
  leadRequiredCaption: "Required in this situation.",
  /** Heading above the either/or symptom rows after the lead. */
  eitherOfHeading: "Plus either of these:",
  groupingConfirmedOnlyOne: "Only one of these needs to match.",
  groupingConfirmedOnlyOneWithTerms: (terms: string[]) =>
    terms.length > 0
      ? `Only one of ${formatTermList(terms)} needs to match.`
      : "Only one of these needs to match.",
  groupingConfirmedAtLeastN: (n: number, terms: string[] = []) => {
    if (n <= 1) {
      return terms.length > 0
        ? `Only one of ${formatTermList(terms)} needs to match.`
        : "Only one of these needs to match.";
    }
    return terms.length > 0
      ? `At least ${n} of ${formatTermList(terms)} need to match.`
      : `At least ${n} of these need to match.`;
  },
  groupingConfirmedAll: "All of these must match.",
  groupingConfirmedAllWithTerms: (terms: string[]) =>
    terms.length > 0
      ? `All of ${formatTermList(terms)} must match.`
      : "All of these must match.",
  clusterMinLabel: "How many must match",
  clusterMinOf: (total: number) => `of ${total}`,
  /** Shown under Confirm when a grouping card is still unanswered --
   *  deliberately NOT a repeat of the prompt text above the buttons. */
  groupingChoiceRequired:
    "Choose how many need to match above before you continue.",
  changeLabel: "Change",
  confirmLabel: (letter: string, nextLetter: string | null) =>
    nextLetter
      ? `Confirm situation ${letter}, next -> ${nextLetter}`
      : `Confirm situation ${letter}`,
  unresolvedBlockedReason: (count: number) =>
    count === 1
      ? "One row still needs a match before you can continue."
      : `${count} rows still need a match before you can continue.`,
  /** NG12 1.7.1 weighted checklist companion -- expand score into features. */
  weightedChecklistExpand: (threshold: number) =>
    `Expand weighted checklist (score at least ${threshold})`,
  weightedChecklistExpandHint:
    "Opens the major and minor features from the guideline checklist so you can code them. The rule will treat a score of the threshold or more as true.",
  weightedChecklistInstrumentBlocked:
    "Expand the weighted checklist above before you continue, or code each feature another way.",
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
  /** Heading above `pathwayConfirmedLeaves` -- shown only when there is
   *  no guideline quote to derive rows from (`boundary.source ===
   *  "tree"`), so already-captured conditions are not silently hidden. */
  confirmedConditionsHeading: "Already captured for this situation:",
  /** Adds a blank lab-value check that applies only to THIS situation
   *  -- distinct from Step 1's global button of the same underlying
   *  action. Unlike age/sex, more than one can apply, so this stays
   *  visible after the first is added (mirrors Step 1's own button). */
  addLabValueLabel: "Add lab value",
  addLabValueAriaLabel: "Add a lab value or reading for this situation only",
  removeConditionAriaLabel: (text: string) => `Remove "${text}" from this situation`,
} as const;

/** Orchestrator chrome: a plain, non-numbered breadcrumb of short phase
 *  names, Back, and the Review hand-off once every step is confirmed.
 *  Review itself is confirmation-only -- the right-column live preview
 *  is the summary. The breadcrumb labels are deliberately short and
 *  distinct from each step's own full heading (e.g. StepPrerequisites'
 *  "What must always be true?" title) so the same idea is never stated
 *  twice on screen. */
export const WIZARD_CHROME = {
  breadcrumbLabels: {
    prerequisites: "Always true",
    "pathway-split": "Situations",
    "pathway-conditions": "Conditions",
    review: "Review",
  } as const,
  /** Fallback when step is unknown -- prefer wizardBackLabel(). */
  backLabel: "Previous question",
  backToAlwaysTrue: "Back to always true",
  backToSituations: "Back to situations",
  previousSituation: "Previous situation",
  materializingStatus: "Setting up the situations you confirmed...",
  reviewTitle: "Check the live preview",
  reviewHelper:
    "The right-hand preview shows what this rule means. If something looks wrong, go back to change an earlier answer.",
  reviewBackLabel: "Back to the last situation",
} as const;

/** Hover help for Highlight Wizard controls (T12a). Keep aria-labels. */
export const WIZARD_TOOLTIPS = {
  noMore: "Confirm nothing else always applies, and continue.",
  addAgeAlways: "Add an age check that applies to every situation.",
  addSexAlways: "Add a sex check that applies to every situation.",
  addLabValueAlways: "Add a lab value or reading that applies to every situation.",
  highlightMore: "Select more words from the guideline that must always be true.",
  editCaptured: "Change this captured item.",
  doneEditing: "Finish editing this captured item.",
  placeManually:
    "Optional: highlight the guideline words this item relates to, if any.",
  removePrerequisite: "Remove this always-true condition from the rule.",
  looksRight: "Accept these situations and continue to build conditions.",
  merge: "Combine two neighbouring situations into one.",
  split: "Split one situation into two separate ones.",
  confirmMerge: "Finish combining the selected situations.",
  cancelMergeSplit: "Stop merging or splitting and keep the current rows.",
  noSplit: "Continue with one situation that applies to everyone.",
  undoMerge: "Undo your merge and restore the separate situations.",
  confirmSituation: "Save this situation's conditions and move on.",
  onlyOne: "Any one of these findings is enough for this group.",
  atLeastN:
    "This many findings from the list must be true -- taken from the guideline wording (for example, 2 or more).",
  allMustMatch: "Every finding in this group must be true.",
  changeGrouping: "Change how many findings in this group must match.",
  copyAcross: "Copy medical codes from the earlier matching situation onto this one.",
  dismissCopy: "Skip copying; look up codes for this situation yourself.",
  addAgeSituation: "Add an age check for this situation only.",
  addSexSituation: "Add a sex check for this situation only.",
  addLabValueSituation: "Add a lab value or reading for this situation only.",
  wizardBack:
    "Go back to the previous wizard question (not Who / Suggest / Save).",
  removeProblem: "Remove this broken empty group so the rule can be saved.",
  editConfirmedCondition: "Change this condition.",
  removeConfirmedCondition: "Remove this condition from the situation.",
  multiCodeHighlight: "Select part of this row's text and attach extra medical codes to it.",
  multiCodeClose: "Close the highlight-and-code tool without adding codes.",
  showMoreChips: "Show the rest of the matched codes.",
  showFewerChips: "Hide the extra matched codes.",
} as const;
