/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-D6CE2AA5
 *   DI: DI-A3107424
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-D6CE2AA5")
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

import { useCallback, useEffect, useMemo, useState } from "react";
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
import CloseIcon from "@mui/icons-material/Close";
import FullscreenIcon from "@mui/icons-material/Fullscreen";
import FullscreenExitIcon from "@mui/icons-material/FullscreenExit";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";

import ConceptCoachPopover from "./ConceptCoachPopover";
import ConceptSearchPanel from "./ConceptSearchPanel";
import ChipSearchPopover from "./ChipSearchPopover";
import HorizontalStepper, {
  type StepDescriptor,
  type StepState,
} from "./HorizontalStepper";
import LivePreviewPane from "./LivePreviewPane";
import type { SandboxImpactBadge } from "./types";
import type { SandboxReportState } from "./TestPatientsPanel";
import Step1Who from "./steps/Step1Who";
import Step2Suggest from "./steps/Step2Suggest";
import Step3Try from "./steps/Step3Try";
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
  findValidationError,
  hasOrRootWithPrerequisites,
  observationWithCriterion,
  promoteOrPrerequisites,
  stripNodeIds,
  wrapRootInAnd,
} from "./treeOps";
import { findDuplicateConceptGroups } from "./namedSets";
import { treeToSentence } from "./treeToSentence";
import { detectVaguePhrase } from "./vaguePhrases";
import type { EditableLogicNode, LogicCriterion, NodeUpdate } from "./types";

export interface EditableRule {
  rule_id: string;
  name?: string;
  strength?: string;
  guideline_id?: string;
  chapter_title?: string;
  recommendation_text?: string;
  logic_tree?: unknown;
  /** Recommended SNOMED procedure that fires when the rule matches.
   *  Surfaced from the API's actionJson; null when uncoded. */
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
    strength: string;
    logic_tree: Record<string, unknown>;
    reason: string;
    /** Only set when the reviewer changed the action SNOMED concept;
     *  omitting it preserves the predecessor's actionJson server-side. */
    action?: LogicCriterion;
    is_default?: boolean;
  }) => void;
}

