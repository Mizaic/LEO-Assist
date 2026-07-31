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
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
import type { LogicNodeKind } from "./types";

/** Group-kind dropdown labels. */
export const GROUP_KIND_LABELS: Record<LogicNodeKind, string> = {
  AND: "Patient must have ALL of these",
  OR: "Patient must have ANY of these",
  NOT: "Patient must NOT have any of these",
  AT_LEAST: "Patient must have at least N of these",
  CONCEPT: "Symptom, sign, procedure, or situation",
  DEMOGRAPHIC: "Patient detail",
  OBSERVATION: "Lab value or reading",
  MEDICATION: "Medicine the patient takes",
  ALLERGY: "Allergy the patient has",
  TREATMENT_HISTORY: "Past treatment or procedure",
  RULE_FIRED: "Depends on another rule",
};

/** Short label used inside small chips / badges. */
export const GROUP_KIND_SHORT: Record<LogicNodeKind, string> = {
  AND: "ALL of these",
  OR: "ANY of these",
  NOT: "NONE of these",
  AT_LEAST: "AT LEAST n of",
  CONCEPT: "Symptom",
  DEMOGRAPHIC: "Patient detail",
  OBSERVATION: "Lab value",
  MEDICATION: "Medicine",
  ALLERGY: "Allergy",
  TREATMENT_HISTORY: "Past treatment",
  RULE_FIRED: "Other rule",
};

/**
 * Plain-English labels for the recency window on an OBSERVATION leaf.
 * Keys are ``within_days`` values; values are sentence-case phrases
 * that read naturally in both the editor (&quot;in the last year&quot;) and
 * the sentence renderer (&quot;... in the last year&quot;).
 *
 * Keep the list short: the picker renders it as a dropdown and adding
 * more options than fit on a 600px screen makes the picker feel like
 * a data-entry form. Reviewers who need a non-standard window can
 * type a number directly into the &quot;days&quot; field.
 */
export const RECENCY_LABELS: ReadonlyArray<{
  days: number;
  label: string;
}> = [
  { days: 30, label: "in the last month" },
  { days: 90, label: "in the last 3 months" },
  { days: 180, label: "in the last 6 months" },
  { days: 365, label: "in the last year" },
  { days: 730, label: "in the last 2 years" },
  { days: 1825, label: "in the last 5 years" },
];

/** Human-readable label for a ``within_days`` value; falls back to "in the last N days". */
export function recencyLabel(days: number | undefined): string {
  if (!Number.isFinite(days) || !days || days <= 0) {
    return "in the last year";
  }
  const match = RECENCY_LABELS.find((r) => r.days === days);
  if (match) return match.label;
  return `in the last ${days} days`;
}

/** Plain-English phrase for each OBSERVATION evaluation mode. */
export const OBSERVATION_MODE_LABELS: Record<string, string> = {
  absolute: "One reading",
  temporal: "Several readings in a row",
  reference_range: "Compared to the patient's normal range",
  trend: "Change over time",
  aggregate: "Average or max of recent readings",
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
  { value: "discuss", label: "Discuss with specialist" },
  { value: "safety_net", label: "Watch and check back" },
  { value: "do_not_offer", label: "Do not offer this" },
  { value: "unspecified", label: "Not specified yet" },
];

/**
 * Plain-English label for a rule-level clinical priority. Falls back to
 * "Not set yet" when the rule has no HAS_ACTION edge priority.
 */
export function priorityLabel(
  priority: string | null | undefined,
  dueDays?: number | null,
): string {
  if (!priority) return "Not set yet";
  const base =
    priority === "immediate"
      ? "Immediate specialist assessment"
      : priority === "very_urgent"
        ? "Very urgent (within 48 hours)"
        : priority === "2ww"
          ? "2 week wait (urgent suspected cancer)"
          : priority === "urgent"
            ? "Urgent"
            : priority === "routine"
              ? "Routine"
              : priority;
  if (priority === "routine" || dueDays == null) return base;
  if (priority === "immediate" && dueDays === 0) return base;
  if (priority === "very_urgent" && dueDays === 2) return base;
  return `${base}, within ${dueDays} days`;
}

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

/** Friendly action labels for the "+ add child" bar.
 *
 * `choice` and `subgroup` are Phase 3 additions: the Add-child bar
 * inside a group used to compose its label inline ("Add a choice (any
 * of these)" / "Add a sub-group (all of these)"). Lifting the strings
 * here keeps health-literacy tweaks in one file and lets the new
 * SentenceCanvas reuse the same vocabulary in its empty states.
 */
