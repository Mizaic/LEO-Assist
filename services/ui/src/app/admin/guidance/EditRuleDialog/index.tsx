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
 *   |     CANVAS (~60%)        |   LivePreviewPane (~40%)    |
 *   |                          |   always visible, no toggle |
 *   |                          |                             |
 *   +--- Sticky DialogActions (Cancel | Back | Next | Save) -+
 *
 *   - The plain-English LivePreviewPane is the source of truth for
 *     reviewers; it sits permanently on the right so the user always
 *     knows what the rule means as they edit. The previous one-line
 *     LivePreviewBanner + slide-in LivePreviewDrawer trade-off was
 *     deleted in Phase 3.
 *   - ChipSearchPopover still anchors to the chip / +Add element the
 *     reviewer just clicked, so concept search appears in context
 *     instead of in a separate column.
 *
 * Footer: sticky DialogActions with Back / Next / Save. Save is the
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

import ConceptCoachPopover from "./ConceptCoachPopover";
import ConceptSearchPanel from "./ConceptSearchPanel";
import ChipSearchPopover from "./ChipSearchPopover";
import HorizontalStepper, {
  type StepDescriptor,
  type StepState,
} from "./HorizontalStepper";
import LivePreviewPane from "./LivePreviewPane";
import Step1Who from "./steps/Step1Who";
import Step2Suggest from "./steps/Step2Suggest";
import Step4Save from "./steps/Step4Save";
import {
  DIALOG_CHROME,
  GROUP_KIND_SHORT,
  STEP_IDS,
  friendlyTerm,
  type StepId,
} from "./copy";
import {
  applyUpdate,
  assignNodeIds,
  canHaveChildren,
  findActionsValidationError,
  findValidationError,
  hasOrRootWithPrerequisites,
  observationWithCriterion,
  promoteOrPrerequisites,
  sanitiseActionsForSave,
  stripNodeIds,
  wrapRootInAnd,
} from "./treeOps";
import { findDuplicateConceptGroups } from "./namedSets";
import { treeToSentence } from "./treeToSentence";
import { detectVaguePhrase } from "./vaguePhrases";
import { slidePanelVariants } from "../motionPresets";
import { normalizeRuleActions } from "../actionShape";
import type {
  EditableLogicNode,
  LogicCriterion,
  NodeUpdate,
  RuleAction,
} from "./types";

export interface EditableRule {
  rule_id: string;
  name?: string;
  /** Deprecated rule-level strength; used only to seed a legacy single
   *  action's strength when ``actions`` is absent (back-compat). */
  strength?: string;
  guideline_id?: string;
  chapter_title?: string;
  recommendation_text?: string;
  logic_tree?: unknown;
  /** One or more recommended procedures, each with its own strength. */
  actions?: RuleAction[];
  /** Deprecated: legacy single recommended SNOMED procedure. Surfaced
   *  from the API's actionJson for rules not yet migrated to
   *  ``actions``; null when uncoded. */
  action?: LogicCriterion | null;
  /** When true this rule fires only if no other rule in the guideline matched. */
  is_default?: boolean;
}

interface Props {
  rule: EditableRule | null;
  open: boolean;
  saving?: boolean;
  onClose: () => void;
  onSave: (payload: {
    name: string;
    logic_tree: Record<string, unknown>;
    reason: string;
    /** Only set when the reviewer changed the recommended procedures;
     *  omitting it preserves the predecessor's actionJson server-side. */
    actions?: Array<Record<string, unknown>>;
    is_default?: boolean;
  }) => void;
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
  const [isDefault, setIsDefault] = useState(false);
  const [currentStepId, setCurrentStepId] = useState<StepId>("who");
  const [stepDirection, setStepDirection] = useState<1 | -1>(1);
  const prevStepIndexRef = useRef(0);
  const { reducedMotion } = useMotion();

  useEffect(() => {
    if (!rule) return;
    const initialTree =
      rule.logic_tree && typeof rule.logic_tree === "object"
        ? assignNodeIds(rule.logic_tree as EditableLogicNode)
        : assignNodeIds({ kind: "AND", children: [] });
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
    setIsDefault(rule.is_default ?? false);
    setCurrentStepId("who");
  }, [rule]);

  const summary = useMemo(() => treeToSentence(tree), [tree]);
  const beforeSummary = useMemo(
    () => treeToSentence(originalTree),
    [originalTree],
  );
  const duplicates = useMemo(() => findDuplicateConceptGroups(tree), [tree]);

  // The chip-anchored search popover is open whenever there is an
  // active concept-picking target with an anchor element. The
  // `replace_action` slot in Step 2 still renders the search inline
  // (it is not a chip-anchored interaction) so we only treat it as
  // the chip popover when the anchor is set.
  const chipPopoverOpen =
    (searchTarget.mode === "replace" || searchTarget.mode === "add") &&
    searchTarget.anchorEl !== null;

  const validationError = useMemo(() => findValidationError(tree), [tree]);
  const actionsError = useMemo(
    () => findActionsValidationError(actions),
    [actions],
  );
  const reasonReady = reason.trim().length >= 3;
  const canSave =
    !!tree && !validationError && !actionsError && reasonReady && !saving;

  const stepDescriptors: StepDescriptor[] = useMemo(() => {
    const whoState: StepState = !tree
      ? "not_started"
      : validationError
        ? "in_progress"
        : "ready";
    const allCoded =
      actions.length > 0 &&
      actions.every((a) => Boolean(a.criterion?.snomed_concept_id));
    const allBlank = actions.every(
      (a) => !a.criterion?.snomed_concept_id && a.strength === "unspecified",
    );
    const suggestState: StepState = allCoded
      ? "ready"
      : allBlank
        ? "not_started"
        : "in_progress";
    const saveState: StepState = reasonReady ? "ready" : "not_started";
    return [
      { id: "who", state: whoState },
      { id: "suggest", state: suggestState },
      { id: "save", state: saveState },
    ];
  }, [tree, validationError, actions, reasonReady]);