interface SearchTarget {
  mode: "replace" | "add" | "replace_action" | "idle";
  parentNodeId: string | null;
  nodeId: string | null;
  /** When mode is ``replace``, distinguishes symptom chips from lab values. */
  replaceKind: "concept" | "observation" | null;
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
  initialQuery: "",
  focusLabel: null,
  anchorEl: null,
};

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
  const [strength, setStrength] = useState("unspecified");
  const [originalStrength, setOriginalStrength] = useState("unspecified");
  const [reason, setReason] = useState("");
  const [searchTarget, setSearchTarget] = useState<SearchTarget>(IDLE_TARGET);
  const [showRecommendation, setShowRecommendation] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [coach, setCoach] = useState<{
    nodeId: string;
    anchor: HTMLElement;
  } | null>(null);
  // The SNOMED-coded recommended procedure (action) -- separate from the
  // logic tree because it is what the system *suggests* when the rule
  // matches, not what the patient must have. ``actionDirty`` lets us
  // omit ``action`` from the save payload when the reviewer never
  // touched it, so the server preserves the predecessor's actionJson
  // unchanged (DI-LEO-AI-170 safety constraint).
  const [action, setAction] = useState<LogicCriterion | null>(null);
  const [originalAction, setOriginalAction] = useState<LogicCriterion | null>(
    null,
  );
  const [actionDirty, setActionDirty] = useState(false);
  const [isDefault, setIsDefault] = useState(false);
  const [currentStepId, setCurrentStepId] = useState<StepId>("who");
  /**
   * Phase 4 -- latest sandbox replay summary, pushed up from
   * TestPatientsPanel (via Step3Try) so the SentenceCanvas in
   * Step1Who can render an inline fire/no-fire badge per card. Reset
   * when the rule prop changes (different rule => previous badges
   * are not for this rule).
   */
  const [sandboxReport, setSandboxReport] =
    useState<SandboxReportState | null>(null);

  useEffect(() => {
    if (!rule) return;
    const initialTree =
      rule.logic_tree && typeof rule.logic_tree === "object"
        ? assignNodeIds(rule.logic_tree as EditableLogicNode)
        : assignNodeIds({ kind: "AND", children: [] });
    setTree(initialTree);
    setOriginalTree(initialTree);
    setName(rule.name ?? "");
    setStrength(rule.strength || "unspecified");
    setOriginalStrength(rule.strength || "unspecified");
    setReason("");
    setSearchTarget(IDLE_TARGET);
    setShowRecommendation(false);
    setCoach(null);
    setAction(rule.action ?? null);
    setOriginalAction(rule.action ?? null);
    setActionDirty(false);
    setIsDefault(rule.is_default ?? false);
    setCurrentStepId("who");
    setSandboxReport(null);
  }, [rule]);

  /**
   * Convert the panel's `SandboxReportState` (which carries the
   * signature it was produced against) into the canvas-facing
   * `SandboxImpactBadge`. The signature is intentionally stripped
   * here -- the canvas only needs status + counts. */
  const sandboxBadge: SandboxImpactBadge | undefined = useMemo(() => {
    if (!sandboxReport) return undefined;
    return {
      status: sandboxReport.status,
      firingPatients: sandboxReport.firingPatients,
      totalPatients: sandboxReport.totalPatients,
    };
  }, [sandboxReport]);

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
  const reasonReady = reason.trim().length >= 3;
  const canSave =
    !!tree && !validationError && reasonReady && !saving;

  const stepDescriptors: StepDescriptor[] = useMemo(() => {
    const whoState: StepState = !tree
      ? "not_started"
      : validationError
        ? "in_progress"
        : "ready";
    const suggestState: StepState =
      action && action.snomed_concept_id
        ? "ready"
        : strength === "unspecified" && !action
          ? "not_started"
          : "in_progress";
    // Step 3 is opt-in evidence -- it never blocks save, so we mark
    // it ready unconditionally so the user does not feel pressured
    // to compile a sandbox before saving a wording-only fix.
    const tryState: StepState = "ready";
    const saveState: StepState = reasonReady ? "ready" : "not_started";
    return [
      { id: "who", state: whoState },
      { id: "suggest", state: suggestState },
      { id: "try", state: tryState },
      { id: "save", state: saveState },
    ];
  }, [tree, validationError, action, strength, reasonReady]);

  const handleJumpStep = useCallback((next: StepId) => {
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
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping: ${friendly}`
        : "Pick a symptom or sign for the empty pill",
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
      initialQuery: "",
      focusLabel: parent
        ? `Adding to: ${groupLabel(parent.kind)}`
        : "Adding a symptom or sign",
      anchorEl: anchor ?? null,
    });
  }

  /** Empty-state CTA: anchor a popover for adding the very first
   *  symptom under the root tree. */
  function handleAddFirstSymptom(anchor: HTMLElement) {
    if (!tree) return;
    handleRequestAdd(tree.node_id, anchor);
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
      initialQuery: topic,
      focusLabel: `Adding to: ${parent ? groupLabel(parent.kind) : "the rule"}`,
      anchorEl: coach.anchor,
    });
    setCoach(null);
  }

  function handleSelectAction() {
    const friendly = friendlyTerm(action?.preferred_term);
    setSearchTarget({
      mode: "replace_action",
      parentNodeId: null,
      nodeId: null,
      replaceKind: null,
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping the procedure: ${friendly}`
        : "Pick the procedure the system should suggest",
      anchorEl: null,
    });
  }

  function handlePick(criterion: LogicCriterion) {
    if (searchTarget.mode === "replace_action") {
      setAction(criterion);
      setActionDirty(true);
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
      strength,
      logic_tree: stripNodeIds(tree),
      reason: reason.trim(),
      ...(actionDirty && action ? { action } : {}),
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
      aria-labelledby="edit-rule-dialog-title"
      PaperProps={{
        sx: fullscreen
          ? { display: "flex", flexDirection: "column" }
          : {
              minHeight: "80vh",
              display: "flex",
              flexDirection: "column",
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
      <DialogContent dividers sx={{ p: 0 }}>
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            minHeight: "100%",
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
              flex: 1,
              minHeight: 0,
              minWidth: 0,
            }}
          >
            <Box
              role="region"
              aria-label={`Step ${currentIndex + 1} of ${STEP_IDS.length}`}
              sx={{
                p: { xs: 2, md: 3 },
                minWidth: 0,
                flex: { xs: "1 1 auto", md: "0 0 60%" },
                width: { xs: "100%", md: "60%" },
                overflowY: "auto",
              }}
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
                showRecommendation={showRecommendation}
                onToggleRecommendation={() =>
                  setShowRecommendation((v) => !v)
                }
                onSelectNode={handleSelectNode}
                onUpdate={handleUpdate}
                onRequestAdd={handleRequestAdd}
                onRequestCoach={handleRequestCoach}
                onAddFirstSymptom={handleAddFirstSymptom}
                ruleId={rule?.rule_id ?? ""}
                onAIDraft={(aiTree) => {
                  const withIds = assignNodeIds(aiTree);
                  setTree(withIds);
                }}
              />
            )}
            {currentStepId === "suggest" && (
              <Stack spacing={2}>
                <Step2Suggest
                  name={name}
                  onNameChange={setName}
                  strength={strength}
                  onStrengthChange={setStrength}
                  action={action}
                  isActionSelected={searchTarget.mode === "replace_action"}
                  onSelectAction={handleSelectAction}
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
            {/* Step 3 stays mounted across all steps so the
                debounced sandbox auto-run keeps producing inline
                impact badges for Step 1 even while the reviewer is
                still editing the canvas (Phase 4). The panel hides
                its visual tree when the reviewer is not on the
                "try" step but its replay loop continues. */}
            <Box
              sx={{
                display: currentStepId === "try" ? "block" : "none",
              }}
              aria-hidden={currentStepId !== "try"}
            >
              <Step3Try
                ruleId={rule?.rule_id ?? ""}
                guidelineId={rule?.guideline_id}
                ruleName={name || rule?.name}
                recommendationText={rule?.recommendation_text}
                draftRule={
                  tree && rule?.rule_id
                    ? {
                        rule_id: rule.rule_id,
                        name: name || rule.name || "",
                        strength: strength || "unspecified",
                        guideline_id: rule.guideline_id,
                        guideline_title: rule.chapter_title || "",
                        chapter_title: rule.chapter_title,
                        recommendation_verbatim:
                          rule.recommendation_text || "",
                        logic_tree: stripNodeIds(tree),
                        ...(actionDirty && action ? { action } : {}),
                      }
                    : null
                }
                onSandboxReportChange={setSandboxReport}
              />
            </Box>
            {currentStepId === "save" && (
              <Step4Save
                reason={reason}
                onReasonChange={setReason}
                saving={saving}
                reasonError={
                  validationError
                    ? `Fix the rule first: ${validationError}`
                    : undefined
                }
              />
            )}
            </Box>
            <Box
              sx={{
                flex: { xs: "1 1 auto", md: "0 0 40%" },
                width: { xs: "100%", md: "40%" },
                borderTop: { xs: "1px solid", md: "none" },
                borderLeft: { xs: "none", md: "1px solid" },
                borderColor: "divider",
                bgcolor: "grey.50",
                overflowY: "auto",
                minHeight: 0,
              }}
            >
              <LivePreviewPane
                summary={summary}
                strength={strength}
                action={action}
                showBeforeAfter={currentStepId === "save"}
                beforeSummary={beforeSummary}
                beforeStrength={originalStrength}
                beforeAction={originalAction}
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