export const ADD_BAR_LABELS = {
  symptom: "Add a symptom, sign, procedure, or situation",
  group: "Add a sub-group",
  detail: "Add a patient detail",
  choice: "Add a choice (any of these)",
  subgroup: "Add a sub-group (all of these)",
  alternatives: "Add alternatives (any of these)",
  pathway: "Add another pathway",
  observation: "Add a lab value or reading",
};

/**
 * Plain-English label for an AT_LEAST cluster (Phase 3 redesign).
 *
 * Used by both the editable canvas / advanced view and the read-only
 * approval view. The previous all-caps "AT LEAST 2 of 4 of these" is
 * intimidating to non-developer reviewers; sentence-case "Any 2 or
 * more of these" reads as everyday English while still naming the
 * threshold in a way the rule author chose.
 *
 * Returns a cluster header string like:
 *   "Any 2 or more of these"      (min=2)
 *   "Any 1 or more of these"      (min=1)
 */
export function atLeastClusterLabel(min: number): string {
  const safe = Math.max(1, Math.floor(min || 1));
  return `Any ${safe} or more of these`;
}

/**
 * Sentence-canvas card titles (Phase 3).
 *
 * The canvas reads top-down as a series of plain-English statements:
 *   "Patient must be / have ..."
 *   "Patient must match one of these pathways"
 *   "Patient must NOT have ..."
 *
 * These titles are read aloud by screen readers as section headings,
 * so they are full sentences rather than single nouns.
 */
export const CANVAS_CARDS = {
  whoTitle: "Patient must have",
  whoEmpty: "No patient details, symptoms, procedures, or situations set yet.",
  pathwaysTitle: "Patient must match one of these pathways",
  pathwaysEmpty: "Add a pathway to give the patient an alternative way to qualify.",
  noneOfTitle: "Patient must NOT have any of these",
  noneOfEmpty: "Add a symptom, procedure, or situation the patient must not have.",
  unsupportedTitle: "This rule has a complex shape",
  unsupportedBody:
    "We could not show this rule as plain-English sentences. Open the Advanced view (operator tree) to edit it, or simplify the rule.",
} as const;

/**
 * AI-assisted drafting copy (Step 1 AI-draft feature).
 *
 * The AI draft button calls the ai-redraft endpoint and pre-populates
 * the editor with an AI-proposed logic tree. The user's role shifts
 * from builder (needs clinical knowledge) to reviewer (confirms each
 * pathway's plain-English preview sentence).
 */
export const AI_DRAFT = {
  emptyCtaLabel: "Draft from NICE text",
  emptyCtaSubtitle:
    "AI will propose a rule structure. You review each pathway.",
  regenerateLabel: "Regenerate AI draft",
  regenerateAria: "Ask AI to regenerate the rule structure from the NICE text",
  loadingLabel: "Drafting rule...",
  errorLabel: "AI draft failed. Try again.",
  badgeLabel: "AI draft - please check",
  badgeAriaLabel: "This pathway was proposed by AI. Please review it.",
} as const;

/**
 * Copy for the optional plain-English pathway name on group nodes
 * (Phase 2 of the wizard redesign).
 *
 * Each pathway in an OR split becomes its own card with a positional
 * letter (A / B / C). A name lets the rule author label that branch
 * with what it actually means -- e.g. "Possible cancer" or "Symptom
 * watch" -- so the read-only review view does not look like a code
 * matrix.
 *
 * The placeholder reads as a friendly suggestion rather than a
 * required field; an empty name keeps the positional letter.
 */
export const PATHWAY_NAME = {
  inputLabel: "Pathway name",
  inputPlaceholder: "e.g. Possible cancer",
  inputAriaTemplate: (positional: string) =>
    `Name for ${positional}. Optional. Helps reviewers see what this branch means.`,
  hint: "Optional. A short label helps reviewers see what this branch is for.",
  helperMaxChars: 80,
} as const;

/**
 * Step IDs for the three-step rule editor.
 *
 * Kept in display order so a `STEP_ORDER` slice is the canonical
 * "next/prev" lookup.
 *
 * The former "try" (sandbox test) step was removed -- reviewers found
 * the empty-state / duplicate "author a test patient" flow awkward,
 * and the compile-time guideline-wide replay on Bitmap Lifecycle
 * already gives them a safety check before a rule goes live.
 */
export const STEP_IDS = ["who", "suggest", "save"] as const;
export type StepId = (typeof STEP_IDS)[number];

/** Plain-English labels for each step.
 *
 * Reading age 7-11. Numbered titles are added by the rail itself
 * ("1. Who", "2. What", ...).
 */
export const STEP_TITLES: Record<StepId, string> = {
  who: "Who is this rule about?",
  suggest: "What should the system suggest?",
  save: "Save your change",
};