  const handleJumpStep = useCallback((next: StepId) => {
    const nextIndex = STEP_IDS.indexOf(next);
    setStepDirection(nextIndex >= prevStepIndexRef.current ? 1 : -1);
    prevStepIndexRef.current = nextIndex;
    setCurrentStepId(next);
    setSearchTarget(IDLE_TARGET);
  }, []);

  const currentIndex = STEP_IDS.indexOf(currentStepId);
  const isFirstStep = currentIndex === 0;
  const isLastStep = currentIndex === STEP_IDS.length - 1;

  const handleNext = useCallback(() => {
    if (isLastStep) return;
    handleJumpStep(STEP_IDS[currentIndex + 1]);
  }, [currentIndex, isLastStep, handleJumpStep]);

  const handleBack = useCallback(() => {
    if (isFirstStep) return;
    handleJumpStep(STEP_IDS[currentIndex - 1]);
  }, [currentIndex, isFirstStep, handleJumpStep]);

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
    });
  }

  function handleRequestAdd(
    parentNodeId: string,
    anchor?: HTMLElement | null,
  ) {
    if (!tree) return;
    const parent = findNode(tree, parentNodeId);
    setSearchTarget({
      mode: "add",
      parentNodeId,
      nodeId: null,
      replaceKind: null,
      actionIndex: null,
      initialQuery: "",
      focusLabel: parent
        ? `Adding to: ${groupLabel(parent.kind)}`
        : "Adding a symptom, sign, procedure, or situation",
      anchorEl: anchor ?? null,
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

  function handleRemoveAction(index: number) {
    setActions((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== index)));
    setActionsDirty(true);
    if (searchTarget.mode === "replace_action" && searchTarget.actionIndex === index) {
      setSearchTarget(IDLE_TARGET);
    }
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
      const parent = findNode(tree, searchTarget.parentNodeId);
      if (parent && canHaveChildren(parent.kind)) {
        handleUpdate({
          kind: "add_concept",
          parentNodeId: searchTarget.parentNodeId,
          criterion,
        });
      } else if (parent && parent.node_id === tree.node_id) {
        const groupRoot = wrapRootInAnd(tree);
        setTree(
          applyUpdate(groupRoot, {
            kind: "add_concept",
            parentNodeId: groupRoot.node_id,
            criterion,
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
    onSave({
      name: name.trim(),
      logic_tree: stripNodeIds(tree),
      reason: reason.trim(),
      ...(actionsDirty ? { actions: sanitiseActionsForSave(actions) } : {}),
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
          <IconButton
            onClick={onClose}
            size="small"
            aria-label="Close without saving"
            disabled={saving}
            sx={{ color: "text.secondary" }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
      </DialogTitle>
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
            steps={stepDescriptors}
            currentStepId={currentStepId}
            onJump={handleJumpStep}
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
              aria-label={`Step ${currentIndex + 1} of ${STEP_IDS.length}`}
              sx={{
                p: { xs: 2, md: 3 },
                minWidth: 0,
                minHeight: 0,
                flex: { xs: "1 1 auto", md: "0 0 60%" },
                width: { xs: "100%", md: "60%" },
                overflowY: { xs: "visible", md: "auto" },
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
            {validationError && currentStepId === "who" && (
              <Alert
                severity="warning"
                sx={{ py: 0.5, mb: 2 }}
                role="status"
              >
                {validationError}
              </Alert>
            )}
            {currentStepId === "who" && (
              <Step1Who
                tree={tree}
                selectedNodeId={searchTarget.nodeId}
                duplicates={duplicates}
                recommendationText={rule?.recommendation_text}
                onSelectNode={handleSelectNode}
                onUpdate={handleUpdate}
                onRequestAdd={handleRequestAdd}
                onRequestCoach={handleRequestCoach}
                onAddFirstSymptom={handleAddFirstSymptom}
                onAddFirstDemographic={handleAddFirstDemographic}
                onAddFirstObservation={handleAddFirstObservation}
                ruleId={rule?.rule_id ?? ""}
                guidelineId={rule?.guideline_id}
                onAIDraft={(aiTree) => {
                  const withIds = assignNodeIds(aiTree);
                  setTree(withIds);
                }}
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
                  validationError
                    ? `Fix the rule first: ${validationError}`
                    : actionsError
                      ? `Fix the rule first: ${actionsError}`
                      : undefined
                }
              />
            )}
            </fm.div>
            </Box>
            <Box
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
              <LivePreviewPane
                summary={summary}
                actions={actions}
                showBeforeAfter={currentStepId === "save"}
                beforeSummary={beforeSummary}
                beforeActions={originalActions}
              />
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
        onPick={handlePick}
        onPickObservation={handlePickObservation}
        onClose={handleClosePopover}
      />
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
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Box sx={{ flex: 1 }} />
        {saving && (
          <CircularProgress size={18} aria-label="Saving your changes" />
        )}
        <Button
          onClick={handleBack}
          disabled={isFirstStep || saving}
          startIcon={<ArrowBackRoundedIcon fontSize="small" />}
          aria-label="Go back to the previous step"
        >
          Back
        </Button>
        {!isLastStep && (
          <Button
            variant="outlined"
            onClick={handleNext}
            disabled={saving}
            endIcon={<ArrowForwardRoundedIcon fontSize="small" />}
            aria-label="Go to the next step"
          >
            Next
          </Button>
        )}
        <Button
          variant="contained"
          onClick={handleSave}
          disabled={!canSave}
          aria-label="Save your changes"
        >
          Save changes
        </Button>
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
