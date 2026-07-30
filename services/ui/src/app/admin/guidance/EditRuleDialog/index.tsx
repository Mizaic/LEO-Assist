/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Widescreen step editor for an AI-generated guidance rule.
 *
 * Layout (v3 -- Phase 3 of the wizard redesign):
 *
 *   +--- DialogTitle (guideline kicker + chapter caption) ---+
 *   +--- HorizontalStepper (4 jump-able steps, 56px tall) ---+
 *   |                          |                             |
 *   |     CANVAS (~60%)        |   right column (~40%)      |
 *   |                          |   always visible, no toggle |
 *   |                          |                             |
 *   +--- Sticky DialogActions (Cancel | Previous/Next step | Save) -+
 *
 *   - The plain-English LivePreviewPane is the source of truth for
 *     reviewers; it sits permanently on the right so the user always
 *     knows what the rule means as they edit. The previous one-line
 *     LivePreviewBanner + slide-in LivePreviewDrawer trade-off was
 *     deleted in Phase 3.
 *   - While the guided highlight-to-build wizard (step "who") is
 *     still working through its own steps, the right column shows
 *     GuidelineQuotePanel (the pinned NICE wording) instead --
 *     LivePreviewPane has nothing useful to summarise until the tree
 *     is actually built, and pinning the source sentence removes the
 *     scroll-up-scroll-down loop reviewers hit checking their picks
 *     against it. `guidedPanelMode` swaps back to "preview" once the
 *     wizard reaches Review.
 *   - ChipSearchPopover still anchors to the chip / +Add element the
 *     reviewer just clicked, so concept search appears in context
 *     instead of in a separate column.
 *
 * Footer: sticky DialogActions with Previous/Next step / Save. Save is the
 * single primary action; it is gated on a >=3-character reason and a
 * valid tree, exactly as in the previous design.
 *
 * Saving POSTs to /api/guidance/rules/review/{id}/decision with
 * ``{ action: "edit", reason, updates: { name, strength, logic_tree } }``.
 * The backend writes a new versioned rule and returns the new rule_id.
 *
 * Design Controls: UN-LEO-AI-094 (v2), DI-LEO-AI-512 (v2),
 *                  DO-LEO-AI-512 (v2), R-LEO-AI-509 (v2),
 *                  VT-LEO-AI-511 (v2).
 */

import { forwardRef, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion as fm } from "framer-motion";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { TransitionProps } from "@mui/material/transitions";
import CloseIcon from "@mui/icons-material/Close";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import FullscreenExitIcon from "@mui/icons-material/FullscreenExit";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";

import { useMotion } from "@leo/design-system";

import CoachTour from "@/components/ui/CoachTour";

import {
  EDIT_RULE_TOUR_STEPS,
  editTourPhaseForStep,
  type TourStep,
} from "../guidanceTourSteps";
import ConceptCoachPopover from "./ConceptCoachPopover";
import ConceptSearchPanel from "./ConceptSearchPanel";
import ConceptSynonymDialog from "./ConceptSynonymDialog";
import ChipSearchPopover from "./ChipSearchPopover";
import HorizontalStepper from "./HorizontalStepper";
import GuidelineQuotePanel from "./GuidelineQuotePanel";
import type { WizardJumpRequest } from "./HighlightWizard";
import type { WizardStepKind } from "./HighlightWizard/wizardState";
import LivePreviewPane from "./LivePreviewPane";
import {
  buildNavSlots,
  slotToWizardTarget,
  type NavSlot,
  type WizardNavTarget,
} from "./navSlots";

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
import Step1Who from "./steps/Step1Who";
import Step2Suggest from "./steps/Step2Suggest";
import Step4Save from "./steps/Step4Save";
import ValidationIssueBanner from "./ValidationIssueBanner";
import {
  DIALOG_CHROME,
  GROUP_KIND_SHORT,
  friendlyTerm,
  type StepId,
} from "./copy";
import {
  applyUpdate,
  assignNodeIds,
  canHaveChildren,
  findActionsValidationError,
  findAllValidationErrors,
  findPriorityValidationError,
  findValidationError,
  findWizardValidationErrors,
  hasOrRootWithPrerequisites,
  observationWithCriterion,
  ensurePathwayKeys,
  promoteOrPrerequisites,
  sanitiseActionsForSave,
  stripNodeIds,
  wrapRootInAnd,
} from "./treeOps";
import { liftSharedPathwayDemographics } from "./liftSharedPathwayDemographics";
import { detectDemographicPhrase } from "./HighlightWizard/demographicPhraseMatch";
import { findDuplicateConceptGroups } from "./namedSets";
import { treeToSentence } from "./treeToSentence";
import { detectVaguePhrase } from "./vaguePhrases";
import { slidePanelVariants } from "../motionPresets";
import { normalizeRuleActions } from "../actionShape";
import {
  addFallbackAfter,
  addOrAlternativeAfter,
  removeActionKeepingGroups,
} from "./actionGroups";
import type {
  EditableLogicNode,
  LogicCriterion,
  NodeUpdate,
  RuleAction,
  RulePriority,
} from "./types";
import type {
  PathwayTextBoundary,
  RecommendationStructure,
} from "./SentenceEditor/pathwayTextSplit";

export interface EditableRule {
  rule_id: string;
  name?: string;
  /** Deprecated rule-level strength; used only to seed a legacy single
   *  action's strength when ``actions`` is absent (back-compat). */
  strength?: string;
  guideline_id?: string;
  chapter_title?: string;
  recommendation_text?: string;
  /** NICE HTML list tree for this recommendation, when it is a list
   *  rather than a plain sentence -- lets the highlight-to-build
   *  wizard's pathway-split step prefer real structure over the
   *  ", or"-boundary heuristic. Null/absent for plain sentences. */
  recommendation_structure?: RecommendationStructure | null;
  companion_panels?: import("./HighlightWizard/weightedChecklist").CompanionPanel[] | null;
  logic_tree?: unknown;
  /** One or more recommended procedures, each with its own strength. */
  actions?: RuleAction[];
  /** Deprecated: legacy single recommended SNOMED procedure. Surfaced
   *  from the API's actionJson for rules not yet migrated to
   *  ``actions``; null when uncoded. */
  action?: LogicCriterion | null;
  /** Rule-level clinical priority from HAS_ACTION edges. */
  action_priority?: RulePriority | null;
  /** Due-days paired with action_priority (null for routine). */
  action_due_days?: number | null;
  /** When true this rule fires only if no other rule in the guideline matched. */
  is_default?: boolean;
}