/** Short label used inside the rail chip when space is tight. */
export const STEP_SHORT_TITLES: Record<StepId, string> = {
  who: "Who",
  suggest: "Suggest",
  save: "Save",
};

/** Helper text shown under each step's heading. One short sentence each. */
export const STEP_HELPERS: Record<StepId, string> = {
  who: "Highlight words in the guideline on the right to turn them into conditions, or edit and remove what's already captured on the left.",
  suggest: "Pick what the system should tell the clinician when this rule matches.",
  save: "Tell us why. Save your change, then compile it from Bitmap Lifecycle to make it live.",
};

/** Tone-chip labels for the rail's per-step state. */
export const STEP_STATE_LABELS = {
  not_started: "Not started",
  in_progress: "In progress",
  ready: "Ready",
} as const;

/** Footer label shown at the bottom of the rail when every step is ready. */
export const ALL_READY_LABEL = "All ready to save";

/**
 * Copy for the "saved, not live yet" banner shown on Step 4.
 *
 * Save in the editor only writes a new rule to Neo4j. The live
 * runtime evaluator only picks the change up after the next
 * compile-and-store on Bitmap Lifecycle flips the active version.
 * The banner spells this out so a reviewer never assumes "Save"
 * means "live for real patients".
 */
export const NOT_LIVE_YET_BANNER = {
  title: "Saved, but not live yet",
  body:
    "Save records your change. To make it live for real patients, open Bitmap Lifecycle and compile the ruleset.",
  actionLabel: "Open Bitmap Lifecycle",
} as const;

/**
 * Copy for the Phase 7 confirm dialogs.
 *
 * Two destructive edits are wrapped in a confirm step:
 *
 *   - Changing a root group's kind (AND <-> OR <-> NOT). This flips
 *     the meaning of the whole rule. The dialog shows the before /
 *     after sentence rendered by ``treeToSentence`` so the reviewer
 *     sees the impact in plain English before committing.
 *   - Flipping an OBSERVATION leaf operator across the threshold
 *     direction (e.g. less-than -> greater-than). This typically
 *     inverts clinical meaning of the whole leaf.
 *
 * Both dialogs follow the same shape so screen-reader users hear a
 * consistent pattern.
 */
export const CONFIRM_KIND_CHANGE = {
  title: "Change the meaning of this rule?",
  body:
    "You are about to change a top-level group. This usually changes which patients the rule fires for. Read the before and after below before you commit.",
  beforeLabel: "Now reads as",
  afterLabel: "Will read as",
  confirmLabel: "Yes, change it",
  cancelLabel: "Cancel",
  ariaLabel: "Confirm changing the meaning of this rule",
} as const;

export const CONFIRM_OBSERVATION_FLIP = {
  title: "Flip the lab value direction?",
  body:
    "You are about to switch this lab value from a less-than test to a greater-than test (or the other way round). This usually inverts which patients the rule fires for.",
  beforeLabel: "Now reads as",
  afterLabel: "Will read as",
  confirmLabel: "Yes, flip it",
  cancelLabel: "Cancel",
  ariaLabel: "Confirm flipping the lab value direction",
} as const;

/**
 * Plain-English phrase fragment for an OBSERVATION operator (Phase 7).
 *
 * Used by the operator-flip confirm dialog to render a one-line
 * before / after sentence without dragging in the full
 * ``treeToSentence`` machinery. Mirrors ``OPERATOR_LABELS`` but
 * keyed by the typed ``ObservationOperator`` so the picker stays
 * type-safe.
 */
export const OBSERVATION_OPERATOR_PHRASES: Record<string, string> = {
  ">=": "is at least",
  "<=": "is at most",
  ">": "is more than",
  "<": "is less than",
  "=": "is exactly",
  between: "is between",
};

/**
 * Returns true when an OBSERVATION leaf operator change crosses the
 * threshold direction (e.g. ``<`` -> ``>``). Includes ``=`` and
 * ``between`` flips because they also change the rule semantics
 * meaningfully (presence vs. range vs. cutoff).
 */
export function isObservationOperatorFlip(
  before: string,
  after: string,
): boolean {
  if (before === after) return false;
  const lt = new Set(["<", "<="]);
  const gt = new Set([">", ">="]);
  if (lt.has(before) && gt.has(after)) return true;
  if (gt.has(before) && lt.has(after)) return true;
  // = and between are clinically distinct enough that swapping them
  // for a directional comparator (or vice versa) deserves a confirm.
  if (before === "=" && (lt.has(after) || gt.has(after))) return true;
  if (after === "=" && (lt.has(before) || gt.has(before))) return true;
  if (before === "between" || after === "between") return true;
  return false;
}

