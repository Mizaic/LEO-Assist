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
 * Review -- short confirmation that points at the right-column live
 *   preview (no second Simple editor). Power edits use Advanced.
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
  useState,
  type Dispatch,
} from "react";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { findPathwaySplit } from "../pathwayDetection";
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
import { buildInitialWizardState } from "./initialWizardState";
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
  /**
   * Opens the add/remove/depth synonym editor for a CONCEPT leaf that
   * already has a matched code -- see `PathwayConditionsStage`'s doc
   * comment on the same prop. Used by both Step 1 (editing an
   * existing prerequisite) and Step 3 (editing an existing pathway
   * condition) row clicks.
   */
  onEditConcept: (nodeId: string) => void;
  guidelineId?: string;
  currentRuleId?: string;
  /** Reports the wizard's own current step so the host can, for
   *  example, pin the guideline quote in the side panel until the
   *  reviewer reaches Review -- the only step where "what this rule
   *  means" is actually built up enough to be worth previewing. */
  onStepChange?: (step: WizardStepKind) => void;
  /**
   * `auto` (default) opens Review when every pathway already has
   * leaves -- so reopening a saved rule does not force Step 1 again.
   * `fresh` always starts at prerequisites (tests / rebuild).
   */
  startMode?: "auto" | "fresh";
  /**
   * Reports the situations the quote panel should colour:
   *  - Step 2: proposed boundaries + null active index (colour-per-
   *    situation overview of what the text detector found)
   *  - Step 3: confirmed boundaries + the active pathway index
   *    (scoped capture view)
   *  - otherwise: `(null, null)` -- plain / tree-leaf highlighting
   */
  onActiveSituationChange?: (
    boundaries: PathwayTextBoundary[] | null,
    activePathwayIndex: number | null,
  ) => void;
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
  onEditConcept,
  guidelineId,
  currentRuleId,
  onStepChange,
  startMode = "auto",
  onActiveSituationChange,
}: HighlightWizardProps) {
  const [state, dispatch] = useReducer(wizardReducer, undefined, () =>
    startMode === "fresh"
      ? INITIAL_WIZARD_STATE
      : buildInitialWizardState(tree, recommendationText, recommendationStructure),
  );
  const [proposedBoundaries, setProposedBoundaries] = useState<
    PathwayTextBoundary[] | null
  >(null);
  const prerequisiteNodes = usePrerequisiteNodes(tree);
  useMaterializationEffect(tree, state, dispatch);

  useEffect(() => {
    onStepChange?.(state.step);
  }, [state.step, onStepChange]);

  useEffect(() => {
    if (state.step === "pathway-conditions" && state.boundaries) {
      onActiveSituationChange?.(state.boundaries, state.pathwayIndex);
    } else if (state.step === "pathway-split" && proposedBoundaries) {
      // Null active index = Step 2 overview: paint every situation
      // its own colour so the detector's full wording is visible.
      onActiveSituationChange?.(proposedBoundaries, null);
    } else {
      onActiveSituationChange?.(null, null);
    }
  }, [
    state.step,
    state.boundaries,
    state.pathwayIndex,
    proposedBoundaries,
    onActiveSituationChange,
  ]);

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
      <WizardHeader step={state.step} onBack={handleBack} />

      {state.step === "prerequisites" && (
        <StepPrerequisites
          recommendationText={recommendationText}
          prerequisites={prerequisiteNodes}
          onEdit={onSelectNode}
          onEditConcept={onEditConcept}
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
            onProposedBoundariesChange={setProposedBoundaries}
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
          onEditConcept={onEditConcept}
          onConfirmPathway={() => dispatch({ type: "CONFIRM_PATHWAY" })}
        />
      )}

      {state.step === "review" && (
        <Stack spacing={1} data-testid="wizard-review">
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {WIZARD_CHROME.reviewTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {WIZARD_CHROME.reviewHelper}
          </Typography>
        </Stack>
      )}
    </Stack>
  );
}