interface Props {
  rule: EditableRule | null;
  open: boolean;
  saving?: boolean;
  /** Shown inside the dialog when the parent save call fails --
   *  errors rendered behind this modal are invisible to the reviewer. */
  saveError?: string | null;
  onClose: () => void;
  onSave: (payload: {
    name: string;
    logic_tree: Record<string, unknown>;
    reason: string;
    /** Only set when the reviewer changed the recommended procedures;
     *  omitting it preserves the predecessor's actionJson server-side. */
    actions?: Array<Record<string, unknown>>;
    /** Only set when the reviewer changed clinical priority; omitting
     *  it preserves the predecessor's HAS_ACTION priority server-side. */
    priority?: RulePriority;
    due_days?: number | null;
    is_default?: boolean;
  }) => void;
}

function deriveInitialPriority(rule: EditableRule): RulePriority {
  const raw = (rule.action_priority || "").toLowerCase();
  if (
    raw === "immediate" ||
    raw === "very_urgent" ||
    raw === "2ww" ||
    raw === "urgent" ||
    raw === "routine"
  ) {
    return raw;
  }
  return "routine";
}

interface SearchTarget {
  mode: "replace" | "add" | "replace_action" | "idle";
  parentNodeId: string | null;
  nodeId: string | null;
  /** When mode is ``replace``, distinguishes symptom chips from lab values. */
  replaceKind: "concept" | "observation" | null;
  /** When mode is ``replace_action``, which row of ``actions`` is targeted. */
  actionIndex: number | null;
  initialQuery: string;
  focusLabel: string | null;
  /**
   * DOM element the popover should anchor to. Captured from the
   * chip's onClick / +Add button onClick so the search appears
   * directly under the trigger the user just touched.
   *
   * For the in-step `replace_action` slot we leave this null because
   * Step 2 still renders the search inline beneath the action chip.
   */
  anchorEl: HTMLElement | null;
  /**
   * Only meaningful when ``mode === "add"``. The highlight-to-build
   * wizard's own "add" triggers (a Step 3 row click, a Step 1
   * highlighted selection) set this so the popover offers a
   * multi-select picker with an explicit confirm, letting the
   * reviewer pick more than one SNOMED code for the same row/phrase
   * in one go (bundled into a single LogicCriterion's ``seeds``, i.e.
   * "match any of these" -- never several separate ANDed leaves).
   * The Advanced/Sentence editor's own "+Add" leaves this false so it
   * keeps ConceptSearchPanel's single-pick flow, including the
   * "Compare value..." observation affordance MultiConceptPicker does
   * not have.
   */
  multiPick: boolean;
}

const IDLE_TARGET: SearchTarget = {
  mode: "idle",
  parentNodeId: null,
  nodeId: null,
  replaceKind: null,
  actionIndex: null,
  initialQuery: "",
  focusLabel: null,
  anchorEl: null,
  multiPick: false,
};

/**
 * Derive the editor's initial ``actions`` array from a loaded rule.
 * Prefers the new ``actions`` field; falls back to the legacy singular
 * ``action``/``strength`` pair (wrapped as a 1-item array) so rules
 * from a server that has not migrated yet still edit correctly.
 */
function deriveInitialActions(rule: EditableRule): RuleAction[] {
  const normalized = normalizeRuleActions(rule.actions as unknown[] | undefined);
  if (normalized && normalized.length > 0) return normalized;
  if (rule.action) {
    return [{ criterion: rule.action, strength: rule.strength || "unspecified" }];
  }
  // A rule always needs at least one recommended-procedure row so the
  // reviewer has somewhere to pick a code; seed a blank one rather than
  // starting from an empty list. A leftover rule-level ``strength`` from
  // a not-yet-migrated legacy rule is preserved on that blank row rather
  // than silently dropped.
  return [
    {
      criterion: { snomed_concept_id: "", preferred_term: "" },
      strength: rule.strength || "unspecified",
    },
  ];
}

/** Blank action row seeded by "+ Add another procedure". */
function makeBlankAction(): RuleAction {
  return {
    criterion: { snomed_concept_id: "", preferred_term: "" },
    strength: "unspecified",
  };
}

/**
 * Bouncy pop-in/out transition for the rule editor Dialog, replacing MUI's
 * flat default fade. Lifecycle callbacks (onEnter/onEntered/onExit/
 * onExited) are driven by a timer matched to the spring's settle time,
 * not by framer's onAnimationComplete -- this keeps Modal's focus and
 * unmount handling deterministic in both real browsers and jsdom tests.
 */
const BouncyDialogTransition = forwardRef<
  HTMLDivElement,
  TransitionProps & { children: React.ReactElement }
>(function BouncyDialogTransition(props, ref) {
  const {
    children,
    in: inProp,
    onEnter,
    onEntered,
    onExit,
    onExited,
    className,
    style,
  } = props;
  const { reducedMotion } = useMotion();
  const settleMs = reducedMotion ? 0 : 260;

  useEffect(() => {
    if (inProp) {
      onEnter?.(null as unknown as HTMLElement, true);
      const t = setTimeout(() => onEntered?.(null as unknown as HTMLElement, true), settleMs);
      return () => clearTimeout(t);
    }
    onExit?.(null as unknown as HTMLElement);
    const t = setTimeout(() => onExited?.(null as unknown as HTMLElement), settleMs);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inProp, settleMs]);

  const hidden = reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.9, y: 28 };
  const visible = reducedMotion ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 };

  // Do not spread MUI TransitionProps onto fm.div -- boolean enter/exit
  // and React drag handlers conflict with framer-motion's prop types.
  // tabIndex=-1: Modal focuses this transition root for assistive tech.
  return (
    <fm.div
      ref={ref}
      className={className}
      style={style as React.CSSProperties | undefined}
      tabIndex={-1}
      initial={hidden}
      animate={inProp ? visible : hidden}
      transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 340, damping: 28 }}
    >
      {children}
    </fm.div>
  );
});