/**
 * Returns true when a group-node kind change is destructive enough
 * that the editor SHOULD confirm before applying it. Phase 7 scopes
 * this to root-level changes between AND, OR, NOT, AT_LEAST -- those
 * change the meaning of the whole rule; deeper nodes are usually
 * being authored from scratch and the confirm would be noise.
 */
export function isDestructiveRootKindChange(
  before: LogicNodeKind,
  after: LogicNodeKind,
): boolean {
  if (before === after) return false;
  const groups = new Set<LogicNodeKind>(["AND", "OR", "NOT", "AT_LEAST"]);
  return groups.has(before) && groups.has(after);
}

/**
 * Centralised dialog chrome (Phase 7c).
 *
 * Lifts the previously-inline DialogTitle and a handful of nearby
 * strings out of ``index.tsx`` so QA / health-literacy reviewers can
 * tweak the wording without grepping the React tree.
 */
export const DIALOG_CHROME = {
  title: "Change this rule",
  closeAria: "Close the rule editor",
  /** Footer only -- jumps Who / Suggest / Save, not wizard situations. */
  previousStepLabel: "Previous step",
  nextStepLabel: "Next step",
  previousStepTooltip:
    "Go to the previous editor step (Who, Suggest, or Save).",
  nextStepTooltip:
    "Go to the next editor step (Who, Suggest, or Save). This does not move between situations.",
  previousStepAria: "Go to the previous editor step",
  nextStepAria: "Go to the next editor step",
} as const;

/**
 * Mid-edit Neo4j draft progress (DI-D52E923B / DO-BED08F09).
 * Save progress keeps unfinished work without publishing a new rule.
 */
export const DRAFT_PROGRESS_COPY = {
  saveProgressLabel: "Save progress",
  saveProgressTooltip:
    "Save your work so far. This does not update the live rule. Use Save on the last step when you are finished.",
  saveProgressAria: "Save progress without publishing the rule",
  savingLabel: "Saving progress...",
  savedLabel: "Progress saved",
  resumeAria: "Saved draft available",
  resumeLead: "You have saved progress on this rule.",
  resumeWhenPrefix: "Last saved",
  resumeLabel: "Resume",
  discardLabel: "Discard draft",
  closeConfirmTitle: "Leave without saving progress?",
  closeConfirmBody:
    "Your changes are not saved yet. Save progress to keep them, or leave and lose this work.",
  closeConfirmLeave: "Leave",
  closeConfirmStay: "Stay",
} as const;

/**
 * Centralised duplicate-symptom-set alert copy (Phase 7c).
 *
 * Phase 1 wrote this inline in ``Step1Who``. Lifting it here keeps
 * the editor's reading-age sweep in one file. The function form
 * keeps the count and the example list out of the copy module.
 */
export const DUPLICATE_SETS_ALERT = {
  ariaLabel: "Repeated symptom set warning",
  oneSetLead: "This rule has the",
  oneSetMid: "in two places:",
  oneSetTail:
    "Keeping duplicates is fine, but you can remove one to keep the rule shorter.",
  oneSetStrong: "same symptom set",
  manySetLead: "This rule has",
  manySetTail: "Removing duplicates keeps the rule easier to read.",
  manySetStrong: (count: number) =>
    `${count} repeated symptom sets`,
} as const;

/** Hint when symptoms are OR'd but a patient detail should apply to all of them. */
export const OR_SYMPTOMS_PREREQUISITE_HINT = {
  ariaLabel: "How to add a must-have patient detail",
  lead:
    "These symptoms are grouped as ANY of these (the patient only needs one).",
  action:
    "To also require a patient detail (like sex or age), click",
  actionStrong: "Add patient detail",
  tail:
    "below. We will keep the symptoms as ANY of these and make the patient detail a must-have AND condition -- you do not need to start again.",
} as const;

/**
 * Centralised ConceptSearchPanel headings + helper copy (Phase 7c).
 *
 * Phase 6b kept these inline in the panel; Phase 7 lifts them so
 * the four headings (replace_action, replace, add, idle) live next
 * to all the other reviewer-facing strings.
 */
