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
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
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
  OBSERVATION: "Lab value or reading",
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

/** Friendly action labels for the "+ add child" bar.
 *
 * `choice` and `subgroup` are Phase 3 additions: the Add-child bar
 * inside a group used to compose its label inline ("Add a choice (any
 * of these)" / "Add a sub-group (all of these)"). Lifting the strings
 * here keeps health-literacy tweaks in one file and lets the new
 * SentenceCanvas reuse the same vocabulary in its empty states.
 */
export const ADD_BAR_LABELS = {
  symptom: "Add a symptom or sign",
  group: "Add a sub-group",
  detail: "Add a patient detail",
  choice: "Add a choice (any of these)",
  subgroup: "Add a sub-group (all of these)",
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
  whoEmpty: "No patient details or symptoms set yet.",
  pathwaysTitle: "Patient must match one of these pathways",
  pathwaysEmpty: "Add a pathway to give the patient an alternative way to qualify.",
  noneOfTitle: "Patient must NOT have any of these",
  noneOfEmpty: "Add a symptom the patient must not have.",
  unsupportedTitle: "This rule has a complex shape",
  unsupportedBody:
    "We could not show this rule as plain-English sentences. Open the Advanced view (operator tree) to edit it, or simplify the rule.",
  advancedAccordionTitle: "Advanced view (operator tree)",
  advancedAccordionHint:
    "Open this if you need fine-grained control over AND, OR, NOT, or AT LEAST groups. The plain-English canvas above stays in sync.",
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
 * Step IDs for the four-step rule editor.
 *
 * Kept in display order so a `STEP_ORDER` slice is the canonical
 * "next/prev" lookup.
 */
export const STEP_IDS = ["who", "suggest", "try", "save"] as const;
export type StepId = (typeof STEP_IDS)[number];

/** Plain-English labels for each step.
 *
 * Reading age 7-11. Numbered titles are added by the rail itself
 * ("1. Who", "2. What", ...).
 */
export const STEP_TITLES: Record<StepId, string> = {
  who: "Who is this rule about?",
  suggest: "What should the system suggest?",
  try: "Test your change safely",
  save: "Save your change",
};

/** Short label used inside the rail chip when space is tight. */
export const STEP_SHORT_TITLES: Record<StepId, string> = {
  who: "Who",
  suggest: "Suggest",
  try: "Test",
  save: "Save",
};

/** Helper text shown under each step's heading. One short sentence each. */
export const STEP_HELPERS: Record<StepId, string> = {
  who: "Pick which patients this rule is about. Click a green pill to swap or change it. Use + Add to add another.",
  suggest: "Pick what the system should tell the clinician when this rule matches.",
  try: "Run your change against saved test patients in a sandbox. Production is never touched.",
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
 * Copy for the sandbox-only Test Patients panel (Phase 1 redesign).
 *
 * Production is NEVER touched from inside the editor. A draft rule
 * has not been compiled into the live Redis bitmap yet, so testing
 * against the live ruleset would test the OLD rule -- which is
 * misleading and unsafe. The wizard therefore offers exactly one
 * test surface: the throwaway sandbox.
 */
export const SANDBOX_PANEL = {
  heading: "Try it in a sandbox",
  intro:
    "Compile your unsaved change into a throwaway bitmap and replay the saved test patients through it. Production is never touched.",
  draftCardTitle: "Test your unsaved change",
  draftCardCaption:
    "We compile the rule you are editing right now into a throwaway bitmap, run the saved patients against it, and discard the sandbox. The live rule is not changed.",
  testButton: "Run sandbox test",
  testButtonRunning: "Running sandbox test...",
  noPatientsTitle: "No saved test patients yet",
  noPatientsBody:
    "Add a test patient that exercises this rule before you save the change. You can author one with AI from this rule, or open the central library to pick from existing patients.",
  ruleNotSavedTitle: "Save the rule once before testing",
  ruleNotSavedBody:
    "We need a saved rule to attach test patients to. Save once on Step 4, then come back here to run a sandbox test before compiling.",
  noDraftYetTitle: "Make a change to test",
  noDraftYetBody:
    "Edit the rule on Step 1 first. The sandbox tests the unsaved draft against the saved test patients.",
} as const;

/**
 * Copy for the per-card sandbox impact badges (Phase 4).
 *
 * After a sandbox replay, each top-level sentence card on the canvas
 * shows a tiny badge summarising how many of the saved test patients
 * the rule fires for. The reviewer sees the impact next to the
 * sentences themselves, instead of having to scroll to the test
 * panel. The summary is whole-rule, not per-card -- a sandbox replay
 * answers "does the rule fire for this patient?", not "which sub-tree
 * matched". The badge is therefore mirrored on every card so the
 * answer is always visible above the fold.
 */
export const SANDBOX_BADGE = {
  /** Pill text when a fresh report is available. */
  freshLabel: (firing: number, total: number) =>
    total === 0
      ? "No saved test patients"
      : firing === total
        ? `Fires for all ${total} test patient${total === 1 ? "" : "s"}`
        : firing === 0
          ? `Fires for 0 of ${total} test patient${total === 1 ? "" : "s"}`
          : `Fires for ${firing} of ${total} test patient${total === 1 ? "" : "s"}`,
  staleLabel: "Sandbox out of date - run again",
  runningLabel: "Running sandbox test...",
  emptyLabel: "Run a sandbox test to see impact",
  ariaLabel: "Sandbox replay impact for this rule",
} as const;

/**
 * Copy for the auto-run + Run now controls on the sandbox panel
 * (Phase 4 -- debounced on-commit replay).
 *
 * The previous Phase-1 design replaced an unsafe live-replay loop
 * with manual sandbox runs only. Reviewers asked for fast feedback
 * back; the answer is auto-run gated on a checkbox, debounced ~1.5s
 * so a single edit does not trigger several runs in a row, and an
 * explicit "Run now" button so the reviewer is never waiting for the
 * debounce to fire.
 */
export const SANDBOX_AUTORUN = {
  toggleLabel: "Auto-run sandbox after each edit",
  toggleHint:
    "We wait about 1.5 seconds after your last edit, then re-run the sandbox so the impact stays fresh.",
  runNowLabel: "Run now",
  runNowAria:
    "Run the sandbox test against the unsaved draft right now, without waiting for auto-run",
  runNowRunningAria: "Running the sandbox test now",
  staleNotice:
    "Your last edit has not been tested yet. Auto-run will pick it up shortly, or click Run now.",
  pendingDebounceLabel: "Auto-run pending...",
} as const;

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
    replace: "Swap a symptom or sign",
    add: "Add a symptom or sign",
    idle: "Find a symptom or sign",
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
  idleHintStrong: "+ Add a symptom",
  idleHintTail: "buttons inside a group.",
  loadError: "Could not search the clinical terms. Please try again.",
} as const;