export default function EditRuleDialog({
  rule,
  open,
  saving,
  saveError = null,
  onClose,
  onSave,
}: Props) {
  const [tree, setTree] = useState<EditableLogicNode | null>(null);
  const [originalTree, setOriginalTree] = useState<EditableLogicNode | null>(
    null,
  );
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [searchTarget, setSearchTarget] = useState<SearchTarget>(IDLE_TARGET);
  const [fullscreen, setFullscreen] = useState(false);
  const [editTourActive, setEditTourActive] = useState(false);
  const [tourGotoRequest, setTourGotoRequest] = useState<{
    requestId: number;
    phase: WizardStepKind;
  } | null>(null);
  const tourGotoSeq = useRef(0);
  const [coach, setCoach] = useState<{
    nodeId: string;
    anchor: HTMLElement;
  } | null>(null);
  // The SNOMED-coded recommended procedures (actions) -- separate from
  // the logic tree because they are what the system *suggests* when the
  // rule matches, not what the patient must have. ``actionsDirty`` lets
  // us omit ``actions`` from the save payload when the reviewer never
  // touched them, so the server preserves the predecessor's actionJson
  // unchanged (DI-LEO-AI-170 safety constraint).
  const [actions, setActions] = useState<RuleAction[]>([]);
  const [originalActions, setOriginalActions] = useState<RuleAction[]>([]);
  const [actionsDirty, setActionsDirty] = useState(false);
  const [priority, setPriority] = useState<RulePriority>("routine");
  const [dueDays, setDueDays] = useState<number | null>(null);
  const [originalPriority, setOriginalPriority] =
    useState<RulePriority>("routine");
  const [originalDueDays, setOriginalDueDays] = useState<number | null>(null);
  const [isDefault, setIsDefault] = useState(false);
  const [currentStepId, setCurrentStepId] = useState<StepId>("who");
  /** Guided wizard phase for the flat stepper (null when not mounted). */
  const [wizardPhase, setWizardPhase] = useState<WizardStepKind | null>(null);
  /** Pin the NICE quote while building; live preview at Check / Suggest / Save. */
  const guidedPanelMode: "quote" | "preview" =
    currentStepId === "who" &&
    wizardPhase != null &&
    wizardPhase !== "review"
      ? "quote"
      : "preview";
  /** Confirmed situation count -- survives Review clearing active index. */
  const [situationCount, setSituationCount] = useState(0);
  /** True once the reviewer has reached Check so that slot stays jumpable. */
  const [reachedCheck, setReachedCheck] = useState(false);
  /** Flat-stepper jump into a guided phase. */
  const [navGotoRequest, setNavGotoRequest] = useState<{
    requestId: number;
    target: WizardNavTarget;
  } | null>(null);
  const navGotoSeq = useRef(0);
  /** Which situation (Step 3 pathway) the guided wizard is currently
   *  building, if any -- see GuidelineQuotePanel's `pathwayBoundaries`/
   *  `activePathwayIndex` props. Null before a pathway split exists. */
  const [activeSituation, setActiveSituation] = useState<{
    boundaries: PathwayTextBoundary[] | null;
    pathwayIndex: number | null;
  }>({ boundaries: null, pathwayIndex: null });
  /** The CONCEPT leaf currently open in the add/remove/depth synonym
   *  editor -- see ConceptSynonymDialog and HighlightWizard's
   *  `onEditConcept` doc comment. Null when the dialog is closed. */
  const [synonymEditorNodeId, setSynonymEditorNodeId] = useState<string | null>(
    null,
  );
  const handleEditConcept = useCallback(
    (nodeId: string) => setSynonymEditorNodeId(nodeId),
    [],
  );
  /** "Take me there" state for the issue banner -- see
   *  `ValidationIssueBanner` and `HighlightWizard`'s `WizardJumpRequest`
   *  doc comment. Lives here (above the "who" step) because the issue
   *  banner itself is visible from Step 4 (Save), where the tree is
   *  not even mounted yet -- jumping has to switch the outer step
   *  first, then hand the wizard a fresh request. */
  const [jumpRequest, setJumpRequest] = useState<WizardJumpRequest | null>(null);
  const handleJumpToIssue = useCallback((nodeId: string) => {
    setCurrentStepId("who");
    setJumpRequest({ nodeId, requestId: Date.now() });
  }, []);
  // Stable across renders (see HighlightWizard's `onActiveSituationChange`
  // dependency array) -- an inline arrow function here would get a new
  // identity on every render, re-firing that effect, calling this, and
  // re-rendering forever.
  const handleActiveSituationChange = useCallback(
    (boundaries: PathwayTextBoundary[] | null, pathwayIndex: number | null) => {
      if (boundaries?.length) {
        setSituationCount(boundaries.length);
      }
      setActiveSituation((prev) =>
        prev.boundaries === boundaries && prev.pathwayIndex === pathwayIndex
          ? prev
          : { boundaries, pathwayIndex },
      );
    },
    [],
  );

  const handleWizardPhaseChange = useCallback((phase: WizardStepKind | null) => {
    setWizardPhase(phase);
    if (phase === "review") setReachedCheck(true);
  }, []);
  const [stepDirection, setStepDirection] = useState<1 | -1>(1);
  const prevStepIndexRef = useRef(0);
  const { reducedMotion } = useMotion();

  useEffect(() => {
    if (!rule) return;
    // wrapRootInAnd: some pending-review AI-extracted rules persist a
    // single criterion as a BARE leaf root (e.g. NG12 1.2.8's
    // {"kind": "concept", "criterion": {...}}), with no AND wrapper.
    // GroupSentence / GroupBody both assume the root is a group (they
    // read node.children, the kind Select, etc.) -- fed a bare leaf
    // they rendered it as an empty group ("nothing yet"), silently
    // hiding the one real criterion from the reviewer. A reviewer who
    // then used "+ add another symptom" to add back the very same
    // criterion they could not see ended up with it TWICE once the
    // add flow's own wrapRootInAnd finally surfaced the hidden
    // original alongside the new pick. Wrapping unconditionally here
    // guarantees both canvases always receive a real group root.
    // ensurePathwayKeys: backfills a stable pathway_key onto every
    // pathway that predates this field (see the "Stable identity"
    // plan section / pathway-stable-key). Safe to run on every load --
    // a pathway that already has a key is left untouched.
    // liftSharedPathwayDemographics: NG12 1.1.2 (and similar) store
    // age inside every pathway AND; lift identical demographics to
    // Always true so the wizard / Scenario model show one shared filter.
    const initialTree = ensurePathwayKeys(
      liftSharedPathwayDemographics(
        wrapRootInAnd(
          rule.logic_tree && typeof rule.logic_tree === "object"
            ? assignNodeIds(rule.logic_tree as EditableLogicNode)
            : assignNodeIds({ kind: "AND", children: [] }),
        ),
      ),
    );
    setTree(initialTree);
    setOriginalTree(initialTree);
    setName(rule.name ?? "");
    setReason("");
    setSearchTarget(IDLE_TARGET);
    setCoach(null);
    const initialActions = deriveInitialActions(rule);
    setActions(initialActions);
    setOriginalActions(initialActions);
    setActionsDirty(false);
    const initialPriority = deriveInitialPriority(rule);
    const initialDueDays =
      initialPriority === "routine"
        ? null
        : rule.action_due_days == null
          ? null
          : Number(rule.action_due_days);
    setPriority(initialPriority);
    setDueDays(
      initialDueDays != null && Number.isFinite(initialDueDays)
        ? initialDueDays
        : null,
    );
    setOriginalPriority(initialPriority);
    setOriginalDueDays(
      initialDueDays != null && Number.isFinite(initialDueDays)
        ? initialDueDays
        : null,
    );
    setIsDefault(rule.is_default ?? false);
    setCurrentStepId("who");
    setWizardPhase(null);
    setSituationCount(0);
    setReachedCheck(false);
    setNavGotoRequest(null);
    setActiveSituation({ boundaries: null, pathwayIndex: null });
  }, [rule]);

  const summary = useMemo(() => treeToSentence(tree), [tree]);
  const beforeSummary = useMemo(
    () => treeToSentence(originalTree),
    [originalTree],
  );
  const duplicates = useMemo(() => findDuplicateConceptGroups(tree), [tree]);

  // The chip-anchored search popover is open whenever there is an
  // active concept-picking target. Every trigger -- including the
  // guided highlight-to-build wizard's own row clicks and Step 1's
  // "highlight more text" confirm -- supplies a real anchor element
  // (the row/button/word chunk just clicked) so the popover appears
  // right next to it, same as every other chip-anchored interaction.
  // The `replace_action` slot in Step 2 still renders the search
  // inline (it is not a chip-anchored interaction), so it is excluded
  // here regardless.
  const chipPopoverOpen = searchTarget.mode === "replace" || searchTarget.mode === "add";

  const validationError = useMemo(() => findValidationError(tree), [tree]);
  // Full tree issues for Save (unfinished situations must block approve).
  const validationIssues = useMemo(() => findAllValidationErrors(tree), [tree]);
  // Mid-wizard banner: hide empty situation shells still waiting to be coded.
  const wizardValidationIssues = useMemo(
    () => findWizardValidationErrors(tree),
    [tree],
  );
  const actionsError = useMemo(
    () => findActionsValidationError(actions),
    [actions],
  );
  const priorityError = useMemo(
    () => findPriorityValidationError(priority, dueDays),
    [priority, dueDays],
  );
  const reasonReady = reason.trim().length >= 3;
  const canSave =
    !!tree &&
    !validationError &&
    !actionsError &&
    !priorityError &&
    reasonReady &&
    !saving;

  const { slots: navSlots, currentId: currentSlotId, currentIndex: navIndex } =
    useMemo(
      () =>
        buildNavSlots({
          outerStep: currentStepId,
          wizardPhase,
          situationCount,
          situationIndex: activeSituation.pathwayIndex ?? 0,
          reachedCheck,
        }),
      [
        currentStepId,
        wizardPhase,
        situationCount,
        activeSituation.pathwayIndex,
        reachedCheck,
      ],
    );

  const prepareEditTourStep = useCallback(async (step: TourStep) => {
    const phase = editTourPhaseForStep(step.id);
    if (!phase) return true;
    if (phase === "save") {
      setCurrentStepId((prev) => (prev === "save" ? prev : "save"));
      setTourGotoRequest(null);
      await delay(120);
      return true;
    }
    setCurrentStepId((prev) => (prev === "who" ? prev : "who"));
    tourGotoSeq.current += 1;
    setTourGotoRequest({
      requestId: tourGotoSeq.current,
      phase,
    });
    await delay(phase === "review" ? 280 : 160);
    return true;
  }, []);

  const finishEditTour = useCallback(() => {
    setEditTourActive(false);
    setTourGotoRequest(null);
  }, []);

  const handleJumpSlot = useCallback(
    (slot: NavSlot) => {
      const nextIndex = navSlots.findIndex((s) => s.id === slot.id);
      setStepDirection(nextIndex >= prevStepIndexRef.current ? 1 : -1);
      prevStepIndexRef.current = Math.max(0, nextIndex);
      setSearchTarget(IDLE_TARGET);
      if (slot.surface !== "who") {
        setCurrentStepId(slot.surface);
        return;
      }
      setCurrentStepId("who");
      const target = slotToWizardTarget(slot);
      if (!target) return;
      navGotoSeq.current += 1;
      setNavGotoRequest({
        requestId: navGotoSeq.current,
        target,
      });
    },
    [navSlots],
  );

  const isFirstStep = navIndex <= 0;
  const isLastStep = navIndex >= navSlots.length - 1;
  const nextSlot = !isLastStep ? navSlots[navIndex + 1] : null;
  const prevSlot = !isFirstStep ? navSlots[navIndex - 1] : null;
  const canGoNext = Boolean(nextSlot?.jumpable);
  const currentIndex = navIndex;

  const handleNext = useCallback(() => {
    if (!nextSlot?.jumpable) return;
    handleJumpSlot(nextSlot);
  }, [nextSlot, handleJumpSlot]);

  const handleBack = useCallback(() => {
    if (!prevSlot) return;
    handleJumpSlot(prevSlot);
  }, [prevSlot, handleJumpSlot]);

  function handleUpdate(update: NodeUpdate) {
    setTree((curr) => (curr ? applyUpdate(curr, update) : curr));
    if (update.kind === "remove" && searchTarget.nodeId === update.nodeId) {
      setSearchTarget(IDLE_TARGET);
    }
  }

  function handleSelectNode(
    nodeId: string,
    anchor?: HTMLElement | null,
  ) {
    if (!tree) return;
    const focused = findNode(tree, nodeId);
    if (!focused) return;
    if (focused.kind === "OBSERVATION") {
      const friendly = friendlyTerm(focused.observation?.observable_term);
      setSearchTarget({
        mode: "replace",
        parentNodeId: null,
        nodeId,
        replaceKind: "observation",
        actionIndex: null,
        initialQuery: friendly,
        focusLabel: friendly
          ? `Swapping lab value: ${friendly}`
          : "Pick a lab value to compare",
        anchorEl: anchor ?? null,
        multiPick: false,
      });
      return;
    }
    if (focused.kind !== "CONCEPT") {
      setSearchTarget(IDLE_TARGET);
      return;
    }
    const friendly = friendlyTerm(focused.criterion?.preferred_term);
    setSearchTarget({
      mode: "replace",
      parentNodeId: null,
      nodeId,
      replaceKind: "concept",
      actionIndex: null,
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping: ${friendly}`
        : "Pick a symptom, sign, procedure, or situation for the empty pill",
      anchorEl: anchor ?? null,
      multiPick: false,
    });
  }

  function handleRequestAdd(
    parentNodeId: string,
    anchor?: HTMLElement | null,
    initialQuery?: string,
    multiPick?: boolean,
  ) {
    if (!tree) return;
    // Age and sex are never SNOMED-coded -- a highlighted phrase like
    // "aged 40 and over" must open the same inline age/sex editor the
    // "+ Add age" button does, pre-filled with the parsed threshold,
    // instead of falling through to concept search (which can only ever
    // surface a bare "current age" observable that has no threshold of
    // its own to add). See `demographicPhraseMatch.ts`'s doc comment.
    const demographic = initialQuery ? detectDemographicPhrase(initialQuery) : null;
    if (demographic) {
      handleUpdate({
        kind: "add_demographic",
        parentNodeId,
        field: demographic.field,
        prefill: {
          operator: demographic.operator,
          value: demographic.value,
          value2: demographic.value2,
          unit: demographic.unit,
        },
        sourceRowText: initialQuery,
      });
      return;
    }
    const parent = findNode(tree, parentNodeId);
    setSearchTarget({
      mode: "add",
      parentNodeId,
      nodeId: null,
      replaceKind: null,
      actionIndex: null,
      initialQuery: initialQuery ?? "",
      focusLabel: parent
        ? `Adding to: ${groupLabel(parent.kind)}`
        : "Adding a symptom, sign, procedure, or situation",
      anchorEl: anchor ?? null,
      multiPick: multiPick ?? false,
    });
  }

  /** Empty-state CTA: anchor a popover for adding the very first
   *  symptom under the root tree. */
  function handleAddFirstSymptom(anchor: HTMLElement) {
    if (!tree) return;
    handleRequestAdd(tree.node_id, anchor);
  }

  function handleAddFirstDemographic() {
    if (!tree) return;
    handleUpdate({ kind: "add_demographic", parentNodeId: tree.node_id });
  }

  function handleAddFirstObservation() {
    if (!tree) return;
    handleUpdate({ kind: "add_observation", parentNodeId: tree.node_id });
  }

  function handleRequestCoach(nodeId: string, anchor: HTMLElement) {
    setCoach({ nodeId, anchor });
  }

  function handleCoachAddCriteria(
    criteria: LogicCriterion[],
    replaceVague: boolean,
  ) {
    if (!tree || !coach) return;
    const parent = findParent(tree, coach.nodeId);
    if (!parent) return;
    let nextTree: EditableLogicNode | null = tree;
    for (const criterion of criteria) {
      if (!nextTree) break;
      nextTree = applyUpdate(nextTree, {
        kind: "add_concept",
        parentNodeId: parent.node_id,
        criterion,
      });
    }
    if (replaceVague && nextTree) {
      nextTree = applyUpdate(nextTree, { kind: "remove", nodeId: coach.nodeId });
    }
    setTree(nextTree);
    setCoach(null);
    if (replaceVague && searchTarget.nodeId === coach.nodeId) {
      setSearchTarget(IDLE_TARGET);
    }
  }

  function handleCoachSearchMore(topic: string) {
    if (!coach || !tree) return;
    const parent = findParent(tree, coach.nodeId);
    // Anchor the chip popover to the coach popover's element if we
    // can find it; otherwise fall back to "no anchor" which leaves
    // the popover anchored to the chip the coach was opened on.
    setSearchTarget({
      mode: "add",
      parentNodeId: parent?.node_id ?? null,
      nodeId: null,
      replaceKind: null,
      actionIndex: null,
      initialQuery: topic,
      focusLabel: `Adding to: ${parent ? groupLabel(parent.kind) : "the rule"}`,
      anchorEl: coach.anchor,
      multiPick: false,
    });
    setCoach(null);
  }

  function handleSelectAction(index: number) {
    const friendly = friendlyTerm(actions[index]?.criterion?.preferred_term);
    setSearchTarget({
      mode: "replace_action",
      parentNodeId: null,
      nodeId: null,
      replaceKind: null,
      actionIndex: index,
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping procedure ${index + 1}: ${friendly}`
        : `Pick the procedure for row ${index + 1}`,
      anchorEl: null,
      multiPick: false,
    });
  }

  function handleActionStrengthChange(index: number, strength: string) {
    setActions((prev) =>
      prev.map((a, i) => (i === index ? { ...a, strength } : a)),
    );
    setActionsDirty(true);
  }

  function handleAddAction() {
    setActions((prev) => [...prev, makeBlankAction()]);
    setActionsDirty(true);
  }

  function handleAddFallback(afterIndex: number) {
    const { actions: next, newIndex } = addFallbackAfter(actions, afterIndex);
    setActions(next);
    setActionsDirty(true);
    handleSelectAction(newIndex);
  }

  function handleAddOrAlternative(afterIndex: number) {
    const { actions: next, newIndex } = addOrAlternativeAfter(
      actions,
      afterIndex,
    );
    setActions(next);
    setActionsDirty(true);
    handleSelectAction(newIndex);
  }

  function handleRemoveAction(index: number) {
    setActions((prev) => removeActionKeepingGroups(prev, index));
    setActionsDirty(true);
    if (searchTarget.mode === "replace_action" && searchTarget.actionIndex === index) {
      setSearchTarget(IDLE_TARGET);
    }
  }

  function handlePriorityChange(next: RulePriority) {
    setPriority(next);
    if (next === "routine") setDueDays(null);
    // NICE "immediate specialist assessment" -- same-day by default.
    else if (next === "immediate") setDueDays(0);
    // NICE "very urgent" -- appointment within 48 hours.
    else if (next === "very_urgent") setDueDays(2);
  }

  function handleDueDaysChange(next: number | null) {
    setDueDays(priority === "routine" ? null : next);
  }

  function handlePick(criterion: LogicCriterion) {
    if (searchTarget.mode === "replace_action" && searchTarget.actionIndex !== null) {
      const idx = searchTarget.actionIndex;
      setActions((prev) => prev.map((a, i) => (i === idx ? { ...a, criterion } : a)));
      setActionsDirty(true);
      setSearchTarget(IDLE_TARGET);
      return;
    }
    if (searchTarget.mode === "replace" && searchTarget.nodeId) {
      const focused = tree ? findNode(tree, searchTarget.nodeId) : null;
      if (
        focused?.kind === "OBSERVATION" &&
        focused.observation &&
        searchTarget.replaceKind === "observation"
      ) {
        handleUpdate({
          kind: "set_observation",
          nodeId: searchTarget.nodeId,
          observation: observationWithCriterion(focused.observation, criterion),
        });
      } else {
        handleUpdate({
          kind: "replace_concept",
          nodeId: searchTarget.nodeId,
          criterion,
        });
      }
      setSearchTarget(IDLE_TARGET);
      return;
    }
    if (searchTarget.mode === "add" && searchTarget.parentNodeId && tree) {
      // See EditableLogicNode.source_row_text's doc comment: when this
      // "add" was opened pre-filled from a wizard row/selection (the
      // only case initialQuery is ever non-empty), tag the new leaf
      // with that row's own text so it reliably resolves back to that
      // row even when the picked term shares no wording with it.
      const sourceRowText = searchTarget.initialQuery.trim() || undefined;
      const parent = findNode(tree, searchTarget.parentNodeId);
      if (parent && canHaveChildren(parent.kind)) {
        handleUpdate({
          kind: "add_concept",
          parentNodeId: searchTarget.parentNodeId,
          criterion,
          sourceRowText,
        });
      } else if (parent && parent.node_id === tree.node_id) {
        const groupRoot = wrapRootInAnd(tree);
        setTree(
          applyUpdate(groupRoot, {
            kind: "add_concept",
            parentNodeId: groupRoot.node_id,
            criterion,
            sourceRowText,
          }),
        );
      }
      setSearchTarget(IDLE_TARGET);
    }
  }

  /**
   * Phase 6b: reviewer picked "Compare value..." on an observable hit.
   * Only meaningful in "add" mode (inserting a new leaf under a
   * group). The seeded OBSERVATION leaf carries the SNOMED code and
   * term; the reviewer fills in the operator / threshold / unit in
   * the canvas inline.
   */
  /**
   * Bulk-add from "Ask LEO for ideas": several sibling CONCEPT leaves
   * under the current add-target parent. Same tree mutation path as
   * ConceptCoachPopover's onAddCriteria, without replacing a vague chip.
   */
  function handleAddMany(criteria: LogicCriterion[]) {
    if (!tree || searchTarget.mode !== "add" || !searchTarget.parentNodeId) {
      return;
    }
    if (criteria.length === 0) return;
    const sourceRowText = searchTarget.initialQuery.trim() || undefined;
    let nextTree: EditableLogicNode | null = tree;
    const parent = findNode(tree, searchTarget.parentNodeId);
    let parentId = searchTarget.parentNodeId;
    if (parent && !canHaveChildren(parent.kind) && parent.node_id === tree.node_id) {
      nextTree = wrapRootInAnd(tree);
      parentId = nextTree.node_id;
    } else if (!parent || !canHaveChildren(parent.kind)) {
      return;
    }
    for (const criterion of criteria) {
      if (!nextTree) break;
      nextTree = applyUpdate(nextTree, {
        kind: "add_concept",
        parentNodeId: parentId,
        criterion,
        sourceRowText,
      });
    }
    setTree(nextTree);
    setSearchTarget(IDLE_TARGET);
  }

  function handlePickObservation(seed: {
    observable_id: string;
    observable_term?: string;
    unit?: string;
  }) {
    if (searchTarget.mode !== "add" || !searchTarget.parentNodeId || !tree) return;
    const parent = findNode(tree, searchTarget.parentNodeId);
    if (parent && canHaveChildren(parent.kind)) {
      handleUpdate({
        kind: "add_observation",
        parentNodeId: searchTarget.parentNodeId,
        seed,
      });
    } else if (parent && parent.node_id === tree.node_id) {
      const groupRoot = wrapRootInAnd(tree);
      setTree(
        applyUpdate(groupRoot, {
          kind: "add_observation",
          parentNodeId: groupRoot.node_id,
          seed,
        }),
      );
    }
    setSearchTarget(IDLE_TARGET);
  }

  function handleClosePopover() {
    setSearchTarget(IDLE_TARGET);
  }

  function handleSave() {
    if (!tree || !canSave) return;
    // Always send the PriorityPanel values. A dirty-flag omit path
    // silently dropped 2WW / urgent changes after remounts and the BE
    // then carried the predecessor's routine forward.
    onSave({
      name: name.trim(),
      logic_tree: stripNodeIds(tree),
      reason: reason.trim(),
      ...(actionsDirty ? { actions: sanitiseActionsForSave(actions) } : {}),
      priority,
      due_days: priority === "routine" ? null : dueDays,
      is_default: isDefault,
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      fullScreen={fullscreen}
      maxWidth="xl"
      disableEnforceFocus
      TransitionComponent={BouncyDialogTransition}
      aria-labelledby="edit-rule-dialog-title"
      PaperProps={{
        sx: fullscreen
          ? { display: "flex", flexDirection: "column", overflow: "hidden" }
          : {
              // An explicit `height` (not just `minHeight`) is required here:
              // without it, Paper sizes to its content's natural height and
              // the descendant `flex: 1, minHeight: 0` chain below has
              // nothing definite to shrink against, so the canvas / preview
              // columns never get a bounded box to scroll inside -- the
              // whole dialog just grows past the viewport instead.
              height: "80vh",
              maxHeight: "calc(100vh - 64px)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            },
      }}
    >
      <DialogTitle
        id="edit-rule-dialog-title"
        component="div"
        sx={{
          pb: 1.25,
          pt: 1.75,
          px: 2.5,
          borderBottom: "1px solid",
          borderColor: "divider",
          background:
            "linear-gradient(180deg, var(--mui-palette-background-paper, #fff) 0%, var(--mui-palette-grey-50, #fafafa) 100%)",
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {rule?.guideline_id && (
              <Typography
                variant="caption"
                sx={{
                  display: "block",
                  color: "primary.dark",
                  fontWeight: 700,
                  letterSpacing: 0.6,
                  textTransform: "uppercase",
                  fontSize: "0.68rem",
                  lineHeight: 1.2,
                }}
              >
                {rule.guideline_id}
              </Typography>
            )}
            <Typography
              variant="h6"
              component="h2"
              sx={{
                fontWeight: 700,
                fontSize: "1.2rem",
                lineHeight: 1.25,
                mt: rule?.guideline_id ? 0.25 : 0,
              }}
            >
              {DIALOG_CHROME.title}
            </Typography>
            {rule?.chapter_title && (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{
                  mt: 0.25,
                  lineHeight: 1.4,
                  display: "-webkit-box",
                  WebkitLineClamp: 1,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {rule.chapter_title}
              </Typography>
            )}
          </Box>
          <Button
            size="small"
            variant="text"
            onClick={() => setEditTourActive(true)}
            aria-label="Take the edit-rule tour"
            data-testid="edit-rule-tour-trigger"
            sx={{ textTransform: "none", mr: 0.5 }}
          >
            Guide me
          </Button>
          <Tooltip
            title={fullscreen ? "Shrink to a window" : "Use the full screen"}
          >
            <IconButton
              onClick={() => setFullscreen((v) => !v)}
              size="small"
              aria-label={
                fullscreen ? "Shrink to a window" : "Use the full screen"
              }
              sx={{ color: "text.secondary" }}
            >
              {fullscreen ? (
                <FullscreenExitIcon fontSize="small" />
              ) : (
                <FullscreenIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
          <Tooltip title="Close and discard unsaved changes.">
            <span>
              <IconButton
                onClick={onClose}
                size="small"
                aria-label="Close without saving"
                disabled={saving}
                sx={{ color: "text.secondary" }}
              >
                <CloseIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </DialogTitle>
      <CoachTour
        tourId="guidance-edit-rule"
        steps={EDIT_RULE_TOUR_STEPS}
        active={editTourActive}
        onFinish={finishEditTour}
        prepareStep={prepareEditTourStep}
      />
      <DialogContent
        dividers
        sx={{
          p: 0,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            flex: "1 1 auto",
            minHeight: 0,
          }}
        >
          <HorizontalStepper
            slots={navSlots}
            currentSlotId={currentSlotId}
            onJump={handleJumpSlot}
          />
          <Box
            sx={{
              display: "flex",
              flexDirection: { xs: "column", md: "row" },
              flex: "1 1 auto",
              minHeight: 0,
              minWidth: 0,
              overflow: { xs: "auto", md: "hidden" },
            }}
          >
            <Box
              role="region"
              aria-label={`Step ${currentIndex + 1} of ${navSlots.length}`}
              tabIndex={0}
              sx={{
                px: { xs: 2, md: 2.5 },
                py: { xs: 1.5, md: 2 },
                minWidth: 0,
                minHeight: 0,
                flex: { xs: "1 1 auto", md: "0 0 60%" },
                width: { xs: "100%", md: "60%" },
                overflowY: { xs: "visible", md: "auto" },
                // overflowY:auto forces overflowX to auto in CSS; clip
                // stray width so a second horizontal bar does not appear
                // under the stepper.
                overflowX: "hidden",
              }}
            >
            <fm.div
              key={currentStepId}
              variants={slidePanelVariants(reducedMotion, stepDirection)}
              initial="initial"
              animate="animate"
              transition={
                reducedMotion
                  ? { duration: 0 }
                  : { type: "spring", stiffness: 320, damping: 30 }
              }
            >
            {currentStepId === "who" && (
              <ValidationIssueBanner
                issues={wizardValidationIssues}
                onJumpToIssue={handleJumpToIssue}
              />
            )}
            {currentStepId === "who" && (
              <Step1Who
                tree={tree}
                selectedNodeId={searchTarget.nodeId}
                duplicates={duplicates}
                recommendationText={rule?.recommendation_text}
                recommendationStructure={rule?.recommendation_structure}
                companionPanels={rule?.companion_panels}
                onSelectNode={handleSelectNode}
                onUpdate={handleUpdate}
                onRequestAdd={handleRequestAdd}
                onRequestCoach={handleRequestCoach}
                onEditConcept={handleEditConcept}
                onAddFirstSymptom={handleAddFirstSymptom}
                onAddFirstDemographic={handleAddFirstDemographic}
                onAddFirstObservation={handleAddFirstObservation}
                ruleId={rule?.rule_id ?? ""}
                guidelineId={rule?.guideline_id}
                onAIDraft={(aiTree) => {
                  const withIds = assignNodeIds(aiTree);
                  setTree(withIds);
                }}
                onActiveSituationChange={handleActiveSituationChange}
                jumpRequest={jumpRequest}
                onWizardStepChange={handleWizardPhaseChange}
                tourGotoRequest={tourGotoRequest}
                navGotoRequest={navGotoRequest}
              />
            )}
            {currentStepId === "suggest" && (
              <Stack spacing={2}>
                {actionsError && (
                  <Alert severity="warning" sx={{ py: 0.5 }} role="status">
                    {actionsError}
                  </Alert>
                )}
                <Step2Suggest
                  name={name}
                  onNameChange={setName}
                  priority={priority}
                  dueDays={dueDays}
                  onPriorityChange={handlePriorityChange}
                  onDueDaysChange={handleDueDaysChange}
                  actions={actions}
                  selectedActionIndex={
                    searchTarget.mode === "replace_action"
                      ? searchTarget.actionIndex
                      : null
                  }
                  onSelectAction={handleSelectAction}
                  onActionStrengthChange={handleActionStrengthChange}
                  onRemoveAction={handleRemoveAction}
                  onAddAction={handleAddAction}
                  onAddFallback={handleAddFallback}
                  onAddOrAlternative={handleAddOrAlternative}
                  isDefault={isDefault}
                  onIsDefaultChange={setIsDefault}
                />
                {searchTarget.mode === "replace_action" && (
                  <Box
                    sx={{
                      p: 1.5,
                      borderRadius: 1.5,
                      border: "1px solid",
                      borderColor: "divider",
                      bgcolor: "background.paper",
                      position: "relative",
                    }}
                  >
                    <Box
                      sx={{
                        position: "absolute",
                        top: 4,
                        right: 4,
                      }}
                    >
                      <Tooltip title="Cancel changing the procedure (ESC)">
                        <IconButton
                          onClick={handleClosePopover}
                          size="small"
                          aria-label="Cancel changing the procedure"
                        >
                          <CloseIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                    <ConceptSearchPanel
                      mode="replace_action"
                      focusLabel={searchTarget.focusLabel}
                      initialQuery={searchTarget.initialQuery}
                      onPick={handlePick}
                    />
                  </Box>
                )}
              </Stack>
            )}
            {currentStepId === "save" && (
              <Step4Save
                reason={reason}
                onReasonChange={setReason}
                saving={saving}
                reasonError={
                  actionsError
                    ? `Fix the rule first: ${actionsError}`
                    : priorityError
                      ? `Fix the rule first: ${priorityError}`
                      : undefined
                }
                treeIssues={validationIssues}
                onJumpToIssue={handleJumpToIssue}
              />
            )}
            </fm.div>
            </Box>
            <Box
              role="region"
              aria-label="Side panel for guideline wording or live preview"
              tabIndex={0}
              sx={{
                flex: { xs: "1 1 auto", md: "0 0 40%" },
                width: { xs: "100%", md: "40%" },
                borderTop: { xs: "1px solid", md: "none" },
                borderLeft: { xs: "none", md: "1px solid" },
                borderColor: "divider",
                bgcolor: "grey.50",
                overflowY: { xs: "visible", md: "auto" },
                minHeight: 0,
              }}
            >
              {/* No AnimatePresence wait here: quote vs preview must
                  swap on the same paint as wizardPhase, or reviewers
                  (and tests) briefly see the wrong side panel. */}
              {guidedPanelMode === "quote" ? (
                <GuidelineQuotePanel
                  recommendationText={rule?.recommendation_text}
                  tree={tree}
                  pathwayBoundaries={activeSituation.boundaries}
                  activePathwayIndex={activeSituation.pathwayIndex}
                />
              ) : (
                <LivePreviewPane
                  summary={summary}
                  actions={actions}
                  priority={priority}
                  dueDays={dueDays}
                  showBeforeAfter={currentStepId === "save"}
                  beforeSummary={beforeSummary}
                  beforeActions={originalActions}
                  beforePriority={originalPriority}
                  beforeDueDays={originalDueDays}
                  recommendationText={rule?.recommendation_text}
                />
              )}
            </Box>
          </Box>
        </Box>
      </DialogContent>
      <ChipSearchPopover
        open={chipPopoverOpen}
        anchorEl={searchTarget.anchorEl}
        mode={
          searchTarget.mode === "replace" || searchTarget.mode === "add"
            ? searchTarget.mode
            : "add"
        }
        replaceKind={searchTarget.replaceKind}
        focusLabel={searchTarget.focusLabel}
        initialQuery={searchTarget.initialQuery}
        multiPick={searchTarget.mode === "add" && searchTarget.multiPick}
        onPick={handlePick}
        onAddMany={handleAddMany}
        onPickObservation={handlePickObservation}
        onClose={handleClosePopover}
      />
      {saveError ? (
        <Alert
          severity="error"
          role="alert"
          sx={{ mx: 3, mb: 0, mt: 1, flexShrink: 0 }}
        >
          {saveError}
        </Alert>
      ) : null}
      <DialogActions
        sx={{
          px: 3,
          py: 2,
          position: "sticky",
          bottom: 0,
          bgcolor: "background.paper",
          borderTop: "1px solid",
          borderColor: "divider",
          zIndex: 1,
          gap: 1,
        }}
      >
        <Tooltip title="Close without saving.">
          <span>
            <Button onClick={onClose} disabled={saving}>
              Cancel
            </Button>
          </span>
        </Tooltip>
        <Box sx={{ flex: 1 }} />
        {saving && (
          <CircularProgress size={18} aria-label="Saving your changes" />
        )}
        {!isFirstStep && (
          <Tooltip title={DIALOG_CHROME.previousStepTooltip}>
            <span>
              <Button
                onClick={handleBack}
                disabled={saving}
                startIcon={<ArrowBackRoundedIcon fontSize="small" />}
                aria-label={DIALOG_CHROME.previousStepAria}
              >
                {DIALOG_CHROME.previousStepLabel}
              </Button>
            </span>
          </Tooltip>
        )}
        {!isLastStep && (
          <Tooltip
            title={
              canGoNext
                ? DIALOG_CHROME.nextStepTooltip
                : "Confirm this step below before moving on."
            }
          >
            <span>
              <Button
                variant="outlined"
                onClick={handleNext}
                disabled={saving || !canGoNext}
                endIcon={<ArrowForwardRoundedIcon fontSize="small" />}
                aria-label={DIALOG_CHROME.nextStepAria}
              >
                {DIALOG_CHROME.nextStepLabel}
              </Button>
            </span>
          </Tooltip>
        )}
        <Tooltip title="Save your change. Patients will not see it until you compile and make it live.">
          <span>
            <Button
              variant="contained"
              onClick={handleSave}
              disabled={!canSave}
              aria-label="Save your changes"
            >
              {currentStepId === "save" ? "Approve and save" : "Save changes"}
            </Button>
          </span>
        </Tooltip>
      </DialogActions>
      {coach && tree && (() => {
        const node = findNode(tree, coach.nodeId);
        const term = node?.criterion?.preferred_term ?? "";
        const match = detectVaguePhrase(term);
        if (!match.isVague) return null;
        return (
          <ConceptCoachPopover
            open
            anchorEl={coach.anchor}
            vagueTerm={friendlyTerm(term)}
            match={match}
            onClose={() => setCoach(null)}
            onAddCriteria={handleCoachAddCriteria}
            onSearchMore={handleCoachSearchMore}
          />
        );
      })()}
      <ConceptSynonymDialog
        open={!!synonymEditorNodeId}
        node={
          synonymEditorNodeId && tree ? findNode(tree, synonymEditorNodeId) : null
        }
        onUpdate={handleUpdate}
        onClose={() => setSynonymEditorNodeId(null)}
        // Wizard (and any other open-by-node-id path): let the reviewer
        // undo a mistaken Step 3 pick by deleting the CONCEPT leaf so
        // the row goes back to unresolved. The Advanced chip editor
        // opens SynonymChipEditor's own dialog without this callback.
        onClearMatch={
          synonymEditorNodeId
            ? () => {
                handleUpdate({ kind: "remove", nodeId: synonymEditorNodeId });
                setSynonymEditorNodeId(null);
              }
            : undefined
        }
      />
    </Dialog>
  );
}

function findNode(node: EditableLogicNode, nodeId: string): EditableLogicNode | null {
  if (node.node_id === nodeId) return node;
  for (const child of node.children ?? []) {
    const hit = findNode(child, nodeId);
    if (hit) return hit;
  }
  return null;
}

function findParent(
  node: EditableLogicNode,
  childId: string,
): EditableLogicNode | null {
  for (const child of node.children ?? []) {
    if (child.node_id === childId) return node;
    const hit = findParent(child, childId);
    if (hit) return hit;
  }
  return null;
}

function groupLabel(kind: string): string {
  return GROUP_KIND_SHORT[kind as keyof typeof GROUP_KIND_SHORT] ?? kind;
}
