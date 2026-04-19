"use client";

/**
 * Widescreen step-rail editor for an AI-generated guidance rule.
 *
 * Layout:
 *   - Left column (rail): four numbered steps, jump-able. The current
 *     step gets the canonical 3px accent strip; ready steps show a
 *     green tick.
 *   - Centre column (canvas): one focused step body at a time. Steps
 *     are presentational components in ./steps/, fed from the state
 *     held in this orchestrator.
 *   - Right column (preview): always-on plain-English mirror of the
 *     rule + a "what the system will do" recap. On step 4 the pane
 *     swaps to a Before / After diff so the reviewer can see exactly
 *     what they are saving.
 *
 * Footer: sticky DialogActions with Back / Next / Save. Save is the
 * single primary action; it is gated on a >=3-character reason and a
 * valid tree, exactly as in the previous design.
 *
 * Saving POSTs to /api/guidance/rules/review/{id}/decision with
 * ``{ action: "edit", reason, updates: { name, strength, logic_tree } }``.
 * The backend writes a new versioned rule and returns the new rule_id.
 *
 * Design Controls: UN-LEO-AI-094, DI-LEO-AI-512, DO-LEO-AI-512,
 *                  R-LEO-AI-509, VT-LEO-AI-511.
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
import LivePreviewPane from "./LivePreviewPane";
import StepRail, { type StepDescriptor, type StepState } from "./StepRail";
import Step1Who from "./steps/Step1Who";
import Step2Suggest from "./steps/Step2Suggest";
import Step3Try from "./steps/Step3Try";
import Step4Save from "./steps/Step4Save";
import { GROUP_KIND_SHORT, STEP_IDS, friendlyTerm, type StepId } from "./copy";
import {
  applyUpdate,
  assignNodeIds,
  findValidationError,
  stripNodeIds,
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
  }) => void;
}

interface SearchTarget {
  mode: "replace" | "add" | "replace_action" | "idle";
  parentNodeId: string | null;
  nodeId: string | null;
  initialQuery: string;
  focusLabel: string | null;
}

const IDLE_TARGET: SearchTarget = {
  mode: "idle",
  parentNodeId: null,
  nodeId: null,
  initialQuery: "",
  focusLabel: null,
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
  const [searchPanelPinned, setSearchPanelPinned] = useState(false);
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
  const [currentStepId, setCurrentStepId] = useState<StepId>("who");

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
    setSearchPanelPinned(false);
    setCoach(null);
    setAction(rule.action ?? null);
    setOriginalAction(rule.action ?? null);
    setActionDirty(false);
    setCurrentStepId("who");
  }, [rule]);

  const summary = useMemo(() => treeToSentence(tree), [tree]);
  const beforeSummary = useMemo(
    () => treeToSentence(originalTree),
    [originalTree],
  );
  const duplicates = useMemo(() => findDuplicateConceptGroups(tree), [tree]);
  // Hash of the current tree -- used by TestPatientsPanel to auto-replay
  // whenever the reviewer's edits could change which patients match.
  const ruleSignature = useMemo(
    () => (tree ? JSON.stringify(stripNodeIds(tree)) : ""),
    [tree],
  );

  // The right-hand search column is "open" when the user is actively
  // picking a concept OR when they have explicitly pinned it open via
  // the slim rail. Otherwise it collapses to a 56px rail so the tree
  // gets the full step width.
  const searchPanelOpen = searchTarget.mode !== "idle" || searchPanelPinned;

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
    setSearchPanelPinned(false);
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

  function handleSelectNode(nodeId: string) {
    if (!tree) return;
    const focused = findNode(tree, nodeId);
    if (!focused) return;
    if (focused.kind !== "CONCEPT") {
      setSearchTarget(IDLE_TARGET);
      return;
    }
    const friendly = friendlyTerm(focused.criterion?.preferred_term);
    setSearchTarget({
      mode: "replace",
      parentNodeId: null,
      nodeId,
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping: ${friendly}`
        : "Pick a symptom or sign for the empty pill",
    });
  }

  function handleRequestAdd(parentNodeId: string) {
    if (!tree) return;
    const parent = findNode(tree, parentNodeId);
    setSearchTarget({
      mode: "add",
      parentNodeId,
      nodeId: null,
      initialQuery: "",
      focusLabel: parent
        ? `Adding to: ${groupLabel(parent.kind)}`
        : "Adding a symptom or sign",
    });
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
    setSearchTarget({
      mode: "add",
      parentNodeId: parent?.node_id ?? null,
      nodeId: null,
      initialQuery: topic,
      focusLabel: `Adding to: ${parent ? groupLabel(parent.kind) : "the rule"}`,
    });
    setSearchPanelPinned(true);
    setCoach(null);
  }

  function handleSelectAction() {
    const friendly = friendlyTerm(action?.preferred_term);
    setSearchTarget({
      mode: "replace_action",
      parentNodeId: null,
      nodeId: null,
      initialQuery: friendly,
      focusLabel: friendly
        ? `Swapping the procedure: ${friendly}`
        : "Pick the procedure the system should suggest",
    });
  }

  function handlePick(criterion: LogicCriterion) {
    if (searchTarget.mode === "replace_action") {
      setAction(criterion);
      setActionDirty(true);
      setSearchTarget(IDLE_TARGET);
      setSearchPanelPinned(false);
      return;
    }
    if (searchTarget.mode === "replace" && searchTarget.nodeId) {
      handleUpdate({ kind: "replace_concept", nodeId: searchTarget.nodeId, criterion });
      setSearchTarget(IDLE_TARGET);
      setSearchPanelPinned(false);
      return;
    }
    if (searchTarget.mode === "add" && searchTarget.parentNodeId) {
      handleUpdate({
        kind: "add_concept",
        parentNodeId: searchTarget.parentNodeId,
        criterion,
      });
    }
  }

  function handleSave() {
    if (!tree || !canSave) return;
    onSave({
      name: name.trim(),
      strength,
      logic_tree: stripNodeIds(tree),
      reason: reason.trim(),
      ...(actionDirty && action ? { action } : {}),
    });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      fullScreen={fullscreen}
      maxWidth="xl"
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
      <DialogTitle id="edit-rule-dialog-title" component="div" sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box sx={{ flex: 1 }}>
            <Typography
              variant="h6"
              component="h2"
              sx={{ fontWeight: 700, fontSize: "1.05rem" }}
            >
              Change this rule
            </Typography>
            {rule?.chapter_title && (
              <Typography variant="caption" color="text.secondary">
                {rule.guideline_id ? `${rule.guideline_id} - ` : ""}
                {rule.chapter_title}
              </Typography>
            )}
          </Box>
          <Tooltip title={fullscreen ? "Shrink to a window" : "Use the full screen"}>
            <IconButton
              onClick={() => setFullscreen((v) => !v)}
              size="small"
              aria-label={fullscreen ? "Shrink to a window" : "Use the full screen"}
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
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0 }}>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: {
              xs: "1fr",
              md: "minmax(220px, 3fr) minmax(0, 6fr) minmax(280px, 4fr)",
            },
            minHeight: "100%",
          }}
        >
          <StepRail
            steps={stepDescriptors}
            currentStepId={currentStepId}
            onJump={handleJumpStep}
          />
          <Box
            role="region"
            aria-label={`Step ${currentIndex + 1} of ${STEP_IDS.length}`}
            sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }}
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
                searchTarget={{
                  mode:
                    searchTarget.mode === "replace_action"
                      ? "idle"
                      : searchTarget.mode,
                  initialQuery: searchTarget.initialQuery,
                  focusLabel: searchTarget.focusLabel,
                  nodeId: searchTarget.nodeId,
                }}
                searchPanelOpen={
                  searchPanelOpen && searchTarget.mode !== "replace_action"
                }
                onOpenSearchPanel={() => setSearchPanelPinned(true)}
                onPickConcept={handlePick}
                onSelectNode={handleSelectNode}
                onUpdate={handleUpdate}
                onRequestAdd={handleRequestAdd}
                onRequestCoach={handleRequestCoach}
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
                />
                {searchTarget.mode === "replace_action" && (
                  <Box
                    sx={{
                      p: 1.5,
                      borderRadius: 1.5,
                      border: "1px solid",
                      borderColor: "divider",
                      bgcolor: "background.paper",
                    }}
                  >
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
            {currentStepId === "try" && rule?.rule_id && (
              <Step3Try
                ruleId={rule.rule_id}
                guidelineId={rule.guideline_id}
                ruleSignature={ruleSignature}
                ruleName={name || rule.name}
                recommendationText={rule.recommendation_text}
                draftRule={
                  tree
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
              />
            )}
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
              borderLeft: { xs: "none", md: "1px solid" },
              borderTop: { xs: "1px solid", md: "none" },
              borderColor: { xs: "divider", md: "divider" },
              bgcolor: "grey.50",
              minWidth: 0,
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
      </DialogContent>
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