export const SEARCH_PANEL = {
  headings: {
    replace_action: "Swap the recommended procedure",
    replace: "Swap a symptom, sign, procedure, or situation",
    replace_observation: "Swap the lab value",
    add: "Add a symptom, sign, procedure, or situation",
    idle: "Find a symptom, sign, procedure, or situation",
  },
  searchLabel: "Search clinical terms",
  searchPlaceholder: "Type a word, like cough or weight loss",
  searchAriaLabel: "Search clinical terms",
  resultsAriaLabel: "Search results",
  searchingAriaLabel: "Searching clinical terms",
  noResults: (q: string) =>
    `No clinical terms match "${q}". Try a shorter word or a different spelling.`,
  idleHintLead: "Click a green pill on the left to swap that symptom for a",
  idleHintMid: "different one, or use one of the",
  idleHintStrong: "+ Add a symptom, procedure, or situation",
  idleHintTail: "buttons inside a group.",
  loadError: "Could not search the clinical terms. Please try again.",
  /** Soft nudge only -- a suggested default from how other rules
   *  already coded this phrase, never an auto-applied pick. The
   *  reviewer always has to tap "Use this" themselves. */
  priorResolutionOneHeading: (term: string) =>
    `Other rules use this code for "${term}"`,
  priorResolutionManyHeading: (term: string) =>
    `Other rules use these codes for "${term}"`,
  priorResolutionCount: (count: number) =>
    count === 1 ? "Used once" : `Used ${count} times`,
  askLeoIdeasLabel: "Ask LEO for ideas",
  askLeoIdeasHint:
    "LEO can suggest specific symptoms or findings you can tick and look up.",
} as const;

/**
 * Full-size "Ask LEO for ideas" dialog: tick candidate terms, then
 * review the SNOMED match for each before adding them to the rule.
 */
export const CONCEPT_EXPAND = {
  title: "Ask LEO for ideas",
  tickStageLead: (phrase: string) =>
    `LEO suggested these terms for "${phrase}". Tick the ones that apply.`,
  tickAllLabel: "Tick all",
  continueLabel: "Look up ticked terms",
  cancelLabel: "Cancel",
  backLabel: "Back",
  loadingIdeas: "Asking LEO for ideas...",
  loadingResolve: "Looking up clinical terms...",
  emptyIdeas:
    "LEO did not suggest any terms for this phrase. Try a shorter phrase or search yourself.",
  loadError: "Could not ask LEO for ideas right now. Please try again.",
  resolveStageLead:
    "Check each match. Change a pick if it looks wrong. Terms with no match stay out.",
  unmatchedLabel: "No match found",
  needsPickLabel: "Pick the best match",
  matchedLabel: "Matched",
  addLabel: "Add matched terms",
  addAriaLabel: "Add the matched clinical terms to the rule",
  noMatchedYet: "None of the ticked terms have a clinical-term match yet.",
} as const;

/**
 * MultiConceptPicker: "highlight a word, assign one or more SNOMED codes"
 * (the NER-style pick). Unlike SEARCH_PANEL's one-pick-per-click flow,
 * every result carries a checkbox and, once ticked, an explicit depth
 * field defaulting to 0 (exact match only) -- see multiConceptSeed.ts for
 * why this default deliberately differs from the legacy add flow.
 */
export const MULTI_CONCEPT_PICKER = {
  searchLabel: "Search clinical terms",
  searchPlaceholder: "Type a word, like cough or weight loss",
  resultsAriaLabel: "Search results",
  noResults: (q: string) =>
    `No clinical terms match "${q}". Try a shorter word or a different spelling.`,
  loadError: "Could not search the clinical terms. Please try again.",
  selectAriaLabel: (term: string) => `Select ${term}`,
  depthAriaLabel: (term: string) =>
    `Depth for ${term}: how many levels of more specific terms to include, 0 for exact match only`,
  depthHelp:
    "0 matches this term exactly. Each level up also matches more specific terms underneath it. Hover to see which codes are included.",
  depthPreviewExact: (term: string) =>
    `Only "${term}" will match -- this exact code, nothing more specific.`,
  depthPreviewLoading: "Loading more specific codes...",
  depthPreviewError: "Could not load the codes for this depth. Try again.",
  depthPreviewEmpty: (term: string, depth: number) =>
    `No more specific codes under "${term}" at depth ${depth}.`,
  depthPreviewHeading: (
    term: string,
    depth: number,
    count: number,
    capped: boolean,
  ) =>
    capped
      ? `"${term}" at depth ${depth} also includes ${count}+ more specific codes (scroll to see them):`
      : `"${term}" at depth ${depth} also includes ${count} more specific code${count === 1 ? "" : "s"}:`,
  depthPreviewApiCap:
    "Showing the first 200 codes from the terminology service. Raise depth carefully if you need a narrower set.",
  confirmLabel: (n: number) => (n === 1 ? "Add 1 code" : `Add ${n} codes`),
  emptyHint:
    "Tick one or more results below, then confirm. Each one can match exactly, or match more specific terms too.",
} as const;

