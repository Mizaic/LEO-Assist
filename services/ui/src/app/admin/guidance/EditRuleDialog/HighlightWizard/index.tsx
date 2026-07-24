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
 * The highlight-to-build rule wizard: a one-question-at-a-time flow
 * anchored to the live NICE guideline sentence, unified for both
 * building from scratch and reviewing an AI-drafted tree. See the
 * plan's wireframes for the exact per-step layout.
 *
 * Step 1 (StepPrerequisites) -- "What must ALWAYS be true?"
 * Step 2 (StepPathwaySplit) -- "Does this split into situations?"
 * Step 3 (PathwayConditionsStage, repeated once per pathway) --
 *   "Within this situation, what must ALL be true?"
 * Review -- the existing SentenceEditor, now anchored to what the
 *   wizard just built, so the hand-off is the same canvas a reviewer
 *   would otherwise land on directly.
 *
 * Every step mutates the SAME EditableLogicNode tree and NodeUpdate
 * contract every other surface (LogicTreeEditor, SentenceEditor) uses
 * -- this component only ever adds a thin, reversible layer of
 * "which question to ask next" on top, never a second data model.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  type Dispatch,
} from "react";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { findPathwaySplit } from "../pathwayDetection";
import SentenceEditor from "../SentenceEditor";
import type {
  PathwayTextBoundary,
  RecommendationStructure,
} from "../SentenceEditor/pathwayTextSplit";
import type { EditableLogicNode, NodeUpdate } from "../types";
import PathwayConditionsStage from "./PathwayConditionsStage";
import StepPathwaySplit from "./StepPathwaySplit";
import StepPrerequisites from "./StepPrerequisites";
import { WIZARD_CHROME } from "./copy";
import { materializePathways, readMaterializedPathways } from "./wizardMapping";
import WizardHeader from "./WizardHeader";
import {
  INITIAL_WIZARD_STATE,
  wizardReducer,
  type WizardAction,
  type WizardState,
  type WizardStepKind,
} from "./wizardState";

export interface HighlightWizardProps {
  tree: EditableLogicNode;
  recommendationText?: string | null;
  recommendationStructure?: RecommendationStructure | null;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
    initialQuery?: string,
    multiPick?: boolean,
  ) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  /** Falls back to whichever manual canvas the host renders when the
   *  reviewer opts out of the guided flow (Step1Who wires this to
   *  flip ViewModeToggle to "advanced"). */
  onSkipToManual: () => void;
  guidelineId?: string;
  currentRuleId?: string;
  /** Reports the wizard's own current step so the host can, for
   *  example, pin the guideline quote in the side panel until the
   *  reviewer reaches Review -- the only step where "what this rule
   *  means" is actually built up enough to be worth previewing. */
  onStepChange?: (step: WizardStepKind) => void;
}

function usePrerequisiteNodes(tree: EditableLogicNode): EditableLogicNode[] {
  return useMemo(() => {
    const split = findPathwaySplit(tree);
    if (split) return split.prerequisites;
    return tree.kind === "AND" ? tree.children ?? [] : [tree];
  }, [tree]);
}

/** Promotes CONFIRM_SPLIT to "ready immediately" only when every
 *  boundary already has a live pathway node -- otherwise the reducer
 *  parks in `materializing` until the effect below observes the
 *  tree mutation land. */
function useMaterializationEffect(
  tree: EditableLogicNode,
  state: WizardState,
  dispatch: Dispatch<WizardAction>,
) {
  useEffect(() => {
    if (!state.materializing || !state.boundaries) return;
    const nodes = readMaterializedPathways(tree, state.boundaries.length);
    if (nodes.length > 0) dispatch({ type: "PATHWAYS_READY" });
  }, [tree, state.materializing, state.boundaries, dispatch]);
}

export default function HighlightWizard({
  tree,
  recommendationText,
  recommendationStructure,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
  onSkipToManual,
  guidelineId,
  currentRuleId,
  onStepChange,
}: HighlightWizardProps) {
  const [state, dispatch] = useReducer(wizardReducer, INITIAL_WIZARD_STATE);
  const prerequisiteNodes = usePrerequisiteNodes(tree);
  useMaterializationEffect(tree, state, dispatch);

  useEffect(() => {
    onStepChange?.(state.step);
  }, [state.step, onStepChange]);

  const handleConfirmSplit = useCallback(
    (boundaries: PathwayTextBoundary[]) => {
      const nodes = materializePathways(tree, boundaries.length, onUpdate);
      dispatch({ type: "CONFIRM_SPLIT", boundaries, readyImmediately: nodes.length > 0 });
    },
    [tree, onUpdate],
  );

  const handleNoSplit = useCallback(() => {
    const text = recommendationText ?? "";
    dispatch({
      type: "CONFIRM_NO_SPLIT",
      boundary: { text, start: 0, end: text.length, source: "heuristic" },
    });
  }, [recommendationText]);

  const handleBack = useCallback(() => dispatch({ type: "BACK" }), []);

  return (
    <Stack spacing={2} data-testid="highlight-wizard">
      <WizardHeader step={state.step} onBack={handleBack} onSkipToManual={onSkipToManual} />

      {state.step === "prerequisites" && (
        <StepPrerequisites
          recommendationText={recommendationText}
          prerequisites={prerequisiteNodes}
          onEdit={onSelectNode}
          onRemove={(nodeId) => onUpdate({ kind: "remove", nodeId })}
          onAddFromSelection={(selection, anchor) =>
            onRequestAdd(tree.node_id, anchor, selection.text, true)
          }
          onConfirmNoMore={() => dispatch({ type: "CONFIRM_PREREQUISITES" })}
        />
      )}

      {state.step === "pathway-split" &&
        (state.materializing ? (
          <Typography variant="body2" color="text.secondary" role="status">
            {WIZARD_CHROME.materializingStatus}
          </Typography>
        ) : (
          <StepPathwaySplit
            recommendationText={recommendationText}
            recommendationStructure={recommendationStructure}
            onConfirm={handleConfirmSplit}
            onNoSplit={handleNoSplit}
          />
        ))}

      {state.step === "pathway-conditions" && state.boundaries && (
        <PathwayConditionsStage
          tree={tree}
          recommendationText={recommendationText}
          boundaries={state.boundaries}
          pathwayIndex={state.pathwayIndex}
          clusterGroupings={state.clusterGroupings}
          onSetClusterGrouping={(pathwayIndex, grouping) =>
            dispatch({ type: "SET_CLUSTER_GROUPING", pathwayIndex, grouping })
          }
          leadClusterGroupings={state.leadClusterGroupings}
          onSetLeadClusterGrouping={(pathwayIndex, grouping) =>
            dispatch({ type: "SET_LEAD_CLUSTER_GROUPING", pathwayIndex, grouping })
          }
          onSelectNode={onSelectNode}
          onUpdate={onUpdate}
          onRequestAdd={onRequestAdd}
          onConfirmPathway={() => dispatch({ type: "CONFIRM_PATHWAY" })}
        />
      )}

      {state.step === "review" && (
        <Stack spacing={1}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {WIZARD_CHROME.reviewTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {WIZARD_CHROME.reviewHelper}
          </Typography>
          <SentenceEditor
            root={tree}
            selectedNodeId={null}
            onSelect={onSelectNode}
            onUpdate={onUpdate}
            onRequestAdd={onRequestAdd}
            onRequestCoach={onRequestCoach}
            guidelineId={guidelineId}
            currentRuleId={currentRuleId}
          />
        </Stack>
      )}
    </Stack>
  );
}
